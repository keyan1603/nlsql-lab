"""Deterministic post-check: does the local SQL filter on a value the question never states?

    python scripts/check_invented.py tuned6 [sets...]

Flags a query that has (a) `column = <number>` or `column IN (...)` with a number that does not occur in the question (as a digit or a number word),
or (b) a quoted date that is not in the question. Reads the question and the SQL only. Used as an extra escalation signal for the router.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from nlsql.invented import invented_values   # noqa: E402

SETS = {"core": "questions", "hard": "questions_hard", "hard2": "questions_hard2", "decline": "questions_decline", "dev": "dev_terse", "dev2": "dev_counter"}


def load_q(s):
    f = SETS.get(s)
    if not f:
        return {}
    d = json.loads((ROOT / "data" / f"{f}.json").read_text(encoding="utf-8"))
    return {q["id"]: q["question"] for q in (d if isinstance(d, list) else d["questions"])}


if __name__ == "__main__":
    label = sys.argv[1]
    for s in (sys.argv[2:] or ["core", "hard", "hard2", "decline"]):
        p = ROOT / "runs" / f"{label}-{s}.jsonl"
        qs = load_q(s)
        if not p.exists() or not qs:
            continue
        tp = fp = fn = 0
        for l in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            if r.get("kind") != "sql" or r["qid"] not in qs:
                continue
            inv = invented_values(qs[r["qid"]], r.get("sql") or "")
            if inv:
                if r["passed"]:
                    fp += 1
                    print(f"  [{s}] FLAG on PASSED {r['qid']}: {inv} :: {qs[r['qid']][:80]}")
                else:
                    tp += 1
                    print(f"  [{s}] flag on failed {r['qid']}: {inv}")
        print(f"{label}-{s}: flagged failed {tp}, flagged passed {fp}")
