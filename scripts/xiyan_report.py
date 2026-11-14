"""Build docs/results/xiyan/summary.md: the final XiYan configuration against the baselines, from saved run files (no model is called).

    python scripts/xiyan_report.py
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from route_eval import sign_p, wilson     # noqa: E402

DATA = {"core": "questions", "hard": "questions_hard", "hard2": "questions_hard2", "decline": "questions_decline"}
SYSTEMS = {
    "XiYan 7B Q4_K_M, plain prompt": {"core": "xiyan7b-q4km", "hard": "xiyan7b-q4km-hard", "hard2": "xiyan7b-q4km-hard2", "decline": "imp-base-decline"},
    "XiYan 7B, final (tuned prompt + 4 decline examples + retry 2)": {s: f"xiyan7b-final-{s}" for s in DATA},
    "Tuned Qwen2.5-Coder-3B (run 6 + retry 2)": {s: f"tuned6r2-{s}" for s in DATA},
    "gemini-3.5-flash-lite (hosted, plain prompt)": {"core": "gemini-flashlite", "hard": "gemini-flashlite-hard", "hard2": "gemini-flashlite-hard2", "decline": "gemini-flashlite-decline"},
}


def jl(label):
    p = ROOT / "runs" / f"{label}.jsonl"
    return {r["qid"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def main() -> int:
    qs = {}
    for s, f in DATA.items():
        qs[s] = {q["id"]: q for q in json.loads((ROOT / "data" / f"{f}.json").read_text(encoding="utf-8"))["questions"]}
    out, L = {}, ["# XiYan 7B: final configuration against the baselines", "",
                  "Single runs, greedy decoding. Intervals are Wilson 95%. Declines: a question that should be declined counts when the reply is the right kind of decline "
                  "(`-- UNANSWERABLE` or `-- CLARIFY`). Wrongly refused: an answerable question that got a decline. Latency is mean seconds per question (LM Studio on a 4 GB GPU for the local rows; the 3B row was timed on a different server and is not comparable).", ""]
    plain = {s: jl(SYSTEMS["XiYan 7B Q4_K_M, plain prompt"][s]) for s in DATA}
    for s in DATA:
        ans = [i for i, q in qs[s].items() if q["expected"] == "answer"]
        dec = [i for i, q in qs[s].items() if q["expected"] != "answer"]
        L += [f"## {s} ({len(ans)} answerable, {len(dec)} to decline)", "",
              "| System | Answerable correct | 95% interval | Declined correctly | Wrongly refused | Wrongly answered | vs XiYan plain (gains, losses, p) | Mean s |", "|---|---|---|---|---|---|---|---|"]
        for name, labels in SYSTEMS.items():
            try:
                r = jl(labels[s])
            except FileNotFoundError:
                continue
            k = sum(r[i]["passed"] for i in ans if i in r)
            n = len([i for i in ans if i in r])
            lo, hi = wilson(k, n) if n else (0, 0)
            d = sum(r[i]["passed"] for i in dec if i in r)
            wr = sum(1 for i in ans if i in r and r[i]["kind"] in ("refusal", "clarify"))
            wa = sum(1 for i in dec if i in r and r[i]["kind"] == "sql")
            g = sum(1 for i in qs[s] if i in r and i in plain[s] and r[i]["passed"] and not plain[s][i]["passed"])
            l = sum(1 for i in qs[s] if i in r and i in plain[s] and plain[s][i]["passed"] and not r[i]["passed"])
            lat = sum(x["latency_s"] for x in r.values()) / len(r)
            cmp = "reference" if labels is SYSTEMS["XiYan 7B Q4_K_M, plain prompt"] else f"{g}, {l}, {sign_p(g, l):.2f}"
            L.append(f"| {name} | {k} of {n} ({k / n:.1%}) | {lo:.1%} to {hi:.1%} | {d} of {len(dec)} | {wr} | {wa} | {cmp} | {lat:.1f} |")
            out[f"{name} / {s}"] = {"correct": k, "n": n, "declined": d, "should_decline": len(dec), "wrongly_refused": wr, "wrongly_answered": wa, "mean_s": round(lat, 2)}
        L.append("")
    (ROOT / "docs" / "results" / "xiyan").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "results" / "xiyan" / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "docs" / "results" / "xiyan" / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
