"""What do the safety controls cost? Send every gold query through the guard and compare with the unguarded result.

    python scripts/guard_fidelity.py

A control that changes correct answers is a cost to report. Each gold query ends up as one of:
    same      the guard ran it and the result matches the gold result
    masked    a personal column was returned masked (an intended change)
    blocked   the guard refused a query the question set treats as correct
    changed   the guard ran it and the result differs (a rewrite changed the meaning: must be zero)
Writes docs/results/guard_fidelity.md.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql import db                                  # noqa: E402
from nlsql.config import ROOT                         # noqa: E402
from nlsql.grader import compare_results              # noqa: E402
from nlsql.guard import Guard, Policy                 # noqa: E402
from nlsql.questions import load_questions            # noqa: E402

SETS = ["questions.json", "questions_hard.json", "questions_hard2.json", "questions_decline.json"]


def main() -> int:
    conn = db.connect("reader")
    guard = Guard(Policy(), audit_path=ROOT / "runs" / "audit_fidelity.jsonl")
    counts: Counter = Counter()
    notes: list[str] = []
    for f in SETS:
        for q in load_questions(ROOT / "data" / f):
            if q.expected != "answer":
                continue
            gold = db.run_query(conn, q.gold_sql).rows
            r = guard.execute(conn, q.question, q.gold_sql)
            if r.decision == "refused" or r.decision in ("capped", "timeout"):
                kind = "blocked"
                notes.append(f"- {q.id}: blocked by {r.layer}: {r.reason}")
            elif r.decision == "masked":
                kind = "masked"
                notes.append(f"- {q.id}: personal column returned masked ({', '.join(r.masked_columns)})")
            else:
                kind = "same" if compare_results(gold, r.rows, q.order_matters, q.float_tol) else "changed"
                if kind == "changed":
                    notes.append(f"- {q.id}: result differs after the guard rewrote the query")
            counts[kind] += 1
    total = sum(counts.values())
    lines = ["# What the guard costs on the gold queries", "",
             f"All {total} answerable gold queries (core, both stress halves and the decline-set controls) went through `Guard.execute`.", "",
             "| Outcome | Queries |", "|---|---|"]
    lines += [f"| {k} | {counts.get(k, 0)} |" for k in ("same", "masked", "blocked", "changed")]
    if notes:
        lines += ["", *notes]
    text = "\n".join(lines) + "\n"
    (ROOT / "docs" / "results" / "guard_fidelity.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if counts.get("changed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
