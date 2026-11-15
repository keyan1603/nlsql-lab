"""Summaries and the markdown report for scripts/run_hybrid.py. Every number in docs/results/hybrid.md is computed here from the
saved run files (runs/hybrid-*.jsonl, *.egress.jsonl) and docs/results/gate.json (the saved-answer simulation); nothing is typed in.
Hand-written interpretation lives in docs/results/hybrid_notes.md and is appended unchanged.

    python scripts/run_hybrid.py --report      # regenerate docs/results/hybrid.md from whatever is in runs/
"""

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, DOCS = ROOT / "runs", ROOT / "docs" / "results"

POOLS = {"core + stress, answerable (181 questions)": ("core", "hard", "hard2"), "decline set (36 questions: 12 controls, 24 should decline)": ("decline",),
         "held-out set": ("heldout",)}
GATE_KEY = {"core + stress, answerable (181 questions)": "core + stress, answerable (181 questions)",
            "decline set (36 questions: 12 controls, 24 should decline)": "decline set (36 questions: 12 controls, 24 should decline)"}
SIM_ROWS = {"gate_first": "3B gate first, then rules 1+, then 7B with escalation", "rules_first": "Rules 1+ first, then 3B gate, then 7B with escalation"}
NO_ESC_ROW = "3B decline gate + 7B SQL"
HOSTED_ROW = "All hosted (gemini-3.5-flash-lite)"


def _mean(xs):
    return round(statistics.mean(xs), 2) if xs else None


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    recs = [r["rec"] for r in rows]
    passed = sum(r["verdict"]["passed"] for r in rows)
    withheld = [r for r in rows if r["rec"]["withheld"]]
    answered = [r for r in rows if not r["rec"]["withheld"]]
    ans_q = [r for r in rows if r["expected"] == "answer"]
    dec_q = [r for r in rows if r["expected"] != "answer"]
    esc = [r for r in recs if r["escalation_source"]]
    by_src = {}
    for r in esc:
        by_src[r["escalation_source"]] = by_src.get(r["escalation_source"], 0) + 1
    totals = [r["latency_s"]["total"] for r in recs]
    tok_h = [r["tokens"].get("hosted", {"in": 0, "out": 0}) for r in recs if "hosted" in r["tiers"]]
    cost = {k: sum(r["cost_usd"].get(k, 0) for r in recs) / n * 1000 for k in ("local", "hosted", "total")}
    lat = {t: _mean([r["latency_s"][t] for r in recs if t in r["latency_s"]]) for t in ("gate", "sql", "hosted")}
    cand_w = [r["candidate"] for r in withheld if r["candidate"]]
    return {
        "n": n, "passed": passed, "accuracy": round(passed / n, 4),
        "answerable": len(ans_q), "answerable_correct": sum(r["verdict"]["passed"] for r in ans_q),
        "should_decline": len(dec_q), "declined_correctly": sum(r["verdict"]["passed"] for r in dec_q),
        "answered": len(answered), "passed_of_answered": sum(r["verdict"]["passed"] for r in answered),
        "withheld": len(withheld), "withheld_share": round(len(withheld) / n, 4),
        "answered_by": {t: sum(1 for r in recs if r["answered_by"] == t) for t in ("gate", "sql", "hosted", "withheld")},
        "escalated": len(esc), "escalation_share": round(len(esc) / n, 4), "escalation_by_source": by_src,
        "hosted_calls": sum(1 for r in recs if "hosted" in r["tiers"]), "left_boundary": sum(1 for r in recs if r["left_boundary"]),
        "hosted_tokens_in": sum(t["in"] for t in tok_h), "hosted_tokens_out": sum(t["out"] for t in tok_h),
        "tier_errors": sum(1 for r in rows if r["verdict"]["outcome"] == "tier_error"),
        "usd_per_1000": {k: round(v, 3) for k, v in cost.items()},
        "latency_mean_s": {"total": _mean(totals), **lat}, "latency_p95_s": round(sorted(totals)[int(0.95 * (n - 1))], 2),
        "withheld_candidate_passed": sum(c["passed"] for c in cand_w), "withheld_candidates": len(cand_w),
        "gate_declines": sum(1 for r in recs if r["gate_decision"] in ("refusal", "clarify")),
        "gate_errors": sum(1 for r in recs if r["gate_decision"] == "error"),
    }


def summarize_run(label, policy, order, saved: dict, stopped, sets, models) -> dict:
    rows = list(saved.values())
    per_set = {s: aggregate([r for r in rows if r["set"] == s]) for s in sets}
    pools = {}
    for name, members in POOLS.items():
        sel = [r for r in rows if r["set"] in members]
        if sel:
            pools[name] = aggregate(sel)
    return {"label": label, "policy": policy, "order": order, "models": models, "stopped": stopped, "per_set": per_set, "pools": pools}


def _pct(k, n):
    return f"{k / n:.1%}" if n else "n/a"


def _egress_blocks(label: str) -> list[str]:
    p = RUNS / f"hybrid-{label}.egress.jsonl"
    if not p.exists():
        return ["(no egress report on disk)"]
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        rep = json.loads(line)
        out += [f"Invocation {i} ({rep.get('finished', '')}), monitor mode `{rep['mode']}`, MySQL endpoint allowed: `{rep['mysql_endpoint']}`.", ""]
        if rep.get("canary") is not None:
            out += [f"- Canary: a deliberate connection to `192.0.2.1:80` (documentation-range public address) was **{'blocked before any packet was sent' if rep['canary'].get('blocked') else 'NOT blocked (monitor failure)'}**."]
        out += [f"- Connection events recorded (DNS lookups, connects, sends), excluding the canary: {rep['attempts_total']}",
                f"- Blocked in the pipeline run (excluding the canary): {rep['blocked_count']}",
                f"- Destinations that were NOT loopback and were allowed (MySQL endpoint only, when it is not loopback): {len(rep['non_loopback_allowed'])}", "",
                "| Kind | Destination | Port | Events | Verdict |", "|---|---|---|---|---|"]
        for a in rep["allowed"]:
            out.append(f"| {a['kind']} | {a['host']} | {a['port']} | {a['count']} | {'allowed (loopback or MySQL)' if rep['mode'] == 'sealed' else ('loopback' if a['host'] in ('127.0.0.1', '::1', 'localhost') else 'outside the machine (observe mode: recorded, not blocked)')} |")
        for b in rep["blocked"]:
            out.append(f"| {b['kind']} | {b['host']} | {b['port']} | {b['count']} | BLOCKED |")
        out.append("")
    return out


def render() -> str:
    L = ["# Hybrid pipeline, run live", "",
         "Generated by `scripts/hybrid_report.py` from the run files; every number below is computed from saved per-question records. "
         "The method, the settings and what could not be verified are in the sections that follow the tables.", ""]
    gate_sim = json.loads((DOCS / "gate.json").read_text(encoding="utf-8")) if (DOCS / "gate.json").exists() else {}
    for p in sorted(RUNS.glob("hybrid-*.summary.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        L += [f"## Run `{s['label']}`: policy **{s['policy']}**, order `{s['order']}`", "",
              f"Gate `{s['models']['gate']}`, SQL `{s['models']['sql']}`." + (f" **Stopped early: {s['stopped']}**" if s["stopped"] else ""), ""]
        L += ["| Set | Questions | Correct | Accuracy | Withheld by policy | Escalated (rules / post-check) | Hosted calls | left_boundary | USD per 1,000 (local + hosted) | Mean s per question |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        rows = [(f"{k}", v) for k, v in s["per_set"].items() if v["n"]] + [(f"**{k}**", v) for k, v in s["pools"].items()]
        for name, a in rows:
            src = a["escalation_by_source"]
            L.append(f"| {name} | {a['n']} | {a['passed']} | {_pct(a['passed'], a['n'])} | {a['withheld']} ({_pct(a['withheld'], a['n'])}) | "
                     f"{a['escalated']} ({_pct(a['escalated'], a['n'])}; {src.get('rules', 0)} / {src.get('postcheck', 0) + src.get('tier_error', 0)}) | {a['hosted_calls']} | {a['left_boundary']} | "
                     f"${a['usd_per_1000']['total']:.2f} (${a['usd_per_1000']['local']:.2f} + ${a['usd_per_1000']['hosted']:.2f}) | {a['latency_mean_s']['total']} |")
        L.append("")
        L += ["Detail per pool: answerable correct, declines correct, accuracy among answered questions, and how the withheld ones would have fared had the untrusted local answer been used.", "",
              "| Pool | Answerable correct | Declined correctly | Answered / correct among answered | Withheld | Local candidate correct among withheld | Hosted tokens in / out | Mean s: gate / 7B / hosted | p95 s | Tier errors |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for name, a in rows:
            lm = a["latency_mean_s"]
            L.append(f"| {name} | {a['answerable_correct']} of {a['answerable']} | {a['declined_correctly']} of {a['should_decline']} | {a['answered']} / {a['passed_of_answered']} ({_pct(a['passed_of_answered'], a['answered'])}) | "
                     f"{a['withheld']} | {a['withheld_candidate_passed']} of {a['withheld_candidates']} | {a['hosted_tokens_in']:,} / {a['hosted_tokens_out']:,} | {lm['gate'] or 'n/a'} / {lm['sql'] or 'n/a'} / {lm['hosted'] or 'n/a'} | {a['latency_p95_s']} | {a['tier_errors']} |")
        L.append("")
        if s["policy"] == "open":
            sim_row = SIM_ROWS[s["order"]]
            L += [f"Live against the saved-answer simulation (`docs/results/gate.md`; simulated row: {sim_row}).", "",
                  "| Pool | Live correct | Live USD per 1,000 | Simulated correct | Simulated USD per 1,000 | All hosted, simulated (correct, USD per 1,000) |", "|---|---|---|---|---|---|"]
            for name, a in s["pools"].items():
                g = gate_sim.get(GATE_KEY.get(name, ""), {})
                if g and sim_row in g:
                    sim, hs = g[sim_row], g[HOSTED_ROW]
                    L.append(f"| {name} | {a['passed']} of {a['n']} ({_pct(a['passed'], a['n'])}) | ${a['usd_per_1000']['total']:.2f} | {sim['correct']} of {sim['n']} ({_pct(sim['correct'], sim['n'])}) | ${sim['usd_per_1000']:.2f} | {hs['correct']} of {hs['n']}, ${hs['usd_per_1000']:.2f} |")
                else:
                    L.append(f"| {name} | {a['passed']} of {a['n']} ({_pct(a['passed'], a['n'])}) | ${a['usd_per_1000']['total']:.2f} | no saved answers to simulate | | |")
            L.append("")
        elif s["policy"] == "sealed":
            L += [f"For orientation, the saved-answer simulation of the same gate and 7B with no escalation at all (`{NO_ESC_ROW}`) scored:", ""]
            for name in GATE_KEY:
                g = gate_sim.get(name, {}).get(NO_ESC_ROW)
                if g:
                    L.append(f"- {name}: {g['correct']} of {g['n']} ({_pct(g['correct'], g['n'])}). The sealed run additionally withholds every question the rules would send up and every untrusted local answer.")
            L.append("")
        L += ["### Egress evidence", ""] + _egress_blocks(s["label"])
    notes = DOCS / "hybrid_notes.md"
    if notes.exists():
        L += ["", notes.read_text(encoding="utf-8").rstrip(), ""]
    return "\n".join(L) + "\n"


def write_report() -> str:
    text = render()
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "hybrid.md").write_text(text, encoding="utf-8")
    return str(DOCS / "hybrid.md")


if __name__ == "__main__":
    print(write_report())
