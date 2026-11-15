"""Score a decline gate in front of a local SQL model, from saved answers (no model is called).

    python scripts/gate_eval.py [--gate tuned6r2] [--sql xiyan7b-final]

Design: the small tuned model sees every question first. If it declines, the question is declined and the SQL model is never used.
Otherwise the SQL model's saved answer is used (optionally with escalation to the hosted model on error, empty result or an
invented value). MEASURED: pass/fail of each saved answer, latencies, hosted tokens. The two local models were served by different
servers, so seconds are indicative only. Writes docs/results/gate.md and gate.json.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cost_model import ASSUMPTIONS, usd                      # noqa: E402
from nlsql.invented import invented_values                   # noqa: E402
from nlsql.router import FRONTIER, route                    # noqa: E402
from route_eval import HELDOUT, SETS, heldout_splits, jl, sign_p, status_of, wilson   # noqa: E402


def arg(name: str, default: str) -> str:
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a else default


def main() -> int:
    gate_run, sql_run, hosted_run = arg("--gate", "tuned6r2"), arg("--sql", "xiyan7b-final"), "gemini-flashlite"
    power = json.loads((ROOT / "docs" / "results" / "power_measurement.json").read_text(encoding="utf-8"))
    watts = power["load_w_mean"] + ASSUMPTIONS["cpu_and_system_w"][0]
    kwh = ASSUMPTIONS["usd_per_kwh"][0]
    sec_cost = lambda s: watts * s / 3600 / 1000 * kwh
    rows = []
    for s, (hs, qf) in ((k, v) for k, v in SETS.items() if k != "heldout"):     # heldout is its own pool, loaded below
        d = json.loads((ROOT / "data" / f"{qf}.json").read_text(encoding="utf-8"))
        qs = {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}
        g, x, h = jl(ROOT / "runs" / f"{gate_run}-{s}.jsonl"), jl(ROOT / "runs" / f"{sql_run}-{s}.jsonl"), jl(ROOT / "runs" / f"{hosted_run}{hs}.jsonl")
        for qid, q in qs.items():
            if qid in g and qid in x and qid in h:
                rows.append({"set": s, "qid": qid, "question": q["question"], "g": g[qid], "x": x[qid], "h": h[qid]})

    held = []                       # the held-out set is its own pool; it is never merged into the 181
    hs, hq = HELDOUT
    gp, xp, hp = ROOT / "runs" / f"{gate_run}-heldout.jsonl", ROOT / "runs" / f"{sql_run}-heldout.jsonl", ROOT / "runs" / f"{hosted_run}{hs}.jsonl"
    if gp.exists() and xp.exists() and hp.exists():
        d = json.loads((ROOT / "data" / f"{hq}.json").read_text(encoding="utf-8"))
        qs = {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}
        g, x, h = jl(gp), jl(xp), jl(hp)
        held = [{"set": "heldout", "qid": qid, "question": q["question"], "g": g[qid], "x": x[qid], "h": h[qid]} for qid, q in qs.items() if qid in g and qid in x and qid in h]

    def gated(r, escalate):
        gc = sec_cost(r["g"]["latency_s"])
        if r["g"]["kind"] != "sql":
            return r["g"]["passed"], gc
        xc = gc + sec_cost(r["x"]["latency_s"])
        bad = status_of(r["x"]) in ("error", "empty") or (r["x"]["kind"] == "sql" and invented_values(r["question"], r["x"].get("sql") or ""))
        if escalate and bad:
            return r["h"]["passed"], xc + usd(r["h"]["tokens_in"], r["h"]["tokens_out"], "Standard")
        return r["x"]["passed"], xc

    hcost = lambda r: usd(r["h"]["tokens_in"], r["h"]["tokens_out"], "Standard")

    def routed(r, t, gate_first):
        """Rules send reasoning-heavy questions to hosted; the gate declines; the 7B answers the rest (escalating on error, empty or invented value)."""
        if not gate_first and route(r["question"], t).target == FRONTIER:
            return r["h"]["passed"], hcost(r)
        gc = sec_cost(r["g"]["latency_s"])
        if gate_first and r["g"]["kind"] != "sql":
            return r["g"]["passed"], gc
        if gate_first and route(r["question"], t).target == FRONTIER:
            return r["h"]["passed"], gc + hcost(r)
        p, c = gated(r, True)
        return p, c

    S = {
        f"3B alone ({gate_run})": lambda r: (r["g"]["passed"], sec_cost(r["g"]["latency_s"])),
        f"7B alone ({sql_run})": lambda r: (r["x"]["passed"], sec_cost(r["x"]["latency_s"])),
        "3B decline gate + 7B SQL": lambda r: gated(r, False),
        "3B decline gate + 7B SQL, escalate on error, empty or invented value": lambda r: gated(r, True),
        "Rules 1+ first, then 3B gate, then 7B with escalation": lambda r: routed(r, 1, False),
        "3B gate first, then rules 1+, then 7B with escalation": lambda r: routed(r, 1, True),
        "3B gate first, then rules 2+, then 7B with escalation": lambda r: routed(r, 2, True),
        "All hosted (gemini-3.5-flash-lite)": lambda r: (r["h"]["passed"], hcost(r)),
    }
    pools = {"core + stress, answerable (181 questions)": [r for r in rows if r["set"] != "decline" and r["x"]["kind"] is not None],
             "decline set (36 questions: 12 controls, 24 should decline)": [r for r in rows if r["set"] == "decline"]}
    pools["core + stress, answerable (181 questions)"] = [r for r in rows if r["set"] != "decline"]
    if held:
        pools.update(heldout_splits(held))
    out, L = {}, ["# Decline gate in front of a local SQL model", "",
                  f"Gate: `{gate_run}`. SQL model: `{sql_run}`. Hosted reference: `{hosted_run}`. Computed from saved single-run answers; a strategy only chooses which saved answer is used. "
                  "The core set includes 6 should-decline questions, so gate refusals there count as correct.", ""]
    for pname, pool in pools.items():
        n = len(pool)
        L += [f"## {pname}", "", "| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |", "|---|---|---|---|---|"]
        base = [S["All hosted (gemini-3.5-flash-lite)"](r)[0] for r in pool]
        out[pname] = {}
        for name, fn in S.items():
            res = [fn(r) for r in pool]
            k = sum(1 for p, _ in res if p)
            lo, hi = wilson(k, n)
            cost = sum(c for _, c in res) / n * 1000
            up = sum(1 for (p, _), b in zip(res, base) if p and not b)
            dn = sum(1 for (p, _), b in zip(res, base) if b and not p)
            pv = "" if name.startswith("All hosted") else f"{sign_p(up, dn):.3f} ({up} up, {dn} down)"
            L.append(f"| {name} | {k} of {n} | {k / n:.1%} ({lo:.1%} to {hi:.1%}) | ${cost:.2f} | {pv} |")
            out[pname][name] = {"correct": k, "n": n, "usd_per_1000": round(cost, 3)}
        L.append("")
    # gate false refusals on answerable questions
    ans = [r for r in rows if r["set"] != "decline"]
    fr = [r["qid"] for r in ans if r["g"]["kind"] != "sql" and r["x"]["passed"] and r["x"]["kind"] == "sql"]
    dec = [r for r in rows if r["set"] == "decline"]
    ctl = [r for r in dec if r["x"]["kind"] == "sql" and r["g"]["kind"] != "sql" and r["x"]["passed"]]
    L += ["## What the gate costs", "", f"- Answerable core and stress questions the 7B got right but the gate refused: {len(fr)} ({', '.join(fr) or 'none'}).",
          f"- Decline-set controls the 7B got right but the gate refused: {len(ctl)}.", ""]
    suffix = "" if gate_run == "tuned6r2" and sql_run == "xiyan7b-final" else "_" + gate_run + "_" + sql_run
    (ROOT / "docs" / "results" / f"gate{suffix}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "docs" / "results" / f"gate{suffix}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
