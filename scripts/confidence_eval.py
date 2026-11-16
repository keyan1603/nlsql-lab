"""Does the model's own token probability tell us which answers to escalate? Computed from runs/confidence-<label>.jsonl and the saved hosted answers.

    python scripts/confidence_eval.py [--label xiyan7bft-e2]

PRE-REGISTERED PLAN (written before the data was collected):
  * Signal: mean token log-probability of the reply (also min, 10th percentile, share of tokens below -1). One feature, mean, is the headline; the others are reported, not chosen between.
  * The threshold is chosen on the POOL (core + hard + hard2) only and applied unchanged to the held-out set. Held-out numbers are never used to pick it.
  * Compared at the same share of questions sent to the hosted model with (a) the ordinary checks alone (error, empty result, invented value) and (b) a random router sending the same share,
    which is the bar a real signal has to beat clearly.
  * Reported with the AUC of the signal for 'this answer is wrong' (only questions where the model wrote SQL), so a weak signal is visible as such.
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from nlsql.invented import invented_values                      # noqa: E402
from route_eval import SETS, jl, wilson                         # noqa: E402


def features(tokens: list) -> dict:
    lp = sorted(t[1] for t in tokens) or [0.0]
    n = len(lp)
    return {"mean": sum(lp) / n, "min": lp[0], "p10": lp[max(0, int(0.1 * n) - 1)], "below1": -sum(1 for x in lp if x < -1.0) / n}


def auc(scores_pos: list, scores_neg: list) -> float:
    """P(score of a wrong answer is lower than that of a right one); ties count half. 0.5 is chance, 1.0 perfect (low score = wrong)."""
    if not scores_pos or not scores_neg:
        return float("nan")
    wins = sum((p < q) + 0.5 * (p == q) for p in scores_pos for q in scores_neg)
    return wins / (len(scores_pos) * len(scores_neg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="xiyan7bft-e2")
    a = ap.parse_args()
    recs = [json.loads(l) for l in (ROOT / "runs" / f"confidence-{a.label}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    hosted = {s: jl(ROOT / "runs" / f"gemini-flashlite{SETS[s][0]}.jsonl") for s in SETS}
    rows = []
    for r in recs:
        h = hosted[r["set"]].get(r["qid"])
        if h is None:
            continue
        f = features(r["tokens"])
        sql = r["kind"] == "sql"
        checks = sql and (r["status"] in ("error", "empty") or bool(invented_values(r["question"], r["sql"] or "")))
        rows.append({**r, **f, "checks": bool(checks), "host_pass": bool(h["passed"]), "pool": r["set"] != "heldout"})
    L = ["# Does the model's own token probability say which answers to escalate?", "",
         f"Model run `{a.label}`, one attempt per question, no repair. Pre-registered plan in the script header: the threshold is fixed on the pool (core, hard, hard2) and applied unchanged to the held-out set.", ""]
    for name, grp in (("Pool", [r for r in rows if r["pool"]]), ("Held-out", [r for r in rows if not r["pool"]])):
        ans = [r for r in grp if r["kind"] == "sql" and r["expected"] == "answer"]
        L += [f"## {name}: {len(grp)} questions ({len(ans)} answerable with SQL)", "", "| Signal | AUC for 'this answer is wrong' |", "|---|---|"]
        for k in ("mean", "min", "p10", "below1"):
            L.append(f"| {k} | {auc([r[k] for r in ans if not r['passed']], [r[k] for r in ans if r['passed']]):.3f} |")
        wrong_checks = [r for r in ans if not r["passed"]]
        L += ["", f"Local first attempt correct: {sum(r['passed'] for r in grp)} of {len(grp)}. Wrong answers the ordinary checks catch: {sum(r['checks'] for r in wrong_checks)} of {len(wrong_checks)}.", ""]
    pool = [r for r in rows if r["pool"]]
    held = [r for r in rows if not r["pool"]]
    if not pool:
        print("\n".join(L)); return 0

    def run(grp: list, thr: float | None, feat: str = "mean"):
        """Escalate on the checks, and (when thr is set) also when the feature is below thr. Returns (correct, n, hosted share)."""
        k = esc = 0
        for r in grp:
            e = r["checks"] or (thr is not None and r["kind"] == "sql" and r[feat] < thr)
            esc += e
            k += r["host_pass"] if e else r["passed"]
        return k, len(grp), esc / len(grp)

    def random_expect(grp: list, share: float) -> float:
        e = [r for r in grp if r["checks"]]
        rest = [r for r in grp if not r["checks"]]
        base_share = len(e) / len(grp)
        p = 0.0 if len(rest) == 0 else max(0.0, min(1.0, (share - base_share) / (len(rest) / len(grp))))
        return sum(r["host_pass"] for r in e) + sum((1 - p) * r["passed"] + p * r["host_pass"] for r in rest)

    L += ["## Escalating on the checks plus low confidence", "",
          "Thresholds on the mean log-probability are picked on the pool so that the total share sent to the hosted model hits the target, then applied unchanged to the held-out set. "
          "'Random' is the expected score of sending the same share at random (after the checks).", "",
          "| Target share | Threshold | Pool correct | Pool share | Pool random | Held-out correct | Held-out share | Held-out random |", "|---|---|---|---|---|---|---|---|"]
    base_k, n, base_share = run(pool, None)
    hk, hn, hs = run(held, None) if held else (0, 0, 0)
    L.append(f"| checks only | none | {base_k} of {n} ({base_k / n:.1%}) | {base_share:.1%} | n/a | {hk} of {hn} | {hs:.1%} | n/a |")
    cand = sorted({round(r["mean"], 4) for r in pool if r["kind"] == "sql"})
    for target in (0.20, 0.30, 0.40, 0.50):
        thr = min(cand, key=lambda t: abs(run(pool, t)[2] - target))
        k, n, sh = run(pool, thr)
        hk, hn, hs = run(held, thr) if held else (0, 0, 0)
        L.append(f"| {target:.0%} | {thr:.3f} | {k} of {n} ({k / n:.1%}) | {sh:.1%} | {random_expect(pool, sh) / n:.1%} | "
                 f"{hk} of {hn} ({hk / hn:.1%}) | {hs:.1%} | {random_expect(held, hs) / hn:.1%} |" if hn else f"| {target:.0%} | {thr:.3f} | {k} of {n} | {sh:.1%} | {random_expect(pool, sh) / n:.1%} | | | |")
    L += ["", "For reference, the saved-answer simulation of escalating when the 3B and 7B disagree scored 154 of 181 (85.1%) with 70 of 181 (38.7%) sent up on the pool, and 44 of 52 (84.6%) with 16 sent up on the held-out set.", ""]
    (ROOT / "docs" / "results" / "confidence_signal.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
