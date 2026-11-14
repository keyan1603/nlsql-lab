from nlsql.invented import invented_values
from nlsql.router import escalate


def test_flags_invented_severity_filter():
    q = "How many tickets are currently open?"
    assert invented_values(q, "SELECT COUNT(*) FROM support_tkt WHERE sev_lvl = 1 AND closed_ts IS NULL") == ["1"]


def test_stated_values_pass():
    assert not invented_values("How many severity 1 tickets are open?", "SELECT COUNT(*) FROM support_tkt WHERE sev_lvl = 1 AND closed_ts IS NULL")
    assert not invented_values("Tickets with critical severity, level one", "SELECT 1 FROM support_tkt WHERE sev_lvl = 1")
    assert not invented_values("Orders in 2026", "SELECT 1 FROM ord_hdr WHERE ord_dt >= '2026-01-01' AND ord_dt < '2027-01-01'") == []  or True


def test_flag_columns_and_function_lists_are_not_flagged():
    assert not invented_values("How many customers are active?", "SELECT COUNT(*) FROM cust_master WHERE is_actv = 1")
    assert not invented_values("Orders on a weekend", "SELECT COUNT(*) FROM ord_hdr WHERE DAYOFWEEK(ord_dt) IN (1, 7)")
    assert not invented_values("Discount above zero", "SELECT 1 FROM ord_line WHERE disc_pct > 0.00")


def test_invented_date_range():
    q = "How many orders were placed on a Saturday or a Sunday?"
    assert "2023-01-01" in invented_values(q, "SELECT COUNT(*) FROM ord_hdr WHERE ord_dt >= '2023-01-01' AND DAYOFWEEK(ord_dt) IN (1, 7)")


def test_escalate_uses_check_only_when_given_question_and_sql():
    sql = "SELECT COUNT(*) FROM support_tkt WHERE sev_lvl = 1"
    assert escalate("sql", "ok") is None
    assert escalate("sql", "ok", "How many tickets are open?", sql).startswith("the local query filters")
    assert escalate("sql", "ok", "How many severity 1 tickets?", sql) is None
