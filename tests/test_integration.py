"""Against the real MySQL database. Skipped on a machine where the lab database is not set up.

Three things are proved here: the gold answers are sound (deterministic, no ties), the grader accepts different correct
queries and rejects the plausible-but-wrong ones the traps are designed to catch, and the read-only account really is read-only.
"""

import pymysql
import pytest

from nlsql import db
from nlsql.grader import Prediction, grade
from nlsql.questions import load_questions
from nlsql.seed import build_seed

pytestmark = pytest.mark.integration
QUESTIONS = {q.id: q for q in load_questions()}


def verdict(reader, qid, sql):
    return grade(QUESTIONS[qid], Prediction("sql", sql=sql), reader)


def test_every_gold_query_runs_returns_rows_and_is_stable(reader):
    for q in QUESTIONS.values():
        if q.expected != "answer":
            continue
        a, b = db.run_query(reader, q.gold_sql), db.run_query(reader, q.gold_sql)
        assert a.rows and a.rows == b.rows, q.id


def test_the_database_holds_exactly_what_the_seed_generates(reader):
    seed = build_seed()
    for table in ("cust_master", "ord_hdr", "ord_line", "refund_req", "support_tkt", "tkt_event", "emp", "prod_catalog", "policy_rule"):
        assert db.scalar(reader, f"SELECT COUNT(*) FROM {table}") == len(seed.rows(table)), table


def test_top_one_questions_have_no_ties(reader):
    rows = db.run_query(reader, "SELECT categ_cd, COUNT(*) n FROM support_tkt GROUP BY categ_cd ORDER BY n DESC LIMIT 2").rows
    assert rows[0][1] > rows[1][1]
    rows = db.run_query(reader, "SELECT DAYNAME(ord_dt), COUNT(*) n FROM ord_hdr GROUP BY 1 ORDER BY n DESC LIMIT 2").rows
    assert rows[0][1] > rows[1][1]
    rows = db.run_query(reader, "SELECT channel_cd, AVG(ord_total_amt) a FROM ord_hdr GROUP BY 1 ORDER BY a DESC LIMIT 2").rows
    assert rows[0][1] != rows[1][1]


def test_the_top_five_question_has_a_deliberate_tie_at_the_cut_off(reader):
    """Fifth and sixth place have the same order count, so the question's own tie-break instruction decides the answer.
    That is intended: it tests whether a model follows 'break ties by customer id'."""
    rows = db.run_query(reader, "SELECT cust_id, COUNT(*) n FROM ord_hdr GROUP BY cust_id ORDER BY n DESC, cust_id LIMIT 6").rows
    assert rows[4][1] == rows[5][1]
    assert [r[0] for r in rows[:5]] == [r[0] for r in db.run_query(reader, QUESTIONS["G02"].gold_sql).rows]


# ---- different correct queries must pass
@pytest.mark.parametrize("qid, sql", [
    ("J01", "SELECT cust_nm FROM cust_master WHERE cust_id IN (SELECT cust_id FROM ord_hdr WHERE ord_status = 'R')"),
    ("N03", "SELECT c.cust_id FROM cust_master c LEFT JOIN ord_hdr o ON o.cust_id = c.cust_id WHERE o.ord_id IS NULL"),
    ("N01", "SELECT COUNT(1) AS open_tickets FROM support_tkt WHERE closed_ts IS NULL"),
    ("A02", "SELECT COUNT(*) FROM cust_master c JOIN code_lookup k ON k.code_type = 'TIER' AND k.code_val = c.tier_cd WHERE k.code_desc = 'Platinum' AND c.is_actv = 1"),
    ("D01", "SELECT COUNT(*) FROM ord_hdr WHERE YEAR(ord_dt) = 2026 AND MONTH(ord_dt) = 10"),
    ("P01", "SELECT rule_val FROM policy_rule WHERE rule_key = 'refund_approval_threshold' ORDER BY eff_from DESC LIMIT 1"),
    ("F03", "SELECT COUNT(*) FROM (SELECT ord_id FROM ord_line WHERE disc_pct > 0 GROUP BY ord_id) t"),
    ("J04", "SELECT t.tkt_id, c.cust_nm, t.sev_lvl FROM support_tkt t JOIN cust_master c ON c.cust_id = t.cust_id WHERE t.closed_ts IS NULL"),
])
def test_alternative_correct_queries_are_accepted(reader, qid, sql):
    v = verdict(reader, qid, sql)
    assert v.passed, (qid, v.outcome, v.detail)


def test_the_extra_column_answer_is_flagged_as_lenient_not_strict(reader):
    v = verdict(reader, "J04", "SELECT t.tkt_id, c.cust_nm, t.sev_lvl FROM support_tkt t JOIN cust_master c ON c.cust_id = t.cust_id WHERE t.closed_ts IS NULL")
    assert v.match == "lenient"


def test_swapped_column_order_is_perm_not_strict(reader):
    v = verdict(reader, "J04", "SELECT c.cust_nm, t.tkt_id FROM support_tkt t JOIN cust_master c ON c.cust_id = t.cust_id WHERE t.closed_ts IS NULL")
    assert v.passed and v.match == "perm"


# ---- the plausible-but-wrong queries the traps are built to catch must fail
@pytest.mark.parametrize("qid, sql, why", [
    ("A04", "SELECT AVG(list_prc) FROM prod_catalog WHERE disc_flag = 1", "read disc_flag as 'has a discount'"),
    ("N01", "SELECT COUNT(*) FROM support_tkt WHERE closed_ts = NULL", "= NULL is never true"),
    ("F02", "SELECT c.tier_cd, SUM(o.ord_total_amt) FROM ord_hdr o JOIN cust_master c ON c.cust_id = o.cust_id JOIN ord_line l ON l.ord_id = o.ord_id WHERE o.ord_status = 'D' AND o.currency_cd = 'USD' GROUP BY c.tier_cd", "fan-out: header total repeated per line"),
    ("F03", "SELECT COUNT(*) FROM ord_line WHERE disc_pct > 0", "counted lines, not orders"),
    ("J01", "SELECT c.cust_nm FROM cust_master c JOIN ord_hdr o ON o.cust_id = c.cust_id WHERE o.ord_status = 'R'", "forgot DISTINCT"),
    ("P01", "SELECT rule_val FROM policy_rule WHERE rule_key = 'refund_approval_threshold' ORDER BY eff_from LIMIT 1", "took the oldest row, not the one in force"),
    ("A02", "SELECT COUNT(*) FROM cust_master WHERE tier_cd = 'P'", "forgot the active filter"),
    ("D06", "SELECT COUNT(*) FROM ord_hdr WHERE DAYOFWEEK(ord_dt) IN (6, 7)", "wrong weekday numbering"),
    ("G02", "SELECT cust_id, COUNT(*) FROM ord_hdr GROUP BY cust_id ORDER BY 2 ASC, cust_id LIMIT 5", "bottom five, not top five"),
    ("A07", "SELECT COUNT(*) FROM refund_req WHERE status_cd = 'Pending'", "used the word instead of the code"),
])
def test_plausible_wrong_queries_are_rejected(reader, qid, sql, why):
    v = verdict(reader, qid, sql)
    assert not v.passed, (qid, why, v.outcome)


def test_a_syntax_error_and_an_unknown_column_are_sql_errors(reader):
    assert verdict(reader, "A01", "SELEC COUNT(*) FROM cust_master").outcome in ("unsafe", "sql_error")
    v = verdict(reader, "A01", "SELECT COUNT(*) FROM cust_master WHERE active = 1")
    assert v.outcome == "sql_error" and "active" in v.detail


# ---- the reader account
def test_the_reader_cannot_write_in_any_way(reader):
    for stmt in ("INSERT INTO code_lookup VALUES ('X','Y','z')", "UPDATE emp SET salary_amt = 0", "DELETE FROM ord_hdr",
                 "DROP TABLE emp", "CREATE TABLE nope (a INT)", "TRUNCATE TABLE ord_line"):
        with pytest.raises(pymysql.err.MySQLError) as err:
            db.run_query(reader, stmt)
        assert err.value.args[0] in (1142, 1792, 1044, 1227), (stmt, err.value.args)      # privilege or read-only session errors


def test_the_reader_has_select_and_nothing_else(reader):
    grants = " ".join(r[0] for r in db.run_query(reader, "SHOW GRANTS FOR CURRENT_USER()").rows)
    assert "GRANT SELECT ON" in grants and "ALL PRIVILEGES" not in grants and "INSERT" not in grants.upper().replace("USAGE", "")


def test_the_reader_cannot_see_other_databases(reader):
    schemas = {r[0] for r in db.run_query(reader, "SELECT schema_name FROM information_schema.schemata").rows}
    assert "nlsql_lab" in schemas and "mysql" not in schemas


def test_a_runaway_query_is_stopped_by_the_server_time_limit(reader):
    with pytest.raises(db.QueryTimeout):
        # four-way join filtered on an expression: the optimizer cannot shortcut it (a plain COUNT over a cross join it can)
        db.run_query(reader, "SELECT COUNT(*) FROM ord_line a, ord_line b, ord_line c, ord_line d WHERE a.qty + b.qty + c.qty + d.qty = 7", timeout_ms=300)


def test_a_huge_result_is_refused(reader):
    with pytest.raises(ValueError):
        db.run_query(reader, "SELECT a.ord_id FROM ord_line a, ord_line b", max_rows=1000)
