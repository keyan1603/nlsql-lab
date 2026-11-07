"""MySQL access. The reader connection is read-only twice over: the account has only SELECT, and the session
is set to a read-only transaction. Every query also gets a server-side time limit."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pymysql

from nlsql.config import Settings, load_settings

DEFAULT_TIMEOUT_MS = 10_000


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    elapsed_ms: float


class QueryTimeout(Exception):
    pass


def connect(role: str = "reader", settings: Settings | None = None):
    s = settings or load_settings()
    user, password = s.credentials(role)
    conn = pymysql.connect(host=s.host, port=s.port, user=user, password=password, database=s.database,
                           charset="utf8mb4", autocommit=True, connect_timeout=5, read_timeout=30)
    if role == "reader":
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def run_query(conn, sql: str, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_rows: int = 10_000) -> QueryResult:
    """Run one statement and return all rows. MAX_EXECUTION_TIME applies to SELECT statements, which is all this path runs."""
    with conn.cursor() as cur:
        cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")
        t0 = time.perf_counter()
        try:
            cur.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
        except pymysql.err.OperationalError as exc:
            if exc.args and exc.args[0] == 3024:              # ER_QUERY_TIMEOUT
                raise QueryTimeout(f"query exceeded {timeout_ms} ms") from exc
            raise
        elapsed = (time.perf_counter() - t0) * 1000
        if len(rows) > max_rows:
            raise ValueError(f"query returned more than {max_rows} rows")
        cols = [d[0] for d in cur.description] if cur.description else []
        return QueryResult(columns=cols, rows=[tuple(r) for r in rows], elapsed_ms=elapsed)


def execute_script(conn, script: str) -> None:
    """Run a multi-statement DDL/DML script on the admin connection (used by the loader only)."""
    statements = [s.strip() for s in _split_statements(script) if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)


def _split_statements(script: str) -> list[str]:
    """Split on a semicolon that ends a line. Column comments contain semicolons mid-line, which this ignores;
    a test checks that the schema file splits into exactly the expected number of statements."""
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    return ("\n".join(lines) + "\n").split(";\n")


def scalar(conn, sql: str) -> Any:
    return run_query(conn, sql).rows[0][0]
