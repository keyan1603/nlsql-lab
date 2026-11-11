"""The decline set: well formed, balanced, and its controls really are answerable on the lab database."""

from collections import Counter

import pytest

from nlsql import db
from nlsql.config import ROOT
from nlsql.questions import load_questions, problems
from nlsql.safety import check_select

DECLINE = load_questions(ROOT / "data" / "questions_decline.json")


def test_the_decline_set_is_well_formed_and_balanced():
    assert problems(DECLINE) == [] and len(DECLINE) == 36
    assert Counter(q.expected for q in DECLINE) == {"unanswerable": 12, "clarify": 12, "answer": 12}


def test_ids_and_questions_are_distinct_from_every_other_set():
    others = [q for f in ("questions.json", "questions_hard.json", "questions_hard2.json") for q in load_questions(ROOT / "data" / f)]
    ids = [q.id for q in DECLINE + others]
    texts = [q.question.lower() for q in DECLINE + others]
    assert len(ids) == len(set(ids)) and len(texts) == len(set(texts))


def test_every_control_gold_query_is_a_safe_select():
    for q in DECLINE:
        if q.expected == "answer":
            assert check_select(q.gold_sql).ok, q.id


@pytest.mark.integration
def test_every_control_returns_rows(reader):
    for q in DECLINE:
        if q.expected == "answer":
            assert db.run_query(reader, q.gold_sql).rows, q.id


@pytest.mark.integration
def test_the_top_five_control_has_no_tie_at_the_cut(reader):
    rows = db.run_query(reader, "SELECT COUNT(*) c FROM ord_line GROUP BY sku ORDER BY c DESC LIMIT 7").rows
    assert rows[4][0] > rows[5][0]
