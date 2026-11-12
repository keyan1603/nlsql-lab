"""The schema as a model will read it. Two variants, because documentation is one of the things the lab measures, and two scopes:
the 11 core tables, or the core plus the 11 extension tables (22 tables, a wider and more confusable schema)."""

from __future__ import annotations

import re

from nlsql.config import ROOT

_COMMENT_COLUMN = re.compile(r"\s+COMMENT\s+'[^']*'")


def schema_ddl(extended: bool = False) -> str:
    text = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    if extended:
        text += "\n" + (ROOT / "sql" / "schema_ext.sql").read_text(encoding="utf-8")
    return text


def schema_for_prompt(include_comments: bool = True, extended: bool = False) -> str:
    """CREATE TABLE statements only (no DROP, no file comments). With include_comments=False every COMMENT is removed,
    leaving just the bare, abbreviated names and types."""
    text = schema_ddl(extended)
    statements = [s.strip() for s in ("\n".join(l for l in text.splitlines() if not l.strip().startswith("--")) + "\n").split(";\n")]
    creates = [s for s in statements if s.upper().startswith("CREATE TABLE")]
    out = []
    for stmt in creates:
        if not include_comments:
            stmt = _COMMENT_COLUMN.sub("", stmt)
            stmt = re.sub(r"\)\s*COMMENT\s*=\s*'[^']*'\s*$", ")", stmt)
        out.append(stmt + ";")
    return "\n\n".join(out)


def compact_schema(tables) -> str:
    """One line per table: name, what it is, and every column with its comment. No types, keys or example values. This is the schema as the
    fine-tuned model reads it (the model learned the types and the join habits from its training pairs); about a third of the size of the
    CREATE TABLE text."""
    lines = []
    for t in tables:
        cols = "; ".join(c.name + (f" ({c.comment})" if c.comment else "") for c in t.columns)
        fk = ("  FK: " + ", ".join(f"{c}->{rt}.{rc}" for c, rt, rc in t.fks)) if t.fks else ""
        lines.append(f"{t.name} - {t.comment}: {cols}{fk}")
    return "\n".join(lines)
