"""The first line of defence for generated SQL: parse it, allow exactly one read-only SELECT, refuse the rest.

This is deliberately a deny-by-default allow-list built on a real SQL parser, not a regular expression. It is the first of
several layers (the read-only database account and the server-side time limit are the others); Phase 4 attacks it on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

FORBIDDEN_FUNCTIONS = {"SLEEP", "BENCHMARK", "LOAD_FILE", "GET_LOCK", "RELEASE_LOCK", "SYS_EXEC", "SYS_EVAL"}


@dataclass(frozen=True)
class SafetyVerdict:
    ok: bool
    reason: str = ""


def check_select(sql: str) -> SafetyVerdict:
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        return SafetyVerdict(False, "empty statement")
    try:
        statements = sqlglot.parse(text, read="mysql")
    except sqlglot.errors.ParseError as exc:
        return SafetyVerdict(False, f"does not parse as MySQL: {str(exc)[:120]}")
    # a trailing comment after the semicolon parses as a comment-only 'statement' (exp.Semicolon); it executes nothing, so it is ignored
    statements = [s for s in statements if s is not None and not isinstance(s, exp.Semicolon)]
    if len(statements) != 1:
        return SafetyVerdict(False, f"{len(statements)} statements; exactly one is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        return SafetyVerdict(False, f"only SELECT is allowed, got {type(tree).__name__}")
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Into)):
            return SafetyVerdict(False, f"{type(node).__name__} is not allowed")
        if isinstance(node, exp.Lock):
            return SafetyVerdict(False, "locking reads are not allowed")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = (node.name or node.sql_name() or "").upper()
            if name in FORBIDDEN_FUNCTIONS:
                return SafetyVerdict(False, f"function {name} is not allowed")
    return SafetyVerdict(True)
