"""Does disagreement between two LOCAL models flag the answers that need the frontier model? (from saved answers; reads the database)

    python scripts/agreement_router.py [--gate tuned6r2] [--sql xiyan7b-final] [--sets core,hard,hard2]

Idea: the tuned 3B and the 7B were trained differently and read the question differently. Run both SQL queries on the read-only
database and compare the result sets with the grader's own comparison. If they agree, the answer is very likely right; if they
disagree, at least one is wrong, so escalate. This needs no labels and no extra model call beyond the two local calls the gate
design already makes, and it runs inside the secure boundary. Writes docs/results/agreement_router.md and .json.

Strategy order (same as scripts/gate_eval.py): 3B decline gate; then rules (optional); then agreement check; then the usual
post-checks (error, empty result, invented value) on the 7B answer.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cost_model import ASSUMPTIONS, usd                                  # noqa: E402
from nlsql.db import connect, run_query                                  # noqa: E402
from nlsql.grader import compare_results                                 # noqa: E402
from nlsql.invented import invented_values                               # noqa: E402
from nlsql.router import FRONTIER, route                                 # noqa: E402
from route_eval import SETS, jl, sign_p, status_of, wilson               # noqa: E402


def arg(name: str, default: str) -> str:
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a else default


def rows_of(conn, sql):
    """Result rows of a query on the read-only connection, or None if it cannot run."""
    try:
        return run_query(conn, sql).rows
    except Exception:
        return None


def main() -> int:
    gate_run, sql_run, hosted_run = arg("--gate", "tuned6r2"), arg("--sql", "xiyan7b-final"), "gemini-flashlite"
    wanted = arg("--sets", "core,hard,hard2").split(",")
    power = json.loads((ROOT / "docs" / "results" / "power_measurement.json").read_text(encoding="utf-8"))
    watts = power["load_w_mean"] + ASSUMPTIONS["cpu_and_system_w"][0]
    kwh = ASSUMPTIONS["usd_per_kwh"][0]
    sec_cost = lambda s: watts * s / 3600 / 1000 * kwh
    hcost = lambda x: usd(x["h"]["tokens_in"], x["h"]["tokens_out"], "Standard")
    conn = connect("reader")
    rows = []
    for s in wanted:
        hs, qf = SETS[s]
        d = json.loads((ROOT / "data" / f"{qf}.json").read_text(encoding="utf-8"))
        qs = {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}
        g, x, h = jl(ROOT / "runs" / f"{gate_run}-{s}.jsonl"), jl(ROOT / "runs" / f"{sql_run}-{s}.jsonl"), jl(ROOT / "runs" / f"{hosted_run}{hs}.jsonl")
        for qid, q in qs.items():
            if qid in g and qid in x and qid in h:
                r = {"set": s, "qid": qid, "question": q["question"], "g": g[qid], "x": x[qid], "h": h[qid], "agree": None}
                # agreement is only defined when both models produced SQL that runs
                if g[qid]["kind"] == "sql" and x[qid]["kind"] == "sql":
                    a, b = rows_of(conn, g[qid]["sql"] or ""), rows_of(conn, x[qid]["sql"] or "")
                    if a is not None and b is not None:
                        r["agree"] = compare_results(a, b, order_matters=False, tol=0.0) is not None   # None means the result sets differ
                rows.append(r)
    n = len(rows)
    base = [r["h"]["passed"] for r in rows]
    sql_rows = [r for r in rows if r["agree"] is not None]
    L = ["# Agreement between two local models as a routing signal", "",
         f"3B `{gate_run}` and 7B `{sql_run}`; both SQL queries were run on the read-only database and their result sets compared with the grader's comparison (order-insensitive, exact). "
         f"Hosted reference `{hosted_run}`. Pool: {', '.join(wanted)} ({n} questions). Single runs, saved answers.", ""]
    ag, dis = [r for r in sql_rows if r["agree"]], [r for r in sql_rows if not r["agree"]]
    L += ["| 7B answer when the two models... | Questions | 7B correct | Share correct |", "|---|---|---|---|",
          f"| agree | {len(ag)} | {sum(1 for r in ag if r['x']['passed'])} | {sum(1 for r in ag if r['x']['passed']) / max(len(ag), 1):.0%} |",
          f"| disagree | {len(dis)} | {sum(1 for r in dis if r['x']['passed'])} | {sum(1 for r in dis if r['x']['passed']) / max(len(dis), 1):.0%} |",
          f"| (one failed to produce SQL that runs, or one declined) | {n - len(sql_rows)} | {sum(1 for r in rows if r['agree'] is None and r['x']['passed'])} | |", ""]

    def pipeline(r, use_rules, use_agree):
        gc = sec_cost(r["g"]["latency_s"])
        if r["g"]["kind"] != "sql":
            return r["g"]["passed"], gc
        if use_rules and route(r["question"], 1).target == FRONTIER:
            return r["h"]["passed"], gc + hcost(r)
        c = gc + sec_cost(r["x"]["latency_s"])
        bad = status_of(r["x"]) in ("error", "empty") or (r["x"]["kind"] == "sql" and invented_values(r["question"], r["x"].get("sql") or ""))
        if use_agree and r["agree"] is False:
            bad = True
        if bad:
            return r["h"]["passed"], c + hcost(r)
        return r["x"]["passed"], c

    L += ["| Strategy (all start with the 3B decline gate) | Sent to hosted | Correct | Accuracy (95% interval) | Cost per 1,000 | vs all hosted, sign test p |", "|---|---|---|---|---|---|"]
    out = {}
    for name, ur, ua in (("7B with error, empty and invented-value escalation", False, False),
                         ("... plus escalate when the 3B and 7B disagree", False, True),
                         ("... plus rules 1+ (router first)", True, False),
                         ("... plus rules 1+ and disagreement", True, True)):
        res = [pipeline(r, ur, ua) for r in rows]
        k = sum(1 for p, _ in res if p)
        sent = sum(1 for r, (_, c) in zip(rows, res) if c >= hcost(r) * 0.999)
        lo, hi = wilson(k, n)
        cost = sum(c for _, c in res) / n * 1000
        up = sum(1 for (p, _), b in zip(res, base) if p and not b)
        dn = sum(1 for (p, _), b in zip(res, base) if b and not p)
        L.append(f"| {name} | {sent} of {n} ({sent / n:.0%}) | {k} of {n} | {k / n:.1%} ({lo:.1%} to {hi:.1%}) | ${cost:.2f} | {sign_p(up, dn):.3f} ({up} up, {dn} down) |")
        out[name] = {"sent": sent, "correct": k, "n": n, "usd_per_1000": round(cost, 3)}
    L.append("")
    (ROOT / "docs" / "results" / "agreement_router.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "docs" / "results" / "agreement_router.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
