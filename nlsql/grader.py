"""Execution accuracy: does the generated query return the same answer as the gold query?

Judged by running both on the database and comparing result sets, never by comparing the SQL text, because many different
queries are correct. Three levels of match are reported, because they answer different questions:

  strict   same rows, same columns in the same order        (what a downstream program that indexes columns needs)
  perm     same rows, columns allowed in a different order   (the headline number: the same answer, laid out differently)
  lenient  the gold columns appear among extra columns        (the answer is there, with additions)

Non-SELECT output is never executed. Questions that cannot be answered, or that are ambiguous, are graded on whether the
model said so instead of inventing a query.
"""

from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from nlsql.questions import Question
from nlsql.safety import check_select

MAX_PERM_WIDTH = 6
MAX_LENIENT_COMBOS = 5000


@dataclass
class Prediction:
    kind: str                       # "sql", "refusal" or "clarify"
    sql: Optional[str] = None
    text: str = ""
    latency_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    how: str = ""                  # how the statement was found in the model's text: fence, bare, marker, unfinished or none


@dataclass
class Verdict:
    qid: str
    outcome: str                    # see OUTCOMES
    match: Optional[str] = None     # strict / perm / lenient when the answer was right
    detail: str = ""
    exec_ms: float = 0.0
    passed: bool = False
    extras: dict = field(default_factory=dict)


OUTCOMES = {
    "correct": "right answer",
    "wrong_result": "ran, but returned a different answer",
    "sql_error": "the database rejected the query",
    "unsafe": "refused by the safety check, never executed",
    "timeout": "exceeded the time limit",
    "no_sql": "no SQL was produced",
    "correct_refusal": "correctly said the question cannot be answered",
    "correct_clarify": "correctly asked for clarification",
    "partial_refusal": "declined, but the wrong way (refused when it should clarify, or the reverse)",
    "wrongly_answered": "invented a query for a question that cannot or should not be answered",
    "wrongly_refused": "declined a question that has an answer",
}
PASSING = {"correct", "correct_refusal", "correct_clarify"}


def norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return v.total_seconds()
    if isinstance(v, (bytes, bytearray)):
        v = bytes(v).decode("utf-8", "replace")
    return str(v).strip()


def _as_number(v: Any) -> Optional[float]:
    if isinstance(v, float):
        return v
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def cells_close(a: Any, b: Any, tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= max(tol, 0.005)
    return a == b


def _sort_key(row: tuple) -> tuple:
    key = []
    for v in row:
        if v is None:
            key.append((0, 0.0, ""))
        elif isinstance(v, float):
            key.append((1, round(v, 1), ""))
        else:
            n = _as_number(v)
            key.append((1, round(n, 1), "") if n is not None else (2, 0.0, v))
    return tuple(key)


def _rows_equal(gold: list[tuple], pred: list[tuple], order_matters: bool, tol: float) -> bool:
    if len(gold) != len(pred):
        return False
    if not order_matters:
        gold, pred = sorted(gold, key=_sort_key), sorted(pred, key=_sort_key)
    return all(len(g) == len(p) and all(cells_close(a, b, tol) for a, b in zip(g, p)) for g, p in zip(gold, pred))


def _project(rows: list[tuple], idx: tuple) -> list[tuple]:
    return [tuple(r[i] for i in idx) for r in rows]


def compare_results(gold_rows: list[tuple], pred_rows: list[tuple], order_matters: bool = False, tol: float = 0.0) -> Optional[str]:
    """Return 'strict', 'perm', 'lenient' or None."""
    gold = [tuple(norm(v) for v in r) for r in gold_rows]
    pred = [tuple(norm(v) for v in r) for r in pred_rows]
    if len(gold) != len(pred):
        return None
    gw = len(gold[0]) if gold else 0
    pw = len(pred[0]) if pred else 0
    if not gold:
        return "strict" if not pred else None
    if gw == pw:
        if _rows_equal(gold, pred, order_matters, tol):
            return "strict"
        if gw <= MAX_PERM_WIDTH:
            for perm in itertools.permutations(range(gw)):
                if _rows_equal(gold, _project(pred, perm), order_matters, tol):
                    return "perm"
        return None
    if pw > gw and pw <= 8:
        for n, idx in enumerate(itertools.permutations(range(pw), gw)):
            if n >= MAX_LENIENT_COMBOS:
                break
            if _rows_equal(gold, _project(pred, idx), order_matters, tol):
                return "lenient"
    return None


def grade(q: Question, pred: Prediction, conn=None, gold_rows: Optional[list] = None) -> Verdict:
    """Grade one prediction. `conn` is a read-only connection; `gold_rows` can be passed to avoid re-running the gold query."""
    from nlsql import db   # imported here so the pure comparison functions work without a database driver configured

    if q.expected != "answer":
        want = "refusal" if q.expected == "unanswerable" else "clarify"
        if pred.kind == want:
            return Verdict(q.id, "correct_refusal" if want == "refusal" else "correct_clarify", passed=True)
        if pred.kind in ("refusal", "clarify"):
            return Verdict(q.id, "partial_refusal", detail=f"expected {want}, got {pred.kind}")
        return Verdict(q.id, "wrongly_answered", detail=(pred.sql or "")[:200])

    if pred.kind in ("refusal", "clarify"):
        return Verdict(q.id, "wrongly_refused", detail=pred.text[:200])
    if not pred.sql or not pred.sql.strip():
        return Verdict(q.id, "no_sql")
    safe = check_select(pred.sql)
    if not safe.ok:
        return Verdict(q.id, "unsafe", detail=safe.reason)
    if gold_rows is None:
        gold_rows = db.run_query(conn, q.gold_sql).rows
    try:
        res = db.run_query(conn, pred.sql.strip().rstrip(";"))
    except db.QueryTimeout as exc:
        return Verdict(q.id, "timeout", detail=str(exc))
    except Exception as exc:                                           # the driver raises many subclasses; the message is the evidence
        return Verdict(q.id, "sql_error", detail=str(exc)[:200])
    level = compare_results(gold_rows, res.rows, q.order_matters, q.float_tol)
    if level:
        return Verdict(q.id, "correct", match=level, exec_ms=res.elapsed_ms, passed=True)
    return Verdict(q.id, "wrong_result", exec_ms=res.elapsed_ms,
                   detail=f"gold {len(gold_rows)} rows x {len(gold_rows[0]) if gold_rows else 0} cols; got {len(res.rows)} rows x {len(res.columns)} cols")


def summarize(verdicts: list[Verdict]) -> dict:
    """Headline numbers for a run."""
    answerable = [v for v in verdicts if v.outcome in ("correct", "wrong_result", "sql_error", "unsafe", "timeout", "no_sql", "wrongly_refused")]
    correct = [v for v in answerable if v.outcome == "correct"]
    by_level = {lvl: sum(1 for v in correct if v.match == lvl) for lvl in ("strict", "perm", "lenient")}
    handled = [v for v in verdicts if v.outcome in ("correct_refusal", "correct_clarify", "partial_refusal", "wrongly_answered")]
    return {
        "questions": len(verdicts),
        "answerable": len(answerable),
        "correct": len(correct),
        "execution_accuracy": round(len(correct) / len(answerable), 4) if answerable else None,
        "match_levels": by_level,
        "sql_errors": sum(1 for v in verdicts if v.outcome == "sql_error"),
        "unsafe": sum(1 for v in verdicts if v.outcome == "unsafe"),
        "timeouts": sum(1 for v in verdicts if v.outcome == "timeout"),
        "should_decline": len(handled),
        "declined_correctly": sum(1 for v in handled if v.outcome in ("correct_refusal", "correct_clarify")),
        "invented_answers": sum(1 for v in handled if v.outcome == "wrongly_answered"),
    }
