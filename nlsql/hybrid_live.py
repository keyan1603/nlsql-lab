"""The live tiers for nlsql.hybrid: LM Studio for the gate and the SQL model, Gemini for the hosted tier, MySQL through the guard.

Kept apart from nlsql/hybrid.py so the control flow can be imported and tested without a database driver or a model server.

Settings that matter and why:
  gate     prompt `tuned` (nlsql.prompts.build_tuned_messages), greedy, ONE call, max_tokens GATE_MAX_TOKENS. The gate only has to
           say "decline" or "proceed", and both are visible in the first line of the reply: a decline is a one-line
           `-- UNANSWERABLE` / `-- CLARIFY`, anything else starts a SQL statement. So the reply is cut at a few dozen tokens
           instead of letting the 3B write a whole query that is then thrown away. The saved-answer simulation used the 3B's full
           answer with retry 2; under greedy decoding the first line is the same, and the retry could only change a SQL answer into
           a different SQL answer or (rarely) a decline, so this is a small, stated difference.
  sql      nlsql.pipeline.solve with Options(prompt="tuned", decline_shots=4, retry=2): the configuration of the final XiYan run
           (docs/results/xiyan/summary.md, runs/xiyan7b-final-*.summary.json: pipeline tag `tuned-retry2-dshots4`), max_tokens 1024.
           Its repair loop probes the database with the read-only account, as in that run.
  hosted   the plain baseline prompt (all 22 tables on the stress, decline and held-out sets, the 11 core tables on core), the same
           prompt the saved hosted answers used, max_tokens 4096 (scripts/gemini_baseline.sh), one call, no retry.
  execute  nlsql.guard.Guard: the governed path production traffic should use (comment/parser/policy layers, SQL regenerated from
           the parse tree, read-only account, time limit, 1000-row cap). The grader in scripts/run_hybrid.py judges the extracted
           SQL on the reader account exactly like scripts/run_eval.py does, so grades are comparable with the saved runs.
"""

from __future__ import annotations

from nlsql import db, llm
from nlsql.guard import Guard
from nlsql.hybrid import ExecOutcome, TierOutput
from nlsql.pipeline import Options, solve
from nlsql.prompts import build_messages, build_tuned_messages

GATE_MAX_TOKENS = 48
SQL_OPTIONS = dict(prompt="tuned", decline_shots=4, retry=2)           # == pipeline tag tuned-retry2-dshots4
HOSTED_MODEL = "gemini-3.5-flash-lite"


def make_gate(model: str, base_url: str, max_tokens: int = GATE_MAX_TOKENS):
    def gate(question: str) -> TierOutput:
        c = llm.chat(model, build_tuned_messages(question), max_tokens=max_tokens, base_url=base_url)
        return TierOutput(c.text, c.latency_s, c.tokens_in, c.tokens_out, 1)
    return gate


def make_sql(model: str, conn, extended: bool = True, max_tokens: int = 1024):
    """The 7B tier. nlsql.pipeline.solve calls llm.chat with the module's BASE_URL, so the caller must set LMSTUDIO_BASE_URL before
    nlsql.llm is imported (scripts/run_hybrid.py does, and checks it)."""
    opts = Options(extended=extended, **SQL_OPTIONS)

    def sql(question: str) -> TierOutput:
        r = solve(model, question, opts, conn=conn, max_tokens=max_tokens)
        return TierOutput(r.text, r.latency_s, r.tokens_in, r.tokens_out, int(r.info.get("calls", 1)))
    return sql


def make_hosted(extended: bool, model: str = HOSTED_MODEL, max_tokens: int = 4096):
    """The hosted tier. The only function in the pipeline whose call can leave the machine. llm.chat routes any model id that
    starts with `gemini` to nlsql.llm_gemini, which enforces the requests-per-minute limit and the daily cap."""
    def hosted(question: str) -> TierOutput:
        c = llm.chat(model, build_messages(question, True, extended), max_tokens=max_tokens)
        return TierOutput(c.text, c.latency_s, c.tokens_in, c.tokens_out, 1)
    return hosted


def make_executor(conn, guard: Guard | None = None):
    guard = guard or Guard()

    def execute(question: str, sql: str) -> ExecOutcome:
        r = guard.execute(conn, question, sql)
        if r.decision in ("allowed", "masked"):
            return ExecOutcome("ok" if r.rows else "empty", "", len(r.rows), r.decision, r.layer)
        # refused (parser, policy or database), timeout, capped: the local answer cannot be used as it is
        return ExecOutcome("error", f"{r.layer}: {r.reason}"[:300], 0, r.decision, r.layer)
    return execute


def connect_reader():
    return db.connect("reader")
