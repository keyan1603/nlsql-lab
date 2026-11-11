"""Sample example values for every column of the lab database and save them to data/schema_examples.json.

    python scripts/build_schema_examples.py

Columns with at most 8 distinct values list all of them (these are the coded columns); the rest list 3. Columns that hold personal
data (email, phone, national id, salary, or anything the schema comment calls sensitive) get no examples, so a prompt never carries
real personal values. Deterministic: values are the first ones in sort order. Uses the read-only account.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql import db                                              # noqa: E402
from nlsql.schema_link import EXAMPLES_FILE, is_sensitive, parse_schema   # noqa: E402


def main() -> int:
    conn = db.connect("reader")
    out: dict = {}
    for t in parse_schema(True):
        for c in t.columns:
            if is_sensitive(t, c):
                continue
            distinct = db.scalar(conn, f"SELECT COUNT(DISTINCT `{c.name}`) FROM `{t.name}`")
            limit = 8 if distinct <= 8 else 3
            rows = db.run_query(conn, f"SELECT DISTINCT `{c.name}` FROM `{t.name}` WHERE `{c.name}` IS NOT NULL ORDER BY `{c.name}` LIMIT {limit}").rows
            vals = [str(r[0])[:30] for r in rows]
            if vals:
                out.setdefault(t.name, {})[c.name] = vals
    EXAMPLES_FILE.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {EXAMPLES_FILE}: {sum(len(v) for v in out.values())} columns in {len(out)} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
