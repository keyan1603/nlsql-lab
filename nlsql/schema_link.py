"""Help the model read the schema: parse it once, show it in the M-Schema layout with example values, and (optionally) show only
the tables a question is likely to need.

M-Schema is the layout the XiYan authors recommend for their model: one block per table, every column with its type, its comment
and a few real values, and the foreign keys listed at the end. Example values matter most for coded columns (a status stored as
'C', a tier stored as 'P'), which is where small models guess.

Table selection is lexical and uses nothing but the question and the schema text (names, comments, example values). It never
sees the gold query. The gold query is used only afterwards, in scripts/check_linking.py, to MEASURE how often the tables a
query needs were kept.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from nlsql.config import ROOT
from nlsql.schema_text import schema_ddl

EXAMPLES_FILE = ROOT / "data" / "schema_examples.json"
_SENSITIVE_NAME = re.compile(r"email|phone|natl|salary|ssn|passport", re.IGNORECASE)
_STOP = set("the a an of in on at to for and or by is are was were be been with from per that this those these what which who whom how many much "
            "did does do has have had show list give me us our their its it as than then there any all each every most more least less top "
            "number count total average name names who whose when where during between over under after before last first".split())


@dataclass
class Column:
    name: str
    type: str
    comment: str = ""
    pk: bool = False


@dataclass
class Table:
    name: str
    comment: str
    columns: list[Column] = field(default_factory=list)
    fks: list[tuple[str, str, str]] = field(default_factory=list)      # (column, referenced table, referenced column)


_TABLE = re.compile(r"CREATE TABLE (\w+) \((.*?)\n\)(?: COMMENT = '(.*?)')?;", re.DOTALL)
_COLUMN = re.compile(r"^(\w+)\s+(\w+(?:\([^)]*\))?(?:\s+UNSIGNED)?)\b(.*)$", re.IGNORECASE)
_COMMENT = re.compile(r"COMMENT\s+'(.*)'\s*,?\s*$")
_FK = re.compile(r"FOREIGN KEY \((\w+)\) REFERENCES (\w+) \((\w+)\)", re.IGNORECASE)
_PK = re.compile(r"PRIMARY KEY \(([^)]*)\)", re.IGNORECASE)


def parse_schema(extended: bool = True) -> list[Table]:
    text = "\n".join(l for l in schema_ddl(extended).splitlines() if not l.strip().startswith("--"))
    tables = []
    for name, body, tcomment in _TABLE.findall(text):
        t = Table(name, (tcomment or "").replace("''", "'"))
        pk_cols: set = set()
        for raw in body.splitlines():
            line = raw.strip()
            if not line:
                continue
            up = line.upper()
            if up.startswith("PRIMARY KEY"):
                pk_cols = {c.strip() for c in _PK.search(line).group(1).split(",")}
            elif up.startswith(("KEY ", "UNIQUE", "INDEX", "CONSTRAINT", "FOREIGN KEY")):
                fk = _FK.search(line)
                if fk:
                    t.fks.append((fk.group(1), fk.group(2), fk.group(3)))
            else:
                m = _COLUMN.match(line)
                if m:
                    c = _COMMENT.search(m.group(3))
                    t.columns.append(Column(m.group(1), m.group(2).upper(), c.group(1).replace("''", "'") if c else ""))
        for c in t.columns:
            c.pk = c.name in pk_cols
        tables.append(t)
    return tables


def load_examples() -> dict:
    return json.loads(EXAMPLES_FILE.read_text(encoding="utf-8")) if EXAMPLES_FILE.exists() else {}


def is_sensitive(table: Table, col: Column) -> bool:
    return bool(_SENSITIVE_NAME.search(col.name)) or "sensitive" in col.comment.lower()


def m_schema(tables: list[Table], examples: dict | None = None, db_name: str = "nlsql") -> str:
    examples = examples if examples is not None else load_examples()
    out = [f"【DB_id】 {db_name}", "【Schema】"]
    for t in tables:
        out.append(f"# Table: {t.name}" + (f", {t.comment}" if t.comment else ""))
        out.append("[")
        for c in t.columns:
            parts = [f"{c.name}:{c.type}"]
            if c.comment:
                parts.append(c.comment)
            if c.pk:
                parts.append("Primary Key")
            vals = (examples.get(t.name) or {}).get(c.name)
            if vals:
                parts.append("Examples: [" + ", ".join(str(v) for v in vals) + "]")
            out.append("(" + ", ".join(parts) + "),")
        out.append("]")
    shown = {t.name for t in tables}
    fks = [f"{t.name}.{c}={rt}.{rc}" for t in tables for c, rt, rc in t.fks if rt in shown]
    if fks:
        out += ["【Foreign keys】", *fks]
    return "\n".join(out)


def _stem(w: str) -> str:
    for suf in ("ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) >= 2]


def _match(q: str, d: str) -> bool:
    if q == d:
        return True
    short, long_ = (q, d) if len(q) <= len(d) else (d, q)
    return len(short) >= 3 and long_.startswith(short)


def select_tables(question: str, tables: list[Table], k: int = 5, examples: dict | None = None) -> list[Table]:
    """The k best-matching tables, plus the tables their foreign keys point at and the code lookup table, in schema order."""
    examples = examples if examples is not None else load_examples()
    docs: dict = {}
    for t in tables:
        fields = {"name": set(tokens(t.name.replace("_", " "))), "tcomment": set(tokens(t.comment)), "cols": set(), "ccomments": set(), "values": set()}
        for c in t.columns:
            fields["cols"] |= set(tokens(c.name.replace("_", " ")))
            fields["ccomments"] |= set(tokens(c.comment))
            if not is_sensitive(t, c):
                for v in (examples.get(t.name) or {}).get(c.name, []):
                    fields["values"] |= set(tokens(str(v)))
        docs[t.name] = fields
    weights = {"name": 3.0, "tcomment": 2.0, "cols": 1.0, "ccomments": 1.0, "values": 1.5}
    df: dict = {}
    for f in docs.values():
        for tok in set().union(*f.values()):
            df[tok] = df.get(tok, 0) + 1
    n = len(tables)
    q_tokens = set(tokens(question))
    scores = {}
    for name, f in docs.items():
        s = 0.0
        for qt in q_tokens:
            best = 0.0
            for field_name, vocab in f.items():
                if any(_match(qt, d) for d in vocab):
                    best = max(best, weights[field_name])
            if best:
                matched_df = sum(1 for g in docs.values() if any(_match(qt, d) for v in g.values() for d in v))
                s += best * math.log(1 + n / max(matched_df, 1))
        scores[name] = s
    top = [name for name, s in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])) if s > 0][:k]
    keep = set(top)
    by_name = {t.name: t for t in tables}
    for name in list(top):
        keep |= {rt for _, rt, _ in by_name[name].fks}
    if "code_lookup" in by_name:
        keep.add("code_lookup")
    return [t for t in tables if t.name in keep]
