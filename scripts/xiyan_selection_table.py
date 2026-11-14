import json, sys
from pathlib import Path
R = Path(__file__).resolve().parent.parent
rows = [("XiYan plain prompt", "xy-plain", "xiyan7b-q4km-hard"), ("mschema prompt", "xy-mschema", None), ("tuned prompt", "xy-tuned", None), ("tuned + dialect rules", "xy-tuned-dialect", None),
        ("tuned + 4 decline examples (d4)", "xy-tuned-d4", None), ("tuned + dialect + d4", "xy-tuned-dialect-d4", None), ("tuned + dialect + d6", "xy-tuned-dialect-d6", None),
        ("tuned + dialect + d6 + 2 answer examples", "xy-tuned-dialect-d6-a2", None), ("tuned + d4 + retry 2 (FINAL)", "xy-tuned-d4-r2", None), ("tuned + d4 + decline guard (rejected)", "xy-tuned-d4-guard", None)]
def g(label):
    p = R / "runs" / f"{label}.summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
L = ["# XiYan selection runs (dev, dev2, hard only)", "", "Choosing rule, fixed before round 2: highest total of answerable-correct (dev 18, dev2 14, hard 72) plus declines-correct (dev 12). Differences of 3 questions or fewer are not distinguishable. hard2 and the decline set were not used.", "",
     "| Configuration | dev answerable (of 18) | dev declines (of 12) | dev2 (of 14) | hard (of 72) | Total answerable (of 104) | Total with declines |", "|---|---|---|---|---|---|---|"]
out = {}
for name, pre, hardlabel in rows:
    d, d2, h = g(f"{pre}-dev"), g(f"{pre}-dev2"), g(hardlabel or f"{pre}-hard")
    if not d or not d2:
        continue
    hc = h["correct"] if h else None
    tot = d["correct"] + d2["correct"] + (hc or 0)
    L.append(f"| {name} | {d['correct']} | {d['declined_correctly']} | {d2['correct']} | {hc if h else 'not run'} | {tot if h else 'n/a'} | {tot + d['declined_correctly'] if h else 'n/a'} |")
    out[name] = {"dev": d["correct"], "dev_declines": d["declined_correctly"], "dev2": d2["correct"], "hard": hc}
L += ["", "Guard: with the decline guard the dev declines rose from 5 to 9 of 12 but 12 answerable questions were lost (74 down to 62) across the three sets (over-declining), so it was rejected."]
dst = R / "docs" / "results" / "xiyan"
dst.mkdir(parents=True, exist_ok=True)
(dst / "selection.md").write_text("\n".join(L) + "\n", encoding="utf-8")
(dst / "selection.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("\n".join(L))
