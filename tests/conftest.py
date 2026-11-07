import pytest


@pytest.fixture(scope="session")
def reader():
    """A read-only connection to the lab database, or a skip when it is not set up on this machine."""
    from nlsql import db
    try:
        conn = db.connect("reader")
        db.scalar(conn, "SELECT COUNT(*) FROM ord_hdr")
    except Exception as exc:                                  # not configured, not running or not loaded: all the same to a test
        pytest.skip(f"lab database not available: {str(exc)[:80]}")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def admin():
    from nlsql import db
    try:
        conn = db.connect("admin")
    except Exception as exc:
        pytest.skip(f"lab database not available: {str(exc)[:80]}")
    yield conn
    conn.close()
