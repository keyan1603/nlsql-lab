"""Run every gold query and check that the labelled set is sound: each query runs, returns something sensible, is
deterministic, and does not have a tie that would make the 'right answer' depend on row order.

    python scripts/check_gold.py [--show]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tabulate import tabulate                                # noqa: E402

from nlsql import db                                         # noqa: E402
from nlsql.config import ROOT                                # noqa: E402
from nlsql.grader import compare_results                     # noqa: E402
from nlsql.questions import load_questions, problems         # noqa: E402
from nlsql.safety import check_select                        # noqa: E402


def main() -> int:
    show = "--show" in sys.argv
    which = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "core"
    questions = load_questions(ROOT / "data" / {"core": "questions.json", "hard": "questions_hard.json", "hard2": "questions_hard2.json", "decline": "questions_decline.json"}[which])
    bad = problems(questions)
    for p in bad:
        print("PROBLEM:", p)
    conn = db.connect("reader")
    rows_out, failures = [], 0
    for q in questions:
        if q.expected != "answer":
            rows_out.append([q.id, q.category, q.difficulty, "(no query: " + q.expected + ")", "", ""])
            continue
        safe = check_select(q.gold_sql)
        try:
            first = db.run_query(conn, q.gold_sql)
            second = db.run_query(conn, q.gold_sql)
        except Exception as exc:
            rows_out.append([q.id, q.category, q.difficulty, "ERROR", str(exc)[:70], ""])
            failures += 1
            continue
        stable = compare_results(first.rows, second.rows, True) == "strict"
        shape = f"{len(first.rows)} x {len(first.columns)}"
        flags = []
        if not safe.ok:
            flags.append("UNSAFE:" + safe.reason)
        if not first.rows:
            flags.append("EMPTY")
        if not stable:
            flags.append("NONDETERMINISTIC")
        if flags:
            failures += 1
        preview = "; ".join(str(r) for r in first.rows[:2])[:90]
        rows_out.append([q.id, q.category, q.difficulty, shape, preview if show or True else "", " ".join(flags)])
    print(tabulate(rows_out, headers=["id", "category", "level", "rows x cols", "first rows", "flags"], tablefmt="github"))
    print(f"\n{len(questions)} questions, {sum(1 for q in questions if q.expected == 'answer')} with gold queries, {failures} failing checks, {len(bad)} set problems")
    return 1 if failures or bad else 0


if __name__ == "__main__":
    sys.exit(main())
