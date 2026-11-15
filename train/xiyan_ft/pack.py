"""Build xiyan_ft_package.zip: the training script, the chat-format data and the README, ready to upload to Kaggle or Colab.

    python train/xiyan_ft/pack.py              # strict (default): drops every answer pair whose query filters on a held-out test cell
    python train/xiyan_ft/pack.py --lenient    # only the question/query overlap filter, as the 3B runs used (more pairs, weaker hygiene)

Checks that no training question is a test question (nlsql.traindata.LeakFilter over the core, hard, hard2 and decline sets) and, in strict
mode, drops every answer pair that filters on a (table, column, value) cell that a test gold query filters on. The source files in
train/data are never modified; the filtered copies exist only inside the zip. The build fails if a question overlaps. Writes
train/xiyan_ft/xiyan_ft_package.zip (not committed) and train/xiyan_ft/package_report.json (committed).
"""
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_terse_data import test_cells                  # noqa: E402
from make_training_data import tests_for_leaks          # noqa: E402
from nlsql.router import families_of                    # noqa: E402
from nlsql.schema_link import parse_schema              # noqa: E402
from nlsql.traindata import LeakFilter, filter_cells    # noqa: E402

FILES = ["train.jsonl", "val.jsonl", "hard_train.jsonl", "hard_val.jsonl", "cont2_train.jsonl", "cont2_val.jsonl"]


def main() -> int:
    strict = "--lenient" not in sys.argv
    leak = LeakFilter(tests_for_leaks())
    held = test_cells()
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    report = {"mode": "strict" if strict else "lenient", "files": {}}
    kept_text, overlap = {}, 0
    for f in FILES:
        rows = [json.loads(line) for line in (ROOT / "train" / "data" / f).read_text(encoding="utf-8").splitlines() if line.strip()]
        out, dropped_cells = [], 0
        for r in rows:
            m = r["messages"]
            sql = m[-1]["content"].removeprefix("```sql").removesuffix("```").strip() if m[-1]["content"].startswith("```sql") else None
            if leak.why(m[1]["content"], sql):
                overlap += 1
            if strict and sql and filter_cells(sql, cols) & held:
                dropped_cells += 1
                continue
            out.append(r)
        kept_text[f] = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out)
        n_dec = sum(1 for r in out if r["messages"][-1]["content"].startswith("--"))
        fam = Counter(x for r in out if r["messages"][-1]["content"].startswith("```sql") for x in (families_of(r["messages"][1]["content"]) or ("no_router_cue",)))
        src = Counter(r.get("source", "original teacher-verified pool") for r in out)
        report["files"][f] = {"pairs": len(out), "declines": n_dec, "dropped_for_held_out_cells": dropped_cells, "router_regex_families": dict(fam), "sources": dict(src)}
    report["overlap_with_test_questions"] = overlap
    print(json.dumps(report, indent=1))
    if overlap:
        print("FAILED: training pairs overlap a test question")
        return 1
    out = ROOT / "train" / "xiyan_ft" / "xiyan_ft_package.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "train" / "xiyan_ft" / "train_qlora_7b.py", "train_qlora_7b.py")
        z.write(ROOT / "train" / "xiyan_ft" / "README.md", "README.md")
        for f, text in kept_text.items():
            z.writestr(f"data/{f}", text)
    (ROOT / "train" / "xiyan_ft" / "package_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("wrote", out, round(out.stat().st_size / 1e6, 1), "MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
