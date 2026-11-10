"""The grader and the SQL safety check, tested without a database."""

import datetime as dt
from decimal import Decimal

import pytest

from nlsql import db
from nlsql.grader import Prediction, compare_results, grade, summarize
from nlsql.questions import Question
from nlsql.safety import check_select


def q(expected="answer", gold="SELECT 1", order=False, tol=0.0, qid="X01"):
    return Question(id=qid, category="t", difficulty="easy", expected=expected, question="?", gold_sql=gold if expected == "answer" else None,
                    order_matters=order, tests="", float_tol=tol)


# ---- result comparison
def test_identical_results_match_strictly():
    assert compare_results([(1, "a"), (2, "b")], [(1, "a"), (2, "b")]) == "strict"


def test_row_order_is_ignored_unless_it_matters():
    assert compare_results([(1,), (2,)], [(2,), (1,)]) == "strict"
    assert compare_results([(1,), (2,)], [(2,), (1,)], order_matters=True) is None


def test_columns_in_a_different_order_match_at_the_perm_level():
    assert compare_results([("EU", 5), ("NA", 9)], [(5, "EU"), (9, "NA")]) == "perm"


def test_extra_columns_match_only_at_the_lenient_level():
    assert compare_results([("C-1",), ("C-2",)], [("C-1", 4), ("C-2", 7)]) == "lenient"


def test_a_missing_column_is_wrong():
    assert compare_results([("C-1", 4)], [("C-1",)]) is None


def test_wrong_values_and_wrong_row_counts_are_wrong():
    assert compare_results([(1,), (2,)], [(1,), (3,)]) is None
    assert compare_results([(1,), (2,)], [(1,)]) is None
    assert compare_results([(1,)], []) is None


def test_decimal_float_and_int_compare_by_value():
    assert compare_results([(Decimal("12.50"),)], [(12.5,)]) == "strict"
    assert compare_results([(3,)], [(Decimal("3.00"),)]) == "strict"


def test_a_numeric_string_equals_the_number():
    assert compare_results([("500.00",)], [(Decimal("500.00"),)]) == "strict"


def test_tolerance_is_applied_only_when_asked_for():
    assert compare_results([(10.0,)], [(10.04,)]) is None
    assert compare_results([(10.0,)], [(10.04,)], tol=0.1) == "strict"


def test_dates_and_text_compare_as_values():
    assert compare_results([(dt.date(2026, 1, 2),)], [(dt.date(2026, 1, 2),)]) == "strict"
    assert compare_results([(dt.date(2026, 1, 2),)], [("2026-01-02",)]) == "strict"
    assert compare_results([("Aurora",)], [("aurora",)]) is None


def test_nulls_compare_equal_to_nulls_only():
    assert compare_results([(None,)], [(None,)]) == "strict"
    assert compare_results([(None,)], [(0,)]) is None


def test_two_empty_results_match():
    assert compare_results([], []) == "strict"


def test_duplicates_matter():
    assert compare_results([("a",), ("a",)], [("a",)]) is None


# ---- grading with a fake database
class FakeResult:
    def __init__(self, rows, columns=("c",)):
        self.rows, self.columns, self.elapsed_ms = rows, list(columns), 1.0


@pytest.fixture
def fake_db(monkeypatch):
    state = {"gold": [(5,)], "pred": FakeResult([(5,)]), "raise": None}

    def run_query(conn, sql, **kw):
        if state["raise"]:
            raise state["raise"]
        return state["pred"] if "pred" in sql else FakeResult(state["gold"])
    monkeypatch.setattr(db, "run_query", run_query)
    return state


def test_a_correct_query_passes(fake_db):
    v = grade(q(gold="SELECT 5"), Prediction("sql", sql="SELECT 5 /*pred*/"), conn=None, gold_rows=[(5,)])
    assert v.outcome == "correct" and v.passed and v.match == "strict"


def test_a_wrong_answer_is_reported_with_shapes(fake_db):
    fake_db["pred"] = FakeResult([(6,)])
    v = grade(q(), Prediction("sql", sql="SELECT 6 /*pred*/"), conn=None, gold_rows=[(5,)])
    assert v.outcome == "wrong_result" and not v.passed and "1 rows" in v.detail


def test_database_errors_are_captured(fake_db):
    fake_db["raise"] = RuntimeError("Unknown column 'x'")
    v = grade(q(), Prediction("sql", sql="SELECT x FROM t"), conn=None, gold_rows=[(5,)])
    assert v.outcome == "sql_error" and "Unknown column" in v.detail


def test_timeouts_are_their_own_outcome(fake_db):
    fake_db["raise"] = db.QueryTimeout("too slow")
    assert grade(q(), Prediction("sql", sql="SELECT 1"), conn=None, gold_rows=[(5,)]).outcome == "timeout"


def test_unsafe_sql_is_never_executed(fake_db):
    fake_db["raise"] = AssertionError("must not run")
    v = grade(q(), Prediction("sql", sql="DROP TABLE emp"), conn=None, gold_rows=[(5,)])
    assert v.outcome == "unsafe"


def test_empty_output_is_no_sql(fake_db):
    assert grade(q(), Prediction("sql", sql="  "), conn=None, gold_rows=[(5,)]).outcome == "no_sql"


def test_refusing_an_answerable_question_is_a_failure(fake_db):
    assert grade(q(), Prediction("refusal", text="cannot"), conn=None).outcome == "wrongly_refused"


def test_unanswerable_questions_are_graded_on_declining():
    assert grade(q("unanswerable"), Prediction("refusal")).outcome == "correct_refusal"
    assert grade(q("unanswerable"), Prediction("sql", sql="SELECT 1")).outcome == "wrongly_answered"
    assert grade(q("unanswerable"), Prediction("clarify")).outcome == "partial_refusal"


def test_ambiguous_questions_are_graded_on_asking():
    assert grade(q("clarify"), Prediction("clarify")).outcome == "correct_clarify"
    assert grade(q("clarify"), Prediction("sql", sql="SELECT 1")).outcome == "wrongly_answered"
    assert grade(q("clarify"), Prediction("refusal")).outcome == "partial_refusal"


def test_the_summary_counts_what_it_should(fake_db):
    verdicts = [grade(q(qid="A"), Prediction("sql", sql="SELECT 5 /*pred*/"), gold_rows=[(5,)]),
                grade(q(qid="B"), Prediction("sql", sql="DROP TABLE x"), gold_rows=[(5,)]),
                grade(q("unanswerable", qid="C"), Prediction("refusal")),
                grade(q("unanswerable", qid="D"), Prediction("sql", sql="SELECT 1"))]
    s = summarize(verdicts)
    assert s["answerable"] == 2 and s["correct"] == 1 and s["execution_accuracy"] == 0.5
    assert s["unsafe"] == 1 and s["should_decline"] == 2 and s["declined_correctly"] == 1 and s["invented_answers"] == 1


# ---- the SQL safety check
@pytest.mark.parametrize("sql", [
    "SELECT * FROM cust_master",
    "select count(*) from ord_hdr where ord_status = 'C';",
    "WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "SELECT a FROM (SELECT 1 AS a) s UNION SELECT 2",
    "SELECT c.cust_nm FROM cust_master c JOIN ord_hdr o ON o.cust_id = c.cust_id WHERE o.ord_dt > '2026-01-01'",
])
def test_plain_selects_are_allowed(sql):
    assert check_select(sql).ok, check_select(sql).reason


@pytest.mark.parametrize("sql", [
    "", "   ", "DROP TABLE emp", "DELETE FROM emp", "UPDATE emp SET salary_amt = 0", "INSERT INTO emp VALUES (1)",
    "SELECT 1; DROP TABLE emp", "SELECT * FROM emp INTO OUTFILE '/tmp/x'", "SELECT SLEEP(10)", "SELECT BENCHMARK(100000000, MD5('a'))",
    "SELECT LOAD_FILE('/etc/passwd')", "SELECT * FROM emp FOR UPDATE", "CREATE TABLE x (a INT)", "ALTER TABLE emp ADD c INT",
    "SHOW TABLES", "not sql at all ???",
])
def test_everything_else_is_refused(sql):
    assert not check_select(sql).ok


def test_the_reason_is_human_readable():
    assert "SELECT" in check_select("DROP TABLE emp").reason
    assert "statements" in check_select("SELECT 1; SELECT 2").reason


def test_a_trailing_comment_after_the_semicolon_is_not_a_second_statement():
    assert check_select("SELECT COUNT(*) FROM ord_hdr;  -- 1 = Sunday, 7 = Saturday").ok
    assert check_select("SELECT 1;\n/* note */").ok
    assert check_select("SELECT 1 -- inline note").ok


def test_text_that_is_not_valid_mysql_is_a_syntax_failure_not_an_unsafe_one(fake_db):
    assert check_select("SELECT COUNT(*) FROM t WHERE a = 1 LEFT JOIN u ON t.a = u.a WHERE u.b IS NULL").kind == "syntax"
    assert check_select("DROP TABLE emp").kind == "policy"
    v = grade(q(), Prediction("sql", sql="SELECT 1 FROM t WHERE a = 1 LEFT JOIN u ON t.a = u.a WHERE u.b IS NULL"), conn=None, gold_rows=[(5,)])
    assert v.outcome == "sql_error"
    assert grade(q(), Prediction("sql", sql="DROP TABLE emp"), conn=None, gold_rows=[(5,)]).outcome == "unsafe"


def test_a_real_second_statement_is_still_refused_even_with_a_comment():
    assert not check_select("SELECT 1; DROP TABLE emp; -- cleanup").ok
    assert not check_select("SELECT 1; SELECT 2 -- two selects").ok
