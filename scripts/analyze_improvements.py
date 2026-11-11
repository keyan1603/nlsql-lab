"""Compare every improvement configuration with the plain-prompt baseline on the same questions.

    python scripts/analyze_improvements.py [--set hardall|core]

Reads runs/imp-<tag>-<set>.jsonl (the stress set is two halves, hard and hard2, pooled to 126 questions; the core set is one file). The
baseline is the Q4_K_M run of the plain prompt. For each configuration: accuracy with a Wilson 95 percent interval, SQL errors, the
number of model calls and mean seconds per question (the price of the technique), and the paired comparison with the baseline (questions
gained, questions lost, exact sign test). Writes docs/results/improvements_<set>.md.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyze_sweep import sign_test, wilson                      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
OUT = ROOT / "docs" / "results"
ANS = ("correct", "wrong_result", "sql_error", "unsafe", "timeout", "no_sql", "wrongly_refused")
NAMES = {"base": "Plain prompt (baseline)", "mschema": "M-Schema layout with example values", "prune5": "Show only 5 likely tables",
         "fs3": "3 worked examples", "retry2": "Retry on database error (up to 2)", "retry2e": "Retry on error or empty result (up to 2)",
         "p5r2": "Stack: 5 tables + retry on error", "p5r2v5": "Stack + vote over 5 candidates"}


def load(path: Path) -> dict:
    return {r["qid"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def parts(tag: str, which: str) -> list[Path]:
    if which == "core":
        return [RUNS / ("xiyan7b-q4km.jsonl" if tag == "base" else f"imp-{tag}-core.jsonl")]
    halves = ("hard", "hard2")
    return [RUNS / (f"xiyan7b-q4km-{h}.jsonl" if tag == "base" else f"imp-{tag}-{h}.jsonl") for h in halves]


def collect(tag: str, which: str) -> dict | None:
    files = parts(tag, which)
    if not all(f.exists() for f in files):
        return None
    merged: dict = {}
    for f in files:
        merged.update(load(f))
    return merged


def main() -> int:
    which = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "hardall"
    tags = ["base"] + sorted({p.name.split("-")[1] for p in RUNS.glob("imp-*.jsonl")} - {"base"}, key=lambda t: list(NAMES).index(t) if t in NAMES else 99)
    data = {t: collect(t, which) for t in tags}
    data = {t: d for t, d in data.items() if d}
    base = data["base"]
    qids = [q for q, r in base.items() if r["outcome"] in ANS]
    lines = [f"# Improvement round on the {'stress' if which == 'hardall' else 'core'} set, XiYanSQL 7B at Q4_K_M", "",
             "Each technique alone, against the plain prompt, on the same questions. Intervals are Wilson 95 percent. Gains and losses are questions "
             "the configuration got right that the baseline missed, and the reverse; p is the exact two-sided sign test on those. "
             "A configuration that has not finished all its questions is marked incomplete and left out of the comparison.", "",
             "| Configuration | Correct | Accuracy | 95% interval | SQL errors | Model calls | Mean s/question | Gains | Losses | p |", "|---|---|---|---|---|---|---|---|---|---|"]
    for tag, recs in data.items():
        scored = [q for q in qids if q in recs]
        if len(scored) < len(qids):
            lines.append(f"| {NAMES.get(tag, tag)} | incomplete ({len(scored)}/{len(qids)}) | | | | | | | | |")
            continue
        ok = sum(recs[q]["outcome"] == "correct" for q in scored)
        lo, hi = wilson(ok, len(scored))
        gains = sum(recs[q]["outcome"] == "correct" and base[q]["outcome"] != "correct" for q in scored)
        losses = sum(recs[q]["outcome"] != "correct" and base[q]["outcome"] == "correct" for q in scored)
        errors = sum(recs[q]["outcome"] == "sql_error" for q in scored)
        calls = sum((recs[q].get("pipeline") or {}).get("calls", 1) for q in scored)
        lat = sum(recs[q]["latency_s"] for q in scored) / len(scored)
        lines.append(f"| {NAMES.get(tag, tag)} | {ok}/{len(scored)} | {ok / len(scored) * 100:.1f}% | {lo * 100:.0f} to {hi * 100:.0f}% | {errors} | {calls} | {lat:.1f} | "
                     + ("ref | ref | ref |" if tag == "base" else f"{gains} | {losses} | {sign_test(gains, losses):.3f} |"))
    OUT.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    (OUT / f"improvements_{which}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
