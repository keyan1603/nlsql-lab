"""Rewrite the run-4/run-6 training files without the pairs whose query filters on a (table, column, value) cell a test gold query uses.

    python scripts/make_strict_data.py

The original files predate the held-out-cell rule for answers (see train/xiyan_ft/README.md). Writes train/data/strict_{train,val,cont2_train,cont2_val}.jsonl
and prints how many pairs were dropped per file. Decline/clarify pairs have no query and are always kept.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_terse_data import test_cells                        # noqa: E402
from nlsql.schema_link import parse_schema                     # noqa: E402
from nlsql.traindata import filter_cells                      # noqa: E402


def main() -> int:
    held = test_cells()
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    for f in ("train", "val", "cont2_train", "cont2_val"):
        rows = [json.loads(l) for l in (ROOT / "train" / "data" / f"{f}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        keep = []
        for r in rows:
            c = r["messages"][-1]["content"]
            sql = c.removeprefix("```sql").removesuffix("```").strip() if c.startswith("```sql") else None
            if not (sql and filter_cells(sql, cols) & held):
                keep.append(r)
        (ROOT / "train" / "data" / f"strict_{f}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
        print(f"{f}: kept {len(keep)} of {len(rows)} (dropped {len(rows) - len(keep)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
