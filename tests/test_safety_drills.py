"""The attack corpus as a regression test: every harmful statement must be stopped by the guard, every harmless one must still run.
Offline part: the guard's text, parser and policy layers alone. Integration part: the full guard against the real database."""

import json

import pytest

from nlsql import db
from nlsql.config import ROOT
from nlsql.guard import Guard, Policy

ATTACKS = json.loads((ROOT / "data" / "attacks.json").read_text(encoding="utf-8"))["attacks"]
HARMFUL = [a for a in ATTACKS if a["expect"] == "blocked"]
HARMLESS = [a for a in ATTACKS if a["expect"] != "blocked"]


def ids(items):
    return [a["id"] for a in items]


def test_the_corpus_covers_every_category_and_is_large_enough():
    cats = {a["category"] for a in ATTACKS}
    assert cats == {"write", "stacking", "resource", "disclosure", "personal"} and len(HARMFUL) >= 60
    assert len({a["id"] for a in ATTACKS}) == len(ATTACKS)


@pytest.mark.parametrize("a", [a for a in HARMFUL if a["category"] in ("write", "stacking", "disclosure", "personal")], ids=lambda a: a["id"])
def test_the_guard_refuses_before_the_database_is_touched(a, tmp_path):
    refusal, to_run, _ = Guard(Policy(), audit_path=tmp_path / "a.jsonl").review(a["sql"])
    assert refusal is not None and to_run == "", a["sql"]


@pytest.mark.parametrize("a", [a for a in HARMLESS if a["expect"] == "allowed"], ids=lambda a: a["id"])
def test_harmless_statements_are_not_refused(a, tmp_path):
    refusal, _, _ = Guard(Policy(), audit_path=tmp_path / "a.jsonl").review(a["sql"])
    assert refusal is None, a["sql"]


@pytest.mark.integration
def test_the_full_guard_stops_every_harmful_statement_on_the_real_database(reader, tmp_path):
    guard = Guard(Policy(), audit_path=tmp_path / "a.jsonl", timeout_ms=1500)
    leaked = []
    for a in HARMFUL:
        r = guard.execute(reader, f"[{a['id']}]", a["sql"])
        if r.decision in ("allowed", "masked"):
            leaked.append(a["id"])
    assert leaked == []


@pytest.mark.integration
def test_the_versioned_comment_leak_is_closed_end_to_end(reader, tmp_path):
    sql = "SELECT 1 /*!50000 UNION SELECT salary_amt FROM emp */"
    try:
        leaked = bool(db.run_query(reader, sql).rows[1:])          # account with SELECT on the whole database: the hidden UNION runs
    except Exception as exc:
        assert "denied" in str(exc).lower()                         # account narrowed by setup/least_privilege.sql: MySQL itself refuses
        leaked = False
    r = Guard(Policy(), audit_path=tmp_path / "a.jsonl").execute(reader, "q", sql)
    assert r.decision == "refused" and r.layer == "text"


@pytest.mark.integration
def test_the_masked_email_never_contains_the_raw_value(reader, tmp_path):
    raw = db.run_query(reader, "SELECT email_addr FROM cust_master WHERE cust_id = 'C-1002'").rows[0][0]
    r = Guard(Policy(), audit_path=tmp_path / "a.jsonl").execute(reader, "q", "SELECT email_addr FROM cust_master WHERE cust_id = 'C-1002'")
    assert r.decision == "masked" and r.rows[0][0] != raw and "***@" in r.rows[0][0] and r.columns == ["email_addr"]


@pytest.mark.integration
def test_a_runaway_query_is_stopped_by_the_time_limit(reader, tmp_path):
    guard = Guard(Policy(), audit_path=tmp_path / "a.jsonl", timeout_ms=1000)
    r = guard.execute(reader, "q", "SELECT COUNT(*) FROM web_event a JOIN web_event b ON a.evt_ts <> b.evt_ts JOIN web_event c ON b.evt_ts <> c.evt_ts")
    assert r.decision == "timeout" and r.elapsed_ms < 5000


@pytest.mark.integration
def test_a_large_result_is_capped_not_returned(reader, tmp_path):
    r = Guard(Policy(max_rows=100), audit_path=tmp_path / "a.jsonl").execute(reader, "q", "SELECT evt_id FROM web_event")
    assert r.decision == "capped" and r.rows == []
