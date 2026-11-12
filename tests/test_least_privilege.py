"""The database-level backstop. These checks only apply after an administrator has run setup/least_privilege.sql;
before that they are skipped, because the lab's reader still has SELECT on the whole database."""

import pytest

from nlsql import db


def _applied(conn) -> bool:
    try:
        db.run_query(conn, "SELECT natl_id FROM emp LIMIT 1")
        return False
    except Exception as exc:
        return "denied" in str(exc).lower()


@pytest.fixture
def narrowed(reader):
    if not _applied(reader):
        pytest.skip("setup/least_privilege.sql has not been applied to this database")
    return reader


@pytest.mark.integration
def test_the_database_itself_refuses_the_two_blocked_columns(narrowed):
    for sql in ("SELECT natl_id FROM emp", "SELECT salary_amt FROM emp", "SELECT * FROM emp",
                "SELECT 1 /*!50000 UNION SELECT salary_amt FROM emp */"):
        with pytest.raises(Exception, match="(?i)denied"):
            db.run_query(narrowed, sql)


@pytest.mark.integration
def test_everything_the_guard_may_ask_for_still_works(narrowed):
    assert db.run_query(narrowed, "SELECT emp_id, emp_nm, dept_cd FROM emp").rows
    assert db.run_query(narrowed, "SELECT COUNT(*) FROM emp").rows == [(24,)]
    assert db.run_query(narrowed, "SELECT email_addr FROM cust_master LIMIT 1").rows
