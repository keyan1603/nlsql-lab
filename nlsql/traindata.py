"""Pure helpers for building a training set from a teacher model: parsing its replies, normalising text, and keeping the training
data away from the test questions. No database or network is used here, so all of it is unit tested.

The leak rules matter more than anything else in this module. A fine-tuned model that has seen the test questions (or a light
rewording of them) will score well for the wrong reason, so a training pair is dropped when its question or its query is the same as,
or very close to, any question in the evaluation files.
"""

from __future__ import annotations

import json
import re

import sqlglot
from sqlglot import exp

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_WORD = re.compile(r"[a-z0-9_\-\.']+")
_STOP = set("the a an of in on at to for and or by is are was were be been with from per that this those these what which who how many much did does do has have had "
            "show me us our their its it as than then there any all each every number count total please give list".split())


def parse_json_array(text: str) -> list[dict]:
    """The first JSON array of objects in a model reply (fences and chatter around it are ignored). Bad replies give []."""
    text = _FENCE.sub("", text.strip())
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def norm_question(q: str) -> str:
    return " ".join(_WORD.findall(q.lower()))


def question_tokens(q: str) -> frozenset:
    return frozenset(w for w in _WORD.findall(q.lower()) if w not in _STOP and len(w) > 1)


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def canonical_sql(sql: str) -> str:
    """The query with whitespace, case, aliases-in-comments and formatting removed, so two spellings of one query compare equal."""
    try:
        return sqlglot.parse_one(sql, read="mysql").sql(dialect="mysql", normalize=True, comments=False)
    except Exception:
        return " ".join(sql.lower().split())


def literals_and_tables(sql: str) -> tuple[frozenset, frozenset]:
    try:
        tree = sqlglot.parse_one(sql, read="mysql")
    except Exception:
        return frozenset(), frozenset()
    lits = frozenset(str(n.this) for n in tree.find_all(exp.Literal))
    tabs = frozenset(t.name for t in tree.find_all(exp.Table))
    return lits, tabs


class LeakFilter:
    """Built from the test questions (with their gold queries where they have one). `why(question, sql)` says why a training pair
    must be dropped, or None when it is clear of every test question."""

    def __init__(self, tests: list[dict], question_threshold: float = 0.6):
        self.threshold = question_threshold
        self.q_norm = {norm_question(t["question"]) for t in tests}
        self.q_tok = [question_tokens(t["question"]) for t in tests]
        self.sql_canon = {canonical_sql(t["gold_sql"]) for t in tests if t.get("gold_sql")}

    def why(self, question: str, sql: str | None) -> str | None:
        if norm_question(question) in self.q_norm:
            return "same question as a test question"
        toks = question_tokens(question)
        if any(jaccard(toks, t) >= self.threshold for t in self.q_tok):
            return f"question wording within {self.threshold:.0%} overlap of a test question"
        if sql and canonical_sql(sql) in self.sql_canon:
            return "same query as a test question's gold query"
        return None


def chat_example(system: str, question: str, reply: str) -> dict:
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": question}, {"role": "assistant", "content": reply}]}


def sql_reply(sql: str) -> str:
    """The assistant's training target for an answerable question: exactly the shape the prompt's rule 1 asks for."""
    return f"```sql\n{sql.strip().rstrip(';').strip()}\n```"


NULL, NOTNULL = "NULL", "NOTNULL"


def filter_cells(sql: str, columns_by_table: dict) -> set:
    """The (table, column, value) cells a query filters on with `=`, `IN` or `IS [NOT] NULL`. Aliases are resolved to tables; an unqualified
    column counts for every table in the query that has a column of that name. Used to keep training examples off the cells a test uses."""
    try:
        tree = sqlglot.parse_one(sql, read="mysql")
    except Exception:
        return set()
    alias = {(t.alias or t.name): t.name for t in tree.find_all(exp.Table)}
    names = set(alias.values())
    cells: set = set()

    def put(c, v):
        if c.table and c.table in alias:
            tabs = {alias[c.table]}
        else:
            tabs = {t for t in names if c.name in columns_by_table.get(t, ())}
        cells.update((t, c.name, v) for t in tabs)
    for n in tree.find_all(exp.EQ):
        a, b = n.this, n.expression
        if isinstance(b, exp.Column):
            a, b = b, a
        if isinstance(a, exp.Column) and isinstance(b, exp.Literal):
            put(a, str(b.this))
    for n in tree.find_all(exp.In):
        if isinstance(n.this, exp.Column):
            for e in n.expressions:
                if isinstance(e, exp.Literal):
                    put(n.this, str(e.this))
    for n in tree.find_all(exp.Is):
        if isinstance(n.this, exp.Column) and isinstance(n.expression, exp.Null):
            put(n.this, NOTNULL if isinstance(n.parent, exp.Not) else NULL)
    return cells
