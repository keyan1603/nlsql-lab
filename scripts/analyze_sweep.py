"""Turn the quantization sweep runs into the numbers and the chart the post needs.

    python scripts/analyze_sweep.py                 # reads runs/xiyan7b-*.jsonl, writes docs/results/quant_analysis.md and quant_curve.png

For every level and every question set: accuracy with a Wilson 95 percent interval, the paired comparison against the 8-bit reference
(questions it gained and lost, an exact two-sided sign test on the discordant questions, which is McNemar's exact test), and the
per-category scores. Answering one question set twice with a different model is a paired design, so the sign test is the right test:
it asks whether the questions that flipped flipped in one direction more often than chance.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RUNS = ROOT / "runs"
OUT = ROOT / "docs" / "results"
FILE_GB = {"Q2_K": 3.016, "Q3_K_S": 3.492, "Q3_K_M": 3.808, "Q3_K_L": 4.088, "IQ4_XS": 4.250, "Q4_K_S": 4.458, "Q4_K_M": 4.683,
           "Q5_K_S": 5.315, "Q5_K_M": 5.445, "Q6_K": 6.254, "Q8_0": 8.099}
ORDER = sorted(FILE_GB, key=FILE_GB.get)


def label(quant: str, kind: str) -> str:
    return f"xiyan7b-{quant.lower().replace('_', '')}" + ("-hard" if kind == "hard" else "")


def load(path: Path) -> dict:
    return {r["qid"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def sign_test(gains: int, losses: int) -> float:
    """Exact two-sided binomial test of gains against losses under 'a flip is equally likely either way'."""
    n = gains + losses
    if n == 0:
        return 1.0
    k = min(gains, losses)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def answerable(records: dict) -> list[str]:
    return [q for q, r in records.items() if r["outcome"] in ("correct", "wrong_result", "sql_error", "unsafe", "timeout", "no_sql", "wrongly_refused")]


def analyse(kind: str) -> dict | None:
    runs = {}
    for q in ORDER:
        path = RUNS / f"{label(q, kind)}.jsonl"
        if path.exists():
            runs[q] = load(path)
    if "Q8_0" not in runs:
        return None
    ref = runs["Q8_0"]
    qids = answerable(ref)
    table = {}
    for q, r in runs.items():
        scored = [k for k in qids if k in r]
        k_ok = sum(1 for k in scored if r[k]["outcome"] == "correct")
        lo, hi = wilson(k_ok, len(scored))
        gains = [k for k in scored if r[k]["outcome"] == "correct" and ref[k]["outcome"] != "correct"]
        losses = [k for k in scored if r[k]["outcome"] != "correct" and ref[k]["outcome"] == "correct"]
        cats: dict = {}
        for k in scored:
            cats.setdefault(r[k].get("category", ""), [0, 0])
        table[q] = {"correct": k_ok, "n": len(scored), "acc": k_ok / len(scored), "lo": lo, "hi": hi, "gains": gains, "losses": losses,
                    "net": len(gains) - len(losses), "p": sign_test(len(gains), len(losses)), "errors": sum(1 for k in scored if r[k]["outcome"] == "sql_error")}
    return {"kind": kind, "table": table, "ref_correct": table["Q8_0"]["correct"], "n": table["Q8_0"]["n"]}


def categories(kind: str) -> dict:
    from nlsql.config import ROOT as R
    from nlsql.questions import load_questions
    qs = {q.id: q.category for q in load_questions(R / "data" / ("questions_hard.json" if kind == "hard" else "questions.json"))}
    out: dict = {}
    for quant in ORDER:
        path = RUNS / f"{label(quant, kind)}.jsonl"
        if not path.exists():
            continue
        for qid, r in load(path).items():
            if qid in qs and r["outcome"] in ("correct", "wrong_result", "sql_error", "unsafe", "timeout", "no_sql", "wrongly_refused"):
                c = out.setdefault(qs[qid], {}).setdefault(quant, [0, 0])
                c[1] += 1
                c[0] += r["outcome"] == "correct"
    return out


def markdown(results: list[dict]) -> str:
    lines = ["# Quantization against difficulty: XiYanSQL-QwenCoder-7B-2504, eleven levels, two question sets", "",
             "Accuracy is the share of answerable questions whose query returned the right result. Intervals are Wilson 95 percent. "
             "Gains and losses are questions a level got right that Q8_0 got wrong, and the reverse; p is the exact two-sided sign test on those "
             "discordant questions (McNemar's exact test). A small p says the flips went one way more than chance would.", ""]
    for res in results:
        name = "Hard set (72 questions, 22 tables)" if res["kind"] == "hard" else "Core set (49 answerable questions, 11 tables)"
        lines += [f"## {name}", "", "| Level | File GB | Correct | Accuracy | 95% interval | SQL errors | Gains vs Q8_0 | Losses vs Q8_0 | Net | p (sign test) |", "|---|---|---|---|---|---|---|---|---|---|"]
        for q in reversed(ORDER):
            t = res["table"].get(q)
            if not t:
                continue
            lines.append(f"| {q} | {FILE_GB[q]:.2f} | {t['correct']}/{t['n']} | {t['acc'] * 100:.1f}% | {t['lo'] * 100:.0f} to {t['hi'] * 100:.0f}% | {t['errors']} | {len(t['gains'])} | {len(t['losses'])} | {t['net']:+d} | {t['p']:.3f} |")
        lines.append("")
    for kind in ("core", "hard"):
        cats = categories(kind)
        if not cats:
            continue
        lines += [f"## Per category, {kind} set (correct / questions)", "", "| Category | " + " | ".join(q for q in reversed(ORDER)) + " |", "|---|" + "---|" * len(ORDER)]
        for cat in sorted(cats):
            lines.append(f"| {cat} | " + " | ".join(f"{cats[cat][q][0]}/{cats[cat][q][1]}" if q in cats[cat] else "" for q in reversed(ORDER)) + " |")
        lines.append("")
    return "\n".join(lines)


def chart(results: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    colors = {"core": "#2b7bba", "hard": "#c0392b"}
    names = {"core": "Core set (11 tables, 49 questions)", "hard": "Hard set (22 tables, 72 questions)"}
    for res in results:
        xs = [FILE_GB[q] for q in ORDER if q in res["table"]]
        ys = [res["table"][q]["acc"] * 100 for q in ORDER if q in res["table"]]
        lo = [res["table"][q]["lo"] * 100 for q in ORDER if q in res["table"]]
        hi = [res["table"][q]["hi"] * 100 for q in ORDER if q in res["table"]]
        ax.plot(xs, ys, marker="o", color=colors[res["kind"]], label=names[res["kind"]], linewidth=2)
        ax.fill_between(xs, lo, hi, color=colors[res["kind"]], alpha=0.12)
    ax.set_xlabel("Model file size (GB), left is smaller")
    ax.set_ylabel("Execution accuracy (%)")
    ax.set_title("Accuracy against model size for XiYanSQL 7B, eleven quantizations")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
    ax.set_ylim(0, 100)
    for q in ("Q2_K", "Q4_K_M", "Q8_0"):
        ax.annotate(q, (FILE_GB[q], 3), ha="center", fontsize=8, color="#555")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "quant_curve.png")


def main() -> int:
    results = [r for r in (analyse("core"), analyse("hard")) if r]
    if not results:
        print("no runs found")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "quant_analysis.md").write_text(markdown(results), encoding="utf-8")
    chart(results)
    print(markdown(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
