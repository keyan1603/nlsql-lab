"""The schema as a model will read it. Two variants, because documentation is one of the things Phase 3 measures."""

from __future__ import annotations

import re

from nlsql.config import ROOT

_COMMENT_COLUMN = re.compile(r"\s+COMMENT\s+'[^']*'")
_COMMENT_TABLE = re.compile(r"\)\s*COMMENT\s*=\s*'[^']*';")


def schema_ddl() -> str:
    return (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")


def schema_for_prompt(include_comments: bool = True) -> str:
    """CREATE TABLE statements only (no DROP, no file comments). With include_comments=False every COMMENT is removed,
    leaving just the bare, abbreviated names and types."""
    text = schema_ddl()
    statements = [s.strip() for s in ("\n".join(l for l in text.splitlines() if not l.strip().startswith("--")) + "\n").split(";\n")]
    creates = [s for s in statements if s.upper().startswith("CREATE TABLE")]
    out = []
    for stmt in creates:
        if not include_comments:
            stmt = _COMMENT_COLUMN.sub("", stmt)
            stmt = re.sub(r"\)\s*COMMENT\s*=\s*'[^']*'\s*$", ")", stmt)
        out.append(stmt + ";")
    return "\n\n".join(out)
