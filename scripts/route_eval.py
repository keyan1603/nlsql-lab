"""Score routing strategies from runs that already exist (no model is called).

    python scripts/route_eval.py

Every question was answered by both the local tuned model (with up to two repair attempts) and the hosted model. A routing strategy
only decides which of the two answers is used, so its accuracy and cost can be read from those saved answers.
MEASURED: pass/fail of each answer, the hosted model's tokens, the local model's seconds. PUBLISHED: hosted prices (scripts/cost_model.py).
ASSUMED: electricity price and the laptop's non-GPU power (scripts/cost_model.py). The local seconds come from the Hugging Face scoring
server, which is slower than LM Studio, so the local cost here is an upper bound; it is tiny either way.
Also checks the rules on the training questions (grouped by the technique each was generated for), a check that uses no test result.
Writes docs/results/routing.md and routing.json.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cost_model import ASSUMPTIONS, usd                      # noqa: E402
from nlsql.invented import invented_values                   # noqa: E402
from nlsql.router import FRONTIER, LOCAL, escalate, families_of, route   # noqa: E402

LOCAL_RUN, HOSTED_RUN = "tuned6r2", "gemini-flashlite"   # LOCAL_RUN is overridden by --local-run
SETS = {"core": ("", "questions"), "hard": ("-hard", "questions_hard"), "hard2": ("-hard2", "questions_hard2"), "decline": ("-decline", "questions_decline"), "heldout": ("-heldout", "questions_heldout")}


def jl(path: Path) -> dict:
    return {r["qid"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def sign_p(gains: int, losses: int) -> float:
    n = gains + losses
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(gains, losses) + 1)) / 2 ** n)


def status_of(r: dict) -> str:
    if r["outcome"] == "sql_error":
        return "error"
    return "empty" if "got 0 rows" in (r.get("detail") or "") else ("n/a" if r["kind"] != "sql" else "ok")


def load_all() -> list[dict]:
    rows = []
    for s, (hs, qf) in ((k, v) for k, v in SETS.items() if k != "heldout"):     # heldout is a separate pool, never part of the 181
        d = json.loads((ROOT / "data" / f"{qf}.json").read_text(encoding="utf-8"))
        qs = {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}
        loc, hos = jl(ROOT / "runs" / f"{LOCAL_RUN}-{s}.jsonl"), jl(ROOT / "runs" / f"{HOSTED_RUN}{hs}.jsonl")
        for qid, q in qs.items():
            if qid in loc and qid in hos:
                rows.append({"set": s, "qid": qid, "question": q["question"], "category": q.get("category", ""), "local": loc[qid], "hosted": hos[qid]})
    return rows


HELDOUT = SETS["heldout"]     # a separate pool: written after the rules were frozen, never merged into the 181


def heldout_splits(rows: list[dict]) -> dict:
    """The held-out pool and its parts by question id prefix: routine (RT), complex (HO), should-decline (HU unanswerable, HM ambiguous), answerable controls (HK)."""
    part = lambda *pre: [r for r in rows if r["qid"].startswith(pre)]
    return {f"held-out set ({len(rows)} questions)": rows,
            f"held-out, routine ({len(part('RT'))})": part("RT"), f"held-out, complex ({len(part('HO'))})": part("HO"),
            f"held-out, should decline ({len(part('HU', 'HM'))})": part("HU", "HM"), f"held-out, answerable controls ({len(part('HK'))})": part("HK")}


def load_heldout(local_run: str, hosted_run: str = HOSTED_RUN) -> list[dict]:
    """Rows for the held-out set, or [] when the local or hosted run for it does not exist yet."""
    hs, qf = HELDOUT
    lp, hp = ROOT / "runs" / f"{local_run}-heldout.jsonl", ROOT / "runs" / f"{hosted_run}{hs}.jsonl"
    if not (lp.exists() and hp.exists()):
        return []
    d = json.loads((ROOT / "data" / f"{qf}.json").read_text(encoding="utf-8"))
    qs = {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}
    loc, hos = jl(lp), jl(hp)
    return [{"set": "heldout", "qid": qid, "question": q["question"], "category": q.get("category", ""), "local": loc[qid], "hosted": hos[qid]}
            for qid, q in qs.items() if qid in loc and qid in hos]


def main() -> int:
    global LOCAL_RUN
    args = sys.argv[1:]
    if "--local-run" in args:
        LOCAL_RUN = args[args.index("--local-run") + 1]
    suffix = "" if LOCAL_RUN == "tuned6r2" else "_" + {"tuned4r2": "run4"}.get(LOCAL_RUN, LOCAL_RUN)
    power = json.loads((ROOT / "docs" / "results" / "power_measurement.json").read_text(encoding="utf-8"))
    kwh = ASSUMPTIONS["usd_per_kwh"][0]
    watts = power["load_w_mean"] + ASSUMPTIONS["cpu_and_system_w"][0]
    rows = load_all()
    held = load_heldout(LOCAL_RUN)
    for r in rows + held:
        r["f_cost"] = usd(r["hosted"]["tokens_in"], r["hosted"]["tokens_out"], "Standard")
        r["l_cost"] = watts * r["local"]["latency_s"] / 3600 / 1000 * kwh
        r["why"] = escalate(r["local"]["kind"], status_of(r["local"]))
        r["inv"] = bool(r["local"]["kind"] == "sql" and invented_values(r["question"], r["local"].get("sql") or ""))

    def strategy(first, up):
        """first: question -> 'local'|'frontier'; up: also escalate a failed local answer."""
        def run(r):
            if first(r) == FRONTIER:
                return r["hosted"]["passed"], r["f_cost"]
            if up(r):
                return r["hosted"]["passed"], r["l_cost"] + r["f_cost"]
            return r["local"]["passed"], r["l_cost"]
        return run

    never, errs = (lambda r: False), (lambda r: r["why"] is not None)
    errs_only = lambda r: r["why"] is not None and not r["why"].startswith("the local model declined")
    errs_inv = lambda r: r["why"] is not None or r["inv"]
    all_local, all_front = (lambda r: LOCAL), (lambda r: FRONTIER)
    rule = lambda t: (lambda r: route(r["question"], t).target)
    S = {
        f"All local ({LOCAL_RUN})": strategy(all_local, never),
        "All hosted (gemini-3.5-flash-lite)": strategy(all_front, never),
        "Rules, 1+ family": strategy(rule(1), never),
        "Rules, 2+ families": strategy(rule(2), never),
        "Local, escalate on error or empty": strategy(all_local, errs_only),
        "Local, escalate on error, empty or decline": strategy(all_local, errs),
        "Rules 1+, plus escalate on error, empty or decline": strategy(rule(1), errs),
        "Rules 2+, plus escalate on error, empty or decline": strategy(rule(2), errs),
        "Local, escalate on error, empty, decline or invented value": strategy(all_local, errs_inv),
        "Rules 1+, plus escalate on error, empty, decline or invented value": strategy(rule(1), errs_inv),
    }
    pools = {"core + stress (181 questions)": [r for r in rows if r["set"] != "decline"], "decline set (36 questions)": [r for r in rows if r["set"] == "decline"]}
    if held:
        pools.update(heldout_splits(held))
    out = {"strategies": {}, "note": "accuracy = share of questions whose used answer passed the grader; cost per 1,000 questions at hosted Standard prices"}
    L = ["# Routing: which model answers", "",
         f"Measured on the saved answers of the local model run `{LOCAL_RUN}` and the hosted gemini-3.5-flash-lite (`{HOSTED_RUN}`), "
         "same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).", ""]
    for pname, pool in pools.items():
        n = len(pool)
        L += [f"## {pname}", "", "| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |", "|---|---|---|---|---|---|"]
        base = [S["All hosted (gemini-3.5-flash-lite)"](r)[0] for r in pool]
        out["strategies"][pname] = {}
        for name, fn in S.items():
            res = [fn(r) for r in pool]
            k = sum(1 for p, _ in res if p)
            lo, hi = wilson(k, n)
            sent = sum(1 for r, (_, c) in zip(pool, res) if c >= r["f_cost"] * 0.999)
            cost = sum(c for _, c in res) / n * 1000
            gains = sum(1 for (p, _), b in zip(res, base) if p and not b)
            losses = sum(1 for (p, _), b in zip(res, base) if b and not p)
            pv = "" if name.startswith("All hosted") else f"{sign_p(gains, losses):.3f} ({gains} up, {losses} down)"
            L.append(f"| {name} | {k} of {n} | {k / n:.1%} ({lo:.1%} to {hi:.1%}) | {sent / n:.0%} | ${cost:.2f} | {pv} |")
            out["strategies"][pname][name] = {"correct": k, "n": n, "sent_to_hosted": sent, "usd_per_1000": round(cost, 3)}
        orc = sum(1 for r in pool if r["local"]["passed"] or r["hosted"]["passed"])
        L += [f"| Oracle: whichever model was right (upper bound, not achievable) | {orc} of {n} | {orc / n:.1%} | | | |", ""]
    # how well do the rules pick out the questions the local model gets wrong?
    ans = pools["core + stress (181 questions)"]
    wrong = [r for r in ans if not r["local"]["passed"]]
    L += ["## How well the rules find the questions the local model gets wrong", "",
          "Among the core and stress questions the local model failed, and the questions where the hosted model was right and the local one wrong.", "",
          "| Threshold | Routed to hosted | Of those, local was wrong | Local-wrong questions caught | Local-wrong questions missed |", "|---|---|---|---|---|"]
    for t in (1, 2):
        routed = [r for r in ans if route(r["question"], t).target == FRONTIER]
        hit = [r for r in routed if not r["local"]["passed"]]
        L.append(f"| {t}+ families | {len(routed)} of {len(ans)} | {len(hit)} ({len(hit) / max(len(routed), 1):.0%}) | {len(hit)} of {len(wrong)} ({len(hit) / len(wrong):.0%}) | {len(wrong) - len(hit)} |")
    L.append("")
    # the rules on the training questions: share routed per technique (uses no test result)
    cand = {c["id"]: c for c in (json.loads(l) for l in (ROOT / "train" / "data" / "candidates.jsonl").read_text(encoding="utf-8").splitlines())}
    tr = [json.loads(l) for l in (ROOT / "train" / "data" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    by: dict = {}
    for row in tr:
        c = cand.get(row["id"])
        if c:
            by.setdefault(c["technique"], []).append(route(c["question"], 1).target == FRONTIER)
    L += ["## The rules on the training questions", "", "Share of training questions the 1+ rule would send to the hosted model, by the technique each was generated for. "
          "This check uses no test result.", "", "| Technique | Questions | Routed to hosted |", "|---|---|---|"]
    for t, v in sorted(by.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        L.append(f"| {t} | {len(v)} | {sum(v) / len(v):.0%} |")
    out["training_share_routed"] = {t: round(sum(v) / len(v), 3) for t, v in by.items()}
    L += ["", "## Misses and false alarms", ""]
    miss = [r for r in ans if not r["local"]["passed"] and r["hosted"]["passed"] and route(r["question"], 1).target == LOCAL]
    L += [f"Hosted right, local wrong, and the rules kept it local ({len(miss)}):", ""] + [f"- {r['qid']} ({r['category']}): {r['question']}" for r in miss[:12]]
    out["missed_ids"] = [r["qid"] for r in miss]
    if held:
        wh = [r for r in held if r["local"]["kind"] == "sql" or r["local"]["passed"] is not None]
        L += ["", "## Held-out set: how well the rules find the local failures", "",
              "| Threshold | Routed to hosted | Local wrong among them (precision) | Local-wrong questions caught (recall) |", "|---|---|---|---|"]
        out["heldout_rules"] = {}
        wrong_h = [r for r in wh if not r["local"]["passed"]]
        for t in (1, 2):
            routed = [r for r in wh if route(r["question"], t).target == FRONTIER]
            hit = [r for r in routed if not r["local"]["passed"]]
            L.append(f"| {t}+ families | {len(routed)} of {len(wh)} | {len(hit)} of {len(routed)} | {len(hit)} of {len(wrong_h)} |")
            out["heldout_rules"][f"{t}+"] = {"routed": len(routed), "local_wrong_in_routed": len(hit), "local_wrong_total": len(wrong_h), "n": len(wh)}
    (ROOT / "docs" / "results" / f"routing{suffix}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "docs" / "results" / f"routing{suffix}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
