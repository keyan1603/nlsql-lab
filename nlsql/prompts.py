"""The prompt every model is given. One prompt for all models on purpose, so a score difference is a model difference.

Model-specific templates (some specialists publish their own) are a separate experiment; this is the common baseline.
p1 shows the 11 core tables; p2 shows all 22 (core plus extension) and is used for the hard question set.
"""

from __future__ import annotations

from nlsql.config import AS_OF_DATE
from nlsql.schema_text import schema_for_prompt

PROMPT_VERSION = "p1"

RULES = f"""You translate business questions into MySQL 8 queries for the database described below.

Rules:
1. Answer with exactly one read-only SELECT statement (a WITH clause is allowed) inside a ```sql code block, and nothing after it.
2. Use only the tables and columns in the schema. Never invent a column or a table.
3. Values such as statuses, tiers, regions and categories are stored as codes, not words. Use the column comments or the code_lookup table to turn a word into its code.
4. If the schema cannot answer the question, reply with exactly one line: -- UNANSWERABLE: <short reason>
5. If the question is too vague to answer without guessing (for example it does not say which measure, period or currency to use), reply with exactly one line: -- CLARIFY: <the question you need answered>
6. Use the dates named in the question. Do not use NOW() or CURDATE(). For reference, the data runs up to {AS_OF_DATE}.
"""


def system_prompt(include_comments: bool = True, extended: bool = False) -> str:
    return f"{RULES}\nDatabase schema (MySQL):\n\n{schema_for_prompt(include_comments, extended)}\n"


def build_messages(question: str, include_comments: bool = True, extended: bool = False) -> list[dict]:
    return [{"role": "system", "content": system_prompt(include_comments, extended)}, {"role": "user", "content": question}]


# The compact prompt for a model fine-tuned on this database. It does not carry the 22-table CREATE TABLE text (about 3,500 tokens).
# It carries a short rule list and a one-line-per-table description of only the tables the question is likely to need (about 430 tokens);
# the model learned the rest (types, join habits, code values) from its training pairs.
TUNED_RULES = f"""You translate business questions into MySQL 8 queries for the nlsql_lab database (customers, orders, support, logistics and marketing).

Rules:
1. Answer with exactly one read-only SELECT statement (a WITH clause is allowed) inside a ```sql code block, and nothing after it.
2. If the database cannot answer the question, reply with exactly one line: -- UNANSWERABLE: <short reason>
3. If the question is too vague to answer without guessing, reply with exactly one line: -- CLARIFY: <the question you need answered>
4. Use the dates named in the question. Do not use NOW() or CURDATE(). For reference, the data runs up to {AS_OF_DATE}.
"""
TUNED_TABLES = 5
_TABLES = None


def tuned_tables(question: str) -> set:
    """Names of the tables tuned_system shows for this question."""
    global _TABLES
    from nlsql.schema_link import parse_schema, select_tables
    if _TABLES is None:
        _TABLES = parse_schema(True)
    return {t.name for t in select_tables(question, _TABLES, TUNED_TABLES)}


def tuned_system(question: str, extra_tables: tuple = ()) -> str:
    """The rules plus the compact description of the tables the question probably needs (selected without the answer), in schema-file order.
    extra_tables adds tables by name; training uses it to make sure the tables the answer needs are shown, inference never does."""
    global _TABLES
    from nlsql.schema_link import parse_schema, select_tables
    from nlsql.schema_text import compact_schema
    if _TABLES is None:
        _TABLES = parse_schema(True)
    names = {t.name for t in select_tables(question, _TABLES, TUNED_TABLES)} | set(extra_tables)
    shown = compact_schema([t for t in _TABLES if t.name in names])
    return f"{TUNED_RULES}\nSchema (the tables most likely to be needed):\n{shown}\n"


def build_tuned_messages(question: str, extra_tables: tuple = ()) -> list[dict]:
    return [{"role": "system", "content": tuned_system(question, extra_tables)}, {"role": "user", "content": question}]
