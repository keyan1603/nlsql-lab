"""The governed executor: the one place generated SQL passes through on its way to the database.

Layers, in order. Each is a separate decision that is written to the audit log, so a refusal says which layer made it.

    text     comments that MySQL treats as code (/*! ... */, /*+ ... */) are refused outright
    parser   nlsql.safety.check_select: one read-only SELECT, no locking reads, no sleep or file functions
    policy   tables must be lab tables, no system variables or server-information functions, personal columns
             are denied or masked, SELECT * is refused on tables that hold personal columns
    rewrite  what runs is the SQL regenerated from the parsed tree, never the text the model wrote, so what the policy
             inspected and what MySQL executes cannot differ (comments and anything the parser skipped are gone)
    database the read-only account, the server-side time limit and a row cap

The audit record holds the question, the SQL, the decision, the layer, the row count and the timing. It never holds result values.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import sqlglot
from sqlglot import exp

from nlsql import db
from nlsql.config import ROOT
from nlsql.safety import check_select

LAB_TABLES = frozenset({
    "code_lookup", "emp", "cust_master", "prod_catalog", "fx_rate", "ord_hdr", "ord_line", "refund_req", "support_tkt", "tkt_event",
    "policy_rule", "warehouse", "inventory", "inv_move", "shipment", "payment", "promo", "ord_promo", "web_event", "cust_segment_hist",
    "supplier", "prod_supplier",
})
PERSONAL_TABLES = frozenset({"emp", "cust_master"})

# Server-information functions and variables: not data, but they map the server for an attacker.
INFO_FUNCTIONS = {"USER", "CURRENTUSER", "SESSIONUSER", "SYSTEMUSER", "DATABASE", "SCHEMA", "CURRENTSCHEMA", "VERSION", "CURRENTVERSION",
                  "CONNECTIONID", "LASTINSERTID", "ROWCOUNT", "FOUNDROWS", "CURRENTROLE"}

_HINT_OR_VERSIONED = re.compile(r"/\*[!+]|/\*M!")


@dataclass(frozen=True)
class Policy:
    """What the question-answering path may see. Defaults suit the lab schema."""
    allowed_tables: frozenset = LAB_TABLES
    deny_columns: frozenset = frozenset({"salary_amt", "natl_id"})
    # column -> SQL template with {c} for the (qualified) column; direct projections of these are returned masked
    mask_columns: dict = field(default_factory=lambda: {
        "email_addr": "CONCAT(LEFT({c}, 1), '***@', SUBSTRING_INDEX({c}, '@', -1))",
        "phone_no": "CONCAT('***', RIGHT({c}, 2))",
    })
    personal_tables: frozenset = PERSONAL_TABLES
    max_rows: int = 1000


@dataclass
class GuardResult:
    decision: str                   # allowed | masked | refused | timeout | capped
    layer: str = ""                 # which layer decided a refusal: text | parser | policy | database
    reason: str = ""
    executed_sql: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    elapsed_ms: float = 0.0
    masked_columns: list = field(default_factory=list)


def _refuse(layer: str, reason: str) -> GuardResult:
    return GuardResult("refused", layer, reason)


class Guard:
    def __init__(self, policy: Policy | None = None, audit_path: Path | None = None, timeout_ms: int = db.DEFAULT_TIMEOUT_MS, role: str = "reader"):
        self.policy = policy or Policy()
        self.audit_path = Path(audit_path) if audit_path else ROOT / "runs" / "audit.jsonl"
        self.timeout_ms = timeout_ms
        self.role = role

    # ---- decide without touching the database
    def review(self, sql: str) -> tuple[GuardResult | None, str, list]:
        """Return (refusal or None, SQL to run, names of masked columns). Pure: no database access."""
        if _HINT_OR_VERSIONED.search(sql or ""):
            return _refuse("text", "comments that MySQL executes (/*! */, /*+ */) are not allowed"), "", []
        v = check_select(sql)
        if not v.ok:
            return _refuse("parser", v.reason), "", []
        tree = sqlglot.parse_one(sql.strip().rstrip(";"), read="mysql")
        refusal = self._policy_checks(tree)
        if refusal:
            return refusal, "", []
        masked = self._mask(tree)
        return None, tree.sql(dialect="mysql", comments=False), masked

    def _policy_checks(self, tree: exp.Expression) -> GuardResult | None:
        p = self.policy
        ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        for t in tree.find_all(exp.Table):
            name = (t.name or "").lower()
            if name in ctes and not t.db:
                continue
            if not name or name not in p.allowed_tables:
                return _refuse("policy", f"table {t.sql(dialect='mysql')!r} is not one of the lab tables")
            if t.db and t.db.lower() != "nlsql_lab":
                return _refuse("policy", f"database {t.db!r} is not allowed")
        for node in tree.walk():
            if isinstance(node, (exp.SessionParameter, exp.Parameter)):
                return _refuse("policy", "system and session variables are not allowed")
            if isinstance(node, exp.Hint):
                return _refuse("policy", "optimizer hints are not allowed")
            if isinstance(node, exp.Func):
                key = (node.name if isinstance(node, exp.Anonymous) else node.key or "").upper().replace("_", "")
                if key in INFO_FUNCTIONS:
                    return _refuse("policy", f"server-information function {key} is not allowed")
        # SELECT * (or t.*) on a table that holds personal columns would return them under another name
        for sel in tree.find_all(exp.Select):
            if any(isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star)) for e in sel.expressions):
                tables = {(t.name or "").lower() for t in sel.find_all(exp.Table) if t.parent_select is sel}
                if tables & p.personal_tables:
                    return _refuse("policy", "SELECT * on a table with personal columns is not allowed; name the columns you need")
        allowed_projections = {id(c) for c in self._direct_projections(tree) if c.name.lower() in p.mask_columns}
        for col in tree.find_all(exp.Column):
            name = col.name.lower()
            if name in p.deny_columns:
                return _refuse("policy", f"column {name} holds personal data and is not available")
            if name in p.mask_columns and id(col) not in allowed_projections:
                return _refuse("policy", f"column {name} may only be shown masked, not used to filter, sort, join or compute")
        return None

    @staticmethod
    def _direct_projections(tree: exp.Expression):
        for sel in tree.find_all(exp.Select):
            for e in sel.expressions:
                inner = e.this if isinstance(e, exp.Alias) else e
                if isinstance(inner, exp.Column):
                    yield inner

    def _mask(self, tree: exp.Expression) -> list:
        masked = []
        for sel in list(tree.find_all(exp.Select)):
            for e in list(sel.expressions):
                alias = e.alias if isinstance(e, exp.Alias) else None
                inner = e.this if isinstance(e, exp.Alias) else e
                if isinstance(inner, exp.Column) and inner.name.lower() in self.policy.mask_columns:
                    template = self.policy.mask_columns[inner.name.lower()]
                    expr = sqlglot.parse_one(template.format(c=inner.sql(dialect="mysql")), read="mysql")
                    e.replace(exp.alias_(expr, alias or inner.name, quoted=False))
                    masked.append(inner.name.lower())
        return masked

    # ---- run
    def execute(self, conn, question: str, sql: str) -> GuardResult:
        t0 = time.perf_counter()
        refusal, to_run, masked = self.review(sql)
        if refusal:
            self._audit(question, sql, refusal)
            return refusal
        try:
            res = db.run_query(conn, to_run, timeout_ms=self.timeout_ms, max_rows=self.policy.max_rows)
            out = GuardResult("masked" if masked else "allowed", "", "", to_run, res.columns, res.rows, res.elapsed_ms, masked)
        except db.QueryTimeout as exc:
            out = GuardResult("timeout", "database", str(exc), to_run, elapsed_ms=(time.perf_counter() - t0) * 1000)
        except ValueError:
            out = GuardResult("capped", "database", f"more than {self.policy.max_rows} rows; add a filter or a LIMIT", to_run,
                              elapsed_ms=(time.perf_counter() - t0) * 1000)
        except Exception as exc:                                      # a database error is a refusal by the database layer
            out = GuardResult("refused", "database", f"{type(exc).__name__}: {str(exc)[:160]}", to_run, elapsed_ms=(time.perf_counter() - t0) * 1000)
        self._audit(question, sql, out)
        return out

    def _audit(self, question: str, sql: str, r: GuardResult) -> None:
        record = {
            "id": uuid.uuid4().hex[:12], "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "role": self.role,
            "question": question, "sql": sql, "sql_sha256": hashlib.sha256((sql or "").encode()).hexdigest()[:16],
            "decision": r.decision, "layer": r.layer, "reason": r.reason, "rows": len(r.rows), "columns": r.columns,
            "masked": r.masked_columns, "elapsed_ms": round(r.elapsed_ms),
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
