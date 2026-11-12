"""The governed executor, tested without a database: what each layer refuses, what masking rewrites, and what the audit log keeps."""

import json

import pytest

from nlsql.guard import Guard, Policy


@pytest.fixture
def guard(tmp_path):
    return Guard(Policy(), audit_path=tmp_path / "audit.jsonl")


def review(g, sql):
    refusal, run, masked = g.review(sql)
    return refusal, run, masked


# ---- text layer
@pytest.mark.parametrize("sql", [
    "SELECT 1 /*!50000 UNION SELECT salary_amt FROM emp */",
    "SELECT /*!50000 SLEEP(2) */ 1",
    "SELECT /*+ MAX_EXECUTION_TIME(0) */ COUNT(*) FROM web_event",
])
def test_comments_mysql_executes_are_refused_at_the_text_layer(guard, sql):
    refusal, _, _ = review(guard, sql)
    assert refusal and refusal.layer == "text"


def test_what_runs_is_the_regenerated_sql_not_the_text_the_model_wrote(guard):
    refusal, run, _ = review(guard, "SELECT cust_id FROM cust_master -- ; DROP TABLE emp")
    assert refusal is None and "DROP" not in run and "--" not in run


def test_regeneration_alone_would_drop_a_versioned_comment():
    import sqlglot
    tree = sqlglot.parse_one("SELECT 1 /*!50000 UNION SELECT 2 */", read="mysql")
    assert "UNION" not in tree.sql(dialect="mysql", comments=False)


# ---- parser layer is still in force
def test_the_parser_layer_still_refuses_writes_and_stacking(guard):
    for sql in ("DROP TABLE emp", "SELECT 1; DROP TABLE emp", "SELECT * FROM web_event FOR UPDATE", "SELECT SLEEP(5)"):
        refusal, _, _ = review(guard, sql)
        assert refusal and refusal.layer == "parser", sql


# ---- tables, variables, information functions
@pytest.mark.parametrize("sql", [
    "SELECT * FROM information_schema.tables",
    "SELECT user FROM mysql.user",
    "SELECT * FROM performance_schema.threads",
    "SELECT * FROM other_db.secrets",
    "SELECT * FROM nlsql_lab.not_a_lab_table",
    "SELECT @@version",
    "SELECT @x",
    "SELECT USER()",
    "SELECT CURRENT_USER()",
    "SELECT DATABASE()",
    "SELECT VERSION()",
    "SELECT CONNECTION_ID()",
])
def test_system_tables_variables_and_server_functions_are_refused(guard, sql):
    refusal, _, _ = review(guard, sql)
    assert refusal and refusal.layer == "policy", sql


def test_a_cte_name_is_not_mistaken_for_an_unknown_table(guard):
    refusal, run, _ = review(guard, "WITH t AS (SELECT cust_id FROM cust_master) SELECT COUNT(*) FROM t")
    assert refusal is None and "WITH t AS" in run


def test_the_lab_database_may_be_named_explicitly(guard):
    assert review(guard, "SELECT COUNT(*) FROM nlsql_lab.emp")[0] is None


# ---- personal data
@pytest.mark.parametrize("sql", [
    "SELECT natl_id FROM emp",
    "SELECT emp_nm, salary_amt FROM emp",
    "SELECT `NATL_ID` FROM `emp`",
    "SELECT AVG(salary_amt) FROM emp",
    "SELECT emp_id FROM emp WHERE salary_amt > 100000",
    "WITH t AS (SELECT natl_id AS a FROM emp) SELECT a FROM t",
    "SELECT dept_cd, MAX(salary_amt) FROM emp GROUP BY dept_cd",
])
def test_denied_columns_are_refused_wherever_they_appear(guard, sql):
    refusal, _, _ = review(guard, sql)
    assert refusal and refusal.layer == "policy" and "personal" in refusal.reason, sql


@pytest.mark.parametrize("sql", [
    "SELECT * FROM emp",
    "SELECT e.* FROM emp e",
    "SELECT x.natl_id FROM (SELECT * FROM emp) x",
    "SELECT * FROM cust_master",
])
def test_star_on_a_table_with_personal_columns_is_refused(guard, sql):
    refusal, _, _ = review(guard, sql)
    assert refusal and refusal.layer == "policy", sql


@pytest.mark.parametrize("sql", [
    "SELECT LOWER(email_addr) FROM cust_master",
    "SELECT CONCAT(email_addr, '') FROM cust_master",
    "SELECT cust_id FROM cust_master WHERE email_addr LIKE 'a%'",
    "SELECT cust_id FROM cust_master ORDER BY phone_no",
    "SELECT COUNT(DISTINCT email_addr) FROM cust_master",
])
def test_masked_columns_cannot_be_used_to_filter_sort_or_compute(guard, sql):
    refusal, _, _ = review(guard, sql)
    assert refusal and refusal.layer == "policy" and "masked" in refusal.reason, sql


def test_a_direct_projection_of_a_masked_column_is_rewritten_and_keeps_its_name(guard):
    refusal, run, masked = review(guard, "SELECT email_addr FROM cust_master WHERE cust_id = 'C-1002'")
    assert refusal is None and masked == ["email_addr"]
    assert "SUBSTRING_INDEX" in run and "AS email_addr" in run and "WHERE cust_id = 'C-1002'" in run


def test_masking_follows_an_alias_and_a_qualifier(guard):
    _, run, masked = review(guard, "SELECT c.phone_no AS tel FROM cust_master c")
    assert masked == ["phone_no"] and "AS tel" in run and "c.phone_no" in run


def test_masking_applies_inside_a_cte_so_the_outer_query_only_sees_masked_values(guard):
    refusal, run, masked = review(guard, "WITH t AS (SELECT email_addr FROM cust_master) SELECT email_addr FROM t")
    assert refusal is None and masked and "SUBSTRING_INDEX" in run


def test_harmless_queries_on_tables_with_personal_columns_are_untouched(guard):
    for sql in ("SELECT emp_id, emp_nm FROM emp", "SELECT COUNT(*) FROM emp", "SELECT tier_cd, COUNT(*) FROM cust_master GROUP BY tier_cd"):
        refusal, run, masked = review(guard, sql)
        assert refusal is None and masked == [], sql


def test_the_policy_is_configurable(tmp_path):
    open_policy = Policy(deny_columns=frozenset(), mask_columns={})
    g = Guard(open_policy, audit_path=tmp_path / "a.jsonl")
    assert review(g, "SELECT salary_amt FROM emp")[0] is None


# ---- audit, with a scripted database
class FakeConn:
    pass


def test_every_decision_is_audited_and_never_contains_result_values(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from nlsql import guard as g
    monkeypatch.setattr(g.db, "run_query", lambda conn, sql, **kw: SimpleNamespace(columns=["a"], rows=[("secret-value",)], elapsed_ms=3.0))
    guard = Guard(Policy(), audit_path=tmp_path / "audit.jsonl")
    ok = guard.execute(FakeConn(), "how many?", "SELECT cust_id FROM cust_master")
    bad = guard.execute(FakeConn(), "drop it", "DROP TABLE emp")
    assert ok.decision == "allowed" and bad.decision == "refused" and bad.layer == "parser"
    lines = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [l["decision"] for l in lines] == ["allowed", "refused"]
    assert lines[0]["question"] == "how many?" and lines[0]["rows"] == 1 and lines[1]["layer"] == "parser"
    assert "secret-value" not in (tmp_path / "audit.jsonl").read_text()


def test_a_database_error_timeout_and_row_cap_are_reported_by_layer(tmp_path, monkeypatch):
    from nlsql import guard as g, db

    def boom(kind):
        def run(conn, sql, **kw):
            raise {"timeout": db.QueryTimeout("slow"), "cap": ValueError("big"), "error": RuntimeError("1146 no table")}[kind]
        return run
    guard = Guard(Policy(), audit_path=tmp_path / "audit.jsonl")
    for kind, decision in (("timeout", "timeout"), ("cap", "capped"), ("error", "refused")):
        monkeypatch.setattr(g.db, "run_query", boom(kind))
        r = guard.execute(FakeConn(), "q", "SELECT cust_id FROM cust_master")
        assert r.decision == decision and r.layer == "database", kind
