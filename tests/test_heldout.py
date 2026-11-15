"""The held-out set: well formed, distinct from every other set, its controls and gold queries run, and the scoring code keeps it out of the 181 pool."""

import sys
from collections import Counter
from pathlib import Path

import pytest

from nlsql import db
from nlsql.config import ROOT
from nlsql.questions import load_questions, problems
from nlsql.safety import check_select

sys.path.insert(0, str(ROOT / "scripts"))

import heldout_checks                                          # noqa: E402
import heldout_report                                          # noqa: E402
import route_eval                                              # noqa: E402

HELD = load_questions(ROOT / "data" / "questions_heldout.json")


def test_the_set_is_well_formed_and_has_the_planned_mix():
    assert problems(HELD) == []
    assert len(HELD) == 52
    assert Counter(q.expected for q in HELD) == {"answer": 40, "unanswerable": 6, "clarify": 6}
    cats = Counter(q.category for q in HELD)
    assert cats["routine"] == 12 and cats["unanswerable"] == 6 and cats["ambiguous"] == 6 and cats["control"] == 4
    assert sum(v for k, v in cats.items() if k not in ("routine", "unanswerable", "ambiguous", "control")) == 24


def test_ids_and_questions_are_distinct_from_every_other_set():
    others = [q for f in ("questions.json", "questions_hard.json", "questions_hard2.json", "questions_decline.json") for q in load_questions(ROOT / "data" / f)]
    assert not ({q.id for q in HELD} & {q.id for q in others})
    assert not ({q.question.lower() for q in HELD} & {q.question.lower() for q in others})


def test_no_dashes_in_the_questions():
    assert all(chr(0x2014) not in q.question and chr(0x2013) not in q.question for q in HELD)


def test_every_gold_query_is_a_safe_select():
    for q in HELD:
        if q.expected == "answer":
            assert check_select(q.gold_sql).ok, q.id


def test_no_overlap_with_the_existing_evaluation_sets():
    assert heldout_checks.check()["vs_eval_sets"] == []


def test_no_overlap_with_the_training_questions():
    assert heldout_checks.check()["vs_training"] == []


@pytest.mark.integration
def test_every_gold_query_returns_rows(reader):
    for q in HELD:
        if q.expected == "answer":
            assert db.run_query(reader, q.gold_sql).rows, q.id


def test_the_heldout_loader_is_empty_without_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(route_eval, "ROOT", tmp_path)
    assert route_eval.load_heldout("no-such-run") == []


def test_the_original_pool_loader_never_contains_heldout_rows():
    assert all(r["set"] != "heldout" for r in route_eval.load_all())


def test_heldout_splits_partition_by_id_prefix():
    rows = [{"qid": q} for q in ("RT01", "RT02", "HO01", "HU01", "HM01", "HK01")]
    parts = route_eval.heldout_splits(rows)
    sizes = {k.split(",", 1)[1].strip() if "," in k else "all": len(v) for k, v in parts.items()}
    assert sizes["routine (2)"] == 2 and sizes["complex (1)"] == 1 and sizes["should decline (2)"] == 2 and sizes["answerable controls (1)"] == 1


def test_rule_stats_counts_recall_and_precision():
    def row(q, local_ok, hosted_ok):
        return {"question": q, "qid": q[:3], "local": {"passed": local_ok}, "hosted": {"passed": hosted_ok}}
    rows = [row("rank customers by spend", False, True),       # routed, local wrong, hosted right
            row("how many customers are there", False, True),  # kept local, local wrong
            row("how many orders were cancelled", True, True),  # kept local, local right
            row("running total of refunds", True, True)]       # routed, local right
    s = heldout_report.rule_stats(rows, 1)
    assert s["routed"] == 2 and s["local_wrong"] == 2 and s["local_wrong_routed"] == 1
    assert s["recall"] == 0.5 and s["precision"] == 0.5 and s["local_wrong_routed_hosted_right"] == 1
