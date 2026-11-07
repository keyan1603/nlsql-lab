"""The prompt every model is given. One prompt for all models on purpose, so a score difference is a model difference.

Model-specific templates (some specialists publish their own) are a separate experiment; this is the common baseline.
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


def system_prompt(include_comments: bool = True) -> str:
    return f"{RULES}\nDatabase schema (MySQL):\n\n{schema_for_prompt(include_comments)}\n"


def build_messages(question: str, include_comments: bool = True) -> list[dict]:
    return [{"role": "system", "content": system_prompt(include_comments)}, {"role": "user", "content": question}]
