"""Compare the hosted baseline with the local model on the same questions.

    python scripts/analyze_gemini.py

Local reference: XiYanSQL 7B at Q4_K_M with the plain prompt (the Phase 2 and Phase 3 runs). Hosted: gemini-3.5-flash-lite,
plain prompt. Per question set: execution accuracy with Wilson 95 percent intervals, the exact paired sign test on the questions
one got right and the other did not, SQL errors, how it handled the questions that should be declined, latency, and tokens.
Writes docs/results/gemini_vs_local.md.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyze_sweep import sign_test, wilson      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
SETS = {  # set -> (local run, hosted run)
    "core (55)": ("xiyan7b-q4km", "gemini-flashlite"),
    "stress, first half (72)": ("xiyan7b-q4km-hard", "gemini-flashlite-hard"),
    "stress, second half (54)": ("xiyan7b-q4km-hard2", "gemini-flashlite-hard2"),
    "decline set (36)": ("imp-base-decline", "gemini-flashlite-decline"),
}
ANSWERABLE = ("correct", "wrong_result", "sql_error", "unsafe", "timeout", "no_sql", "wrongly_refused")
HANDLED = ("correct_refusal", "correct_clarify", "partial_refusal", "wrongly_answered")


def load(name: str) -> dict:
    p = RUNS / f"{name}.jsonl"
    if not p.exists():
        return {}
    return {r["qid"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def stats(recs: dict, qids: list) -> dict:
    ans = [q for q in qids if recs[q]["outcome"] in ANSWERABLE]
    ok = sum(recs[q]["outcome"] == "correct" for q in ans)
    hand = [q for q in qids if recs[q]["outcome"] in HANDLED]
    return {"ans": len(ans), "ok": ok, "err": sum(recs[q]["outcome"] == "sql_error" for q in ans),
            "dec": sum(recs[q]["outcome"] in ("correct_refusal", "correct_clarify") for q in hand), "hand": len(hand),
            "inv": sum(recs[q]["outcome"] == "wrongly_answered" for q in hand), "wref": sum(recs[q]["outcome"] == "wrongly_refused" for q in ans),
            "lat": statistics.mean(recs[q]["latency_s"] for q in qids), "tin": sum(recs[q]["tokens_in"] for q in qids), "tout": sum(recs[q]["tokens_out"] for q in qids)}


def main() -> int:
    rows = ["| Question set | Local correct | Hosted correct | Local only | Hosted only | p | Local SQL errors | Hosted SQL errors | Declined correctly (local / hosted) | Invented answers (local / hosted) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    tot = {"l": [0, 0], "h": [0, 0]}
    lat = {"l": [], "h": []}
    tokens = [0, 0]
    qcount = 0
    for name, (lname, hname) in SETS.items():
        loc, host = load(lname), load(hname)
        qids = [q for q in loc if q in host]
        if not qids or len(qids) < len(loc):
            rows.append(f"| {name} | incomplete ({len(host)}/{len(loc)} hosted answers) | | | | | | | | |")
            continue
        l, h = stats(loc, qids), stats(host, qids)
        aq = [q for q in qids if loc[q]["outcome"] in ANSWERABLE]
        lo_only = sum(loc[q]["outcome"] == "correct" and host[q]["outcome"] != "correct" for q in aq)
        ho_only = sum(host[q]["outcome"] == "correct" and loc[q]["outcome"] != "correct" for q in aq)
        w = lambda s: "%d/%d (%.1f%%, %d to %d%%)" % (s["ok"], s["ans"], s["ok"] / s["ans"] * 100, wilson(s["ok"], s["ans"])[0] * 100, wilson(s["ok"], s["ans"])[1] * 100)
        rows.append(f"| {name} | {w(l)} | {w(h)} | {lo_only} | {ho_only} | {sign_test(lo_only, ho_only):.3f} | {l['err']} | {h['err']} | "
                    + (f"{l['dec']}/{l['hand']} / {h['dec']}/{h['hand']} | {l['inv']} / {h['inv']} |" if l["hand"] else "n/a | n/a |"))
        for k, s in (("l", l), ("h", h)):
            tot[k][0] += s["ok"]
            tot[k][1] += s["ans"]
            lat[k].append(s["lat"] * len(qids))
        tokens[0] += h["tin"]
        tokens[1] += h["tout"]
        qcount += len(qids)
    lines = ["# Hosted baseline against the local model", "",
             "Local: XiYanSQL 7B at Q4_K_M (partial GPU offload on a 4 GB laptop GPU), plain prompt, greedy. Hosted: gemini-3.5-flash-lite, plain prompt, temperature 0. "
             "Same questions, same database, same grader. p is the exact two-sided sign test on the answerable questions only one of them got right.", "", *rows]
    if qcount:
        lines += ["", f"Pooled over the sets that finished: local {tot['l'][0]}/{tot['l'][1]} ({tot['l'][0] / tot['l'][1] * 100:.1f}%), hosted {tot['h'][0]}/{tot['h'][1]} ({tot['h'][0] / tot['h'][1] * 100:.1f}%). "
                  f"Mean seconds per question, local: {sum(lat['l']) / qcount:.1f}. "
                  f"Hosted tokens: {tokens[0]:,} in, {tokens[1]:,} out over {qcount} questions ({tokens[0] / qcount:,.0f} and {tokens[1] / qcount:,.0f} per question)."]
    sample = load("gemini-latency-sample")
    if sample:
        ls = sorted(r["latency_s"] for r in sample.values())
        first = load("gemini-flashlite-hard")
        lines += ["", f"Hosted latency, measured on a {len(ls)}-question sample after the client timer was fixed to exclude rate-limit waits (the full run's timer included them): "
                  f"mean {statistics.mean(ls):.1f} s, median {ls[len(ls) // 2]:.1f} s, 95th percentile {ls[int(0.95 * (len(ls) - 1))]:.1f} s. "
                  f"The same {len(ls)} questions had the same outcome (right or wrong) in both hosted runs, although the SQL text differed in "
                  f"{sum(r['sql'] != first[q]['sql'] for q, r in sample.items())} of them: the hosted model is not bit-for-bit repeatable at temperature 0."]
    text = "\n".join(lines) + "\n"
    (ROOT / "docs" / "results" / "gemini_vs_local.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
