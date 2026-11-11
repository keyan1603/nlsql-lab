"""Measure table selection: how often does the pruned schema still contain every table the gold query uses?

    python scripts/check_linking.py [--k 5]

The gold query is used here only to count; the selector never sees it.
"""

import argparse
import sys
from pathlib import Path

import sqlglot
from sqlglot import exp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql.config import ROOT                                       # noqa: E402
from nlsql.questions import load_questions                          # noqa: E402
from nlsql.schema_link import parse_schema, select_tables           # noqa: E402


def gold_tables(sql: str, known: set) -> set:
    tree = sqlglot.parse_one(sql, read="mysql")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    return {t.name for t in tree.find_all(exp.Table) if t.name not in ctes and t.name in known}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()
    for label, fname, extended in (("core", "questions.json", False), ("hard", "questions_hard.json", True), ("hard2", "questions_hard2.json", True)):
        tables = parse_schema(extended)
        known = {t.name for t in tables}
        qs = [q for q in load_questions(ROOT / "data" / fname) if q.expected == "answer"]
        ok, shown, missed = 0, 0, []
        for q in qs:
            need = gold_tables(q.gold_sql, known)
            kept = {t.name for t in select_tables(q.question, tables, args.k)}
            shown += len(kept)
            if need <= kept:
                ok += 1
            else:
                missed.append((q.id, sorted(need - kept)))
        print(f"{label:6} k={args.k}: all needed tables kept for {ok}/{len(qs)} ({ok / len(qs):.0%}); average {shown / len(qs):.1f} of {len(tables)} tables shown")
        for qid, miss in missed[:12]:
            print(f"   {qid} missing {miss}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
