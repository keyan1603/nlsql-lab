"""The improvement round: everything that can be wrapped around a model call without changing the model.

Four techniques, each switched on by an option so they can be measured one at a time and together:

  prompt   "mschema" shows the schema as the XiYan authors recommend (columns with comments and real example values, foreign keys listed)
  prune    show only the k tables the question is most likely to need (lexical match, never sees the gold query)
  fewshot  put k worked examples (question and query) before the real question, chosen by similarity to it
  retry    run the model's query; if the database rejects it (or, optionally, returns nothing) send the error back and ask for a fix
  vote     sample several candidates, run them all, and answer with the result most of them agree on

With every option at its default, the messages are byte for byte what nlsql.prompts.build_messages produces, so the baseline runs
already on disk stay comparable. Nothing here sees the gold query or the expected answer.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from nlsql import db, llm
from nlsql.config import ROOT
from nlsql.extract import extract
from nlsql.grader import norm
from nlsql.prompts import RULES, build_messages, build_tuned_messages
from nlsql.safety import check_select
from nlsql.schema_link import m_schema, parse_schema, select_tables, tokens
from nlsql.schema_text import schema_for_prompt

FEWSHOT_FILE = ROOT / "data" / "fewshot.json"
XSHOTS_FILE = ROOT / "data" / "xiyan_shots.json"
DIALECT_RULES = """Extra rules:
- Write MySQL 8 only: DATE_FORMAT, DATEDIFF, TIMESTAMPDIFF, DATE_SUB. Never SQLite or SQL Server functions (strftime, julianday, DATEADD, GETDATE, TOP).
- Add no condition, limit, column or ordering that the question does not ask for. Use exactly the numbers and dates it gives.
- Do not use a reserved word as an alias.
"""
SAMPLE_TEMPERATURE = 0.7


@dataclass
class Options:
    prompt: str = "plain"          # plain | mschema | tuned (compact prompt, for a model that has the schema in its weights)
    prune: int = 0                 # 0 keeps every table
    fewshot: int = 0
    retry: int = 0                 # extra attempts after a database error
    retry_empty: bool = False      # also treat "ran but returned no rows" as a reason to retry
    vote: int = 1                  # candidates; 1 means no voting
    extended: bool = True          # 22 tables (stress set) or the 11 core tables
    comments: bool = True
    dialect: bool = False          # add the MySQL-dialect and "add nothing the question does not say" rules (tuned prompt)
    decline_shots: int = 0         # worked CLARIFY / UNANSWERABLE replies from data/xiyan_shots.json (balanced, fixed order)
    guard: bool = False            # a second model call that checks, before the answer is accepted, that the schema can answer the question
    answer_shots: int = 0          # worked answerable examples from the same file, chosen by similarity among those whose tables are shown

    @property
    def baseline(self) -> bool:
        return (self.prompt == "plain" and not self.prune and not self.fewshot and not self.retry and self.vote <= 1
                and not self.guard and not self.dialect and not self.decline_shots and not self.answer_shots)

    def tag(self) -> str:
        parts = [self.prompt] + ([f"prune{self.prune}"] if self.prune else []) + ([f"fs{self.fewshot}"] if self.fewshot else []) \
            + ([f"retry{self.retry}" + ("e" if self.retry_empty else "")] if self.retry else []) + ([f"vote{self.vote}"] if self.vote > 1 else [])             + (["dialect"] if self.dialect else []) + ([f"dshots{self.decline_shots}"] if self.decline_shots else []) + ([f"ashots{self.answer_shots}"] if self.answer_shots else []) + (["guard"] if self.guard else [])
        return "-".join(parts)


@dataclass
class Result:
    text: str
    latency_s: float
    tokens_in: int
    tokens_out: int
    finish: str
    stats: dict
    info: dict = field(default_factory=dict)


# ---------------------------------------------------------------- few-shot pool
def _tables_of(sql: str) -> list[str]:
    tree = sqlglot.parse_one(sql, read="mysql")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table)} - ctes)


def xiyan_shots(decline: int, answer: int, question: str, shown: set) -> list[dict]:
    """Decline examples (alternating UNANSWERABLE / CLARIFY, fixed order) first, then the answerable ones most similar to the question."""
    pool = json.loads(XSHOTS_FILE.read_text(encoding="utf-8"))["examples"]
    us = [e for e in pool if e.get("decline", "").startswith("-- UNANSWERABLE")]
    cs = [e for e in pool if e.get("decline", "").startswith("-- CLARIFY")]
    declines = [x for pair in zip(us, cs) for x in pair][:decline]
    answerable = [dict(e, tables=_tables_of(e["sql"])) for e in pool if e.get("sql")]
    return pick_examples(question, answer, shown, answerable)[:answer] + declines if answer else declines


def load_fewshot() -> list[dict]:
    pool = json.loads(FEWSHOT_FILE.read_text(encoding="utf-8"))["examples"]
    for e in pool:
        e["tables"] = _tables_of(e["sql"]) if e.get("sql") else []
    return pool


def pick_examples(question: str, k: int, shown: set, pool: list[dict] | None = None) -> list[dict]:
    """The k pool examples most similar to the question, using only examples whose tables are all in the prompt."""
    pool = pool if pool is not None else load_fewshot()
    eligible = [e for e in pool if set(e["tables"]) <= shown]
    q = set(tokens(question))
    df: Counter = Counter()
    for e in eligible:
        df.update(set(tokens(e["question"])))
    n = max(len(eligible), 1)

    def score(e: dict) -> float:
        et = set(tokens(e["question"]))
        return sum(math.log(1 + n / df[t]) for t in q & et) / (1 + 0.1 * len(et))
    return sorted(eligible, key=lambda e: (-score(e), e["id"]))[:k]


# ---------------------------------------------------------------- prompt
def _ddl_subset(names: set, include_comments: bool, extended: bool) -> str:
    blocks = schema_for_prompt(include_comments, extended).split("\n\n")
    return "\n\n".join(b for b in blocks if (m := re.match(r"CREATE TABLE (\w+)", b)) and m.group(1) in names)


def _turns(shots: list[dict]) -> list[dict]:
    out = []
    for e in shots:
        out.append({"role": "user", "content": e["question"]})
        out.append({"role": "assistant", "content": "```sql\n" + e["sql"] + "\n```" if e.get("sql") else e["decline"]})
    return out


def build(question: str, opts: Options) -> tuple[list[dict], dict]:
    """The messages for one question and a record of what was shown."""
    if opts.prompt == "tuned":
        from nlsql.prompts import tuned_system, tuned_tables
        system = tuned_system(question)
        if opts.dialect:
            system = system.replace("\nSchema (the tables", "\n" + DIALECT_RULES + "\nSchema (the tables", 1)
        names = tuned_tables(question)
        shots = xiyan_shots(opts.decline_shots, opts.answer_shots, question, names)
        messages = [{"role": "system", "content": system}] + _turns(shots) + [{"role": "user", "content": question}]
        return messages, {"tables": "likely tables, compact", "fewshot": [e["id"] for e in shots]}
    if opts.baseline:
        return build_messages(question, opts.comments, opts.extended), {"tables": "all", "fewshot": []}
    tables = parse_schema(opts.extended)
    chosen = select_tables(question, tables, opts.prune) if opts.prune else tables
    names = {t.name for t in chosen}
    schema = m_schema(chosen) if opts.prompt == "mschema" else (_ddl_subset(names, opts.comments, opts.extended) if opts.prune else schema_for_prompt(opts.comments, opts.extended))
    rules = RULES + ("\n" + DIALECT_RULES if opts.dialect else "")
    messages = [{"role": "system", "content": f"{rules}\nDatabase schema (MySQL):\n\n{schema}\n"}]
    shots = pick_examples(question, opts.fewshot, names) if opts.fewshot else []
    shots = shots + (xiyan_shots(opts.decline_shots, opts.answer_shots, question, names) if (opts.decline_shots or opts.answer_shots) else [])
    messages += _turns(shots)
    messages.append({"role": "user", "content": question})
    return messages, {"tables": sorted(names), "fewshot": [e["id"] for e in shots]}


# ---------------------------------------------------------------- run a candidate and judge it without the gold answer
def probe(conn, sql: str | None):
    """('ok', rows) | ('empty', []) | ('error', message). The same checks the grader applies, but no gold query is involved."""
    if not sql or not sql.strip():
        return "error", "no SQL statement was found in the reply"
    safe = check_select(sql)
    if not safe.ok:
        return "error", safe.reason
    try:
        res = db.run_query(conn, sql.strip().rstrip(";"))
    except db.QueryTimeout as exc:
        return "error", str(exc)
    except Exception as exc:                                   # the driver raises many subclasses; its message is what the model needs
        return "error", re.sub(r"^\(\d+, ['\"]|['\"]\)$", "", str(exc))[:300]
    return ("ok", res.rows) if res.rows else ("empty", [])


def _feedback(status: str, info) -> str:
    if status == "error":
        return f"The database rejected that query: {info}\nReturn a corrected query in a ```sql code block, using only tables and columns from the schema."
    return ("That query ran but returned no rows. Check the codes and dates you filtered on (see the column comments and code_lookup) "
            "and return a corrected query in a ```sql code block.")


def signature(rows: list[tuple]) -> tuple:
    """A result set reduced to something comparable: row order and column order do not matter."""
    return tuple(sorted(tuple(sorted(str(round(v, 2)) if isinstance(v, float) else str(v) for v in map(norm, r))) for r in rows))


def one_candidate(model: str, messages: list[dict], opts: Options, conn, max_tokens: int, temperature: float = 0.0):
    """One answer, with up to opts.retry repair attempts. Returns (final completion text, totals, attempt log)."""
    msgs = list(messages)
    log, tin, tout, lat, finish, stats = [], 0, 0, 0.0, "", {}
    best = None
    for attempt in range(opts.retry + 1):
        c = llm.chat(model, msgs, max_tokens=max_tokens, temperature=temperature)
        tin, tout, lat, finish, stats = tin + c.tokens_in, tout + c.tokens_out, lat + c.latency_s, c.finish_reason, c.stats
        pred = extract(c.text)
        if pred.kind != "sql" or conn is None or not opts.retry:
            status, info = ("n/a", None)
        else:
            status, info = probe(conn, pred.sql)
        log.append({"status": status, "sql": (pred.sql or "")[:300]})
        # keep the first answer unless a repair turned a runnable-but-empty query into an error
        if best is None or not (best[1] == "empty" and status == "error"):
            best = (c.text, status, info)
        if status == "ok" or status == "n/a" or (status == "empty" and not opts.retry_empty) or attempt == opts.retry:
            break
        msgs = msgs + [{"role": "assistant", "content": c.text}, {"role": "user", "content": _feedback(status, info)}]
    return best[0], best[1], best[2], dict(tin=tin, tout=tout, lat=lat, finish=finish, stats=stats), log


GUARD_SYSTEM = """You check whether a database can answer a business question. You are given the question and the relevant tables.
Reply with exactly one word:
OK - every fact, column and measure the question needs exists in the tables, and the question is specific enough to answer without guessing.
MISSING - the question asks for something the tables do not hold (a measure, attribute or event that has no column).
VAGUE - the question could mean several different things (which measure, period, ranking or group is not stated) and any query would be a guess."""


def guard_verdict(model: str, question: str, max_tokens: int = 8) -> tuple[str, int, float]:
    """('OK' | 'MISSING' | 'VAGUE', tokens, seconds). An unreadable reply counts as OK, so a failed check never blocks an answer."""
    from nlsql.prompts import tuned_system
    tables = "Schema (the tables" + tuned_system(question).split("Schema (the tables", 1)[1]
    msgs = [{"role": "system", "content": GUARD_SYSTEM + "\n\n" + tables}, {"role": "user", "content": question}]
    c = llm.chat(model, msgs, max_tokens=max_tokens)
    word = (c.text.strip().split() or ["OK"])[0].strip(".:,;-").upper()
    return (word if word in ("OK", "MISSING", "VAGUE") else "OK"), c.tokens_in + c.tokens_out, c.latency_s


def solve(model: str, question: str, opts: Options, conn=None, max_tokens: int = 1024) -> Result:
    messages, shown = build(question, opts)
    candidates = []
    totals = dict(tin=0, tout=0, lat=0.0)
    n = max(opts.vote, 1)
    for i in range(n):
        text, status, rows, t, log = one_candidate(model, messages, opts, conn, max_tokens, 0.0 if i == 0 else SAMPLE_TEMPERATURE)
        for k in totals:
            totals[k] += t[k]
        if conn is not None and n > 1 and status == "n/a":                  # voting needs the result of every candidate, even without retry
            pred = extract(text)
            status, rows = probe(conn, pred.sql) if pred.kind == "sql" else ("n/a", None)
        candidates.append({"text": text, "status": status, "rows": rows, "log": log})
    chosen = candidates[0]
    votes = None
    if n > 1:
        groups: dict = {}
        for idx, c in enumerate(candidates):
            if c["status"] == "ok":
                groups.setdefault(signature(c["rows"]), []).append(idx)
        if groups:
            best_group = max(groups.values(), key=lambda g: (len(g), -g[0]))
            chosen = candidates[best_group[0]]
            votes = sorted((len(g) for g in groups.values()), reverse=True)
    guard_info = None
    if opts.guard and extract(chosen["text"]).kind == "sql":
        verdict, gtok, glat = guard_verdict(model, question)
        guard_info = {"verdict": verdict, "tokens": gtok}
        totals["lat"] += glat
        if verdict != "OK":
            text = "-- UNANSWERABLE: the schema does not hold what the question asks for" if verdict == "MISSING" else "-- CLARIFY: the question is too vague; which measure, period or group do you mean?"
            chosen = dict(chosen, text=text)
    info = {**shown, "guard": guard_info, "calls": sum(len(c["log"]) for c in candidates), "attempts": [c["log"] for c in candidates] if (opts.retry or n > 1) else None, "votes": votes}
    return Result(chosen["text"], totals["lat"], totals["tin"], totals["tout"], "", {}, info)
