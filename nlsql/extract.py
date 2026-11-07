"""Turn a model's raw text into a Prediction: SQL, an 'unanswerable' statement, or a clarifying question.

Handles the shapes small models actually produce: a fenced ```sql block, a bare statement, reasoning wrapped in <think> tags,
an <answer> wrapper, several code blocks (the last one is the final answer), the two one-line decline markers, and the
completion style of models fine-tuned on a "Context: ... SQL Query: ..." template, which write the schema out again and put the
statement after a marker with no fence at all.

Every prediction records HOW its statement was found (`how`): fence and bare mean the model followed the output instruction;
marker and unfinished mean the format was ignored and the statement was recovered. The evaluation reports that share, because
a model that needs recovery is harder to put behind an API than one that follows instructions.
"""

from __future__ import annotations

import re

from nlsql.grader import Prediction

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)
_ANSWER = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```[ \t]*(?:sql|mysql)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_UNFINISHED_FENCE = re.compile(r"```[ \t]*(?:sql|mysql)?[ \t]*\n(.*)\Z", re.DOTALL | re.IGNORECASE)
_STARTS_LIKE_SQL = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(select|with)\b", re.IGNORECASE)
_MARKER = re.compile(r"(?im)^[ \t]*(?:sql query|sql|query|answer|final sql|final query)[ \t]*:[ \t]*\n?")
_LINE_START_STATEMENT = re.compile(r"(?im)^[ \t]*(?:select|with)\b")


def _first_statement(text: str) -> str:
    """The statement at the start of text, cut at the first semicolon that ends a line or at a blank line."""
    text = text.strip()
    cut = re.search(r";[ \t]*(?:\n|\Z)", text)
    if cut:
        text = text[: cut.end()]
    blank = re.search(r"\n[ \t]*\n", text)
    if blank:
        text = text[: blank.start()]
    return text.strip()


def extract(raw: str, latency_s: float = 0.0, tokens_in: int = 0, tokens_out: int = 0) -> Prediction:
    meta = dict(latency_s=latency_s, tokens_in=tokens_in, tokens_out=tokens_out)
    text = raw or ""
    had_unclosed_think = bool(_UNCLOSED_THINK.search(text)) and "</think>" not in text.lower()
    text = _THINK.sub("", text)
    if had_unclosed_think:                                   # the model ran out of tokens while still thinking: there is no answer
        return Prediction("sql", sql=None, text="reasoning did not finish", how="none", **meta)
    wrapped = _ANSWER.search(text)
    if wrapped:
        text = wrapped.group(1)
    stripped = text.strip()

    first_line = next((ln.strip() for ln in stripped.splitlines() if ln.strip()), "")
    upper = first_line.upper()
    if upper.startswith("-- UNANSWERABLE") or upper.startswith("UNANSWERABLE"):
        return Prediction("refusal", text=first_line, how="fence", **meta)
    if upper.startswith("-- CLARIFY") or upper.startswith("CLARIFY"):
        return Prediction("clarify", text=first_line, how="fence", **meta)

    blocks = [b.strip() for b in _FENCE.findall(text) if b.strip()]
    if blocks:
        return Prediction("sql", sql=blocks[-1], text=stripped[:300], how="fence", **meta)
    unfinished = _UNFINISHED_FENCE.search(text)
    if unfinished and unfinished.group(1).strip():
        return Prediction("sql", sql=unfinished.group(1).strip(), text=stripped[:300], how="unfinished", **meta)
    if _STARTS_LIKE_SQL.match(stripped):
        return Prediction("sql", sql=_first_statement(stripped), text=stripped[:300], how="bare", **meta)
    # recovery: the statement follows a label such as "SQL Query:" (the last label wins), or is the last statement at a line start
    markers = list(_MARKER.finditer(stripped))
    if markers:
        tail = stripped[markers[-1].end():]
        if _STARTS_LIKE_SQL.match(tail):
            return Prediction("sql", sql=_first_statement(tail), text=stripped[:300], how="marker", **meta)
    starts = list(_LINE_START_STATEMENT.finditer(stripped))
    if starts:
        return Prediction("sql", sql=_first_statement(stripped[starts[-1].start():]), text=stripped[:300], how="marker", **meta)
    # prose with no statement in it: record it as 'no SQL' so the grader reports it instead of guessing
    return Prediction("sql", sql=None, text=stripped[:300], how="none", **meta)
