"""Create the tables and load the deterministic seed. Safe to re-run: the schema drops and recreates everything.

    python scripts/load_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql import db                                  # noqa: E402
from nlsql.config import ROOT, load_settings          # noqa: E402
from nlsql.seed import SEED, build_seed, insert_all   # noqa: E402


def main() -> int:
    settings = load_settings()
    print("settings:", settings)
    conn = db.connect("admin", settings)
    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        db.execute_script(conn, (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        counts = insert_all(conn, build_seed())
    finally:
        conn.close()
    print(f"seed {SEED} loaded:")
    for table, n in counts.items():
        print(f"  {table:14s} {n:5d}")
    with db.connect("reader", settings) as reader:
        print("reader sees", db.scalar(reader, "SELECT COUNT(*) FROM ord_hdr"), "orders")
        print("server version:", db.scalar(reader, "SELECT VERSION()"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
