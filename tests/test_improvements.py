"""The improvement round, tested without a model: schema parsing and selection, the few-shot pool, the retry loop and voting
(with a scripted fake model and a fake database), plus integration checks that the worked examples run and do not copy the evaluation sets."""

import re
from types import SimpleNamespace

import pytest

from nlsql import db, pipeline
from nlsql.config import ROOT
from nlsql.pipeline import Options, build, pick_examples, load_fewshot, signature, solve
from nlsql.prompts import build_messages
from nlsql.questions import load_questions
from nlsql.safety import check_select
from nlsql.schema_link import m_schema, parse_schema, select_tables, load_examples


# ---- schema parsing and layout
def test_the_schema_parses_into_22_tables_and_120_columns():
    tables = parse_schema(True)
    assert len(tables) == 22 and sum(len(t.columns) for t in tables) == 120
    assert len(parse_schema(False)) == 11


def test_keys_and_comments_are_read():
    by = {t.name: t for t in parse_schema(True)}
    assert ("cust_id", "cust_master", "cust_id") in by["ord_hdr"].fks
    assert any(c.name == "ord_status" and "delivered" in c.comment for c in by["ord_hdr"].columns)
    assert [c.name for c in by["ord_line"].columns if c.pk] == ["ord_id", "line_no"]


def test_m_schema_shows_example_values_but_never_personal_ones():
    text = m_schema(parse_schema(True))
    assert "Examples: [C, D, N, R, S]" in text
    assert "【Foreign keys】" in text and "ord_hdr.cust_id=cust_master.cust_id" in text
    for personal in ("email_addr", "phone_no", "natl_id", "salary_amt"):
        line = next(l for l in text.splitlines() if l.startswith(f"({personal}:"))
        assert "Examples" not in line, personal
    assert "@" not in "".join(v for cols in load_examples().values() for vs in cols.values() for v in vs)


# ---- table selection
def test_selection_keeps_the_tables_a_question_names_and_the_lookup_table():
    names = {t.name for t in select_tables("How many platinum customers placed orders last year?", parse_schema(True), 4)}
    assert {"cust_master", "ord_hdr", "code_lookup"} <= names


def test_selection_follows_foreign_keys_to_parent_tables():
    names = {t.name for t in select_tables("Total quantity per product on delivered orders", parse_schema(True), 3)}
    assert "ord_hdr" in names and "prod_catalog" in names


def test_selection_shows_far_fewer_than_all_tables():
    assert len(select_tables("Which carriers delivered late?", parse_schema(True), 5)) < 12


# ---- prompts
def test_default_options_reproduce_the_baseline_prompt_exactly():
    for ext in (True, False):
        msgs, _ = build("How many orders?", Options(extended=ext))
        assert msgs == build_messages("How many orders?", True, ext)


def test_pruned_ddl_contains_only_the_chosen_tables():
    msgs, shown = build("How many warehouses are there?", Options(prune=2))
    system = msgs[0]["content"]
    assert "CREATE TABLE warehouse" in system and "CREATE TABLE web_event" not in system
    assert set(re.findall(r"CREATE TABLE (\w+)", system)) == set(shown["tables"])


def test_few_shot_examples_become_chat_turns_before_the_question():
    msgs, shown = build("How many customers are in each tier?", Options(fewshot=2))
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "How many customers are in each tier?" and len(shown["fewshot"]) == 2


def test_examples_that_use_hidden_tables_are_never_offered():
    pool = load_fewshot()
    core_tables = {t.name for t in parse_schema(False)}
    for e in pick_examples("How many movements per warehouse?", 20, core_tables, pool):
        assert set(e["tables"]) <= core_tables


def test_the_most_similar_example_comes_first():
    pool = load_fewshot()
    top = pick_examples("How many customers are there in each loyalty tier?", 1, {t.name for t in parse_schema(True)}, pool)[0]
    assert top["id"] == "F01"


# ---- retry and voting with a scripted model
class Script:
    """A fake model that returns the next scripted reply, and a fake database keyed on the SQL text."""
    def __init__(self, replies):
        self.replies, self.calls, self.seen = list(replies), 0, []

    def chat(self, model, messages, max_tokens=1024, temperature=0.0, **kw):
        self.seen.append((list(messages), temperature))
        text = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return SimpleNamespace(text=text, latency_s=1.0, tokens_in=10, tokens_out=5, finish_reason="stop", stats={})


class FakeDb:
    def __init__(self, table):
        self.table = table                       # sql substring -> rows, or an Exception

    def run_query(self, conn, sql, **kw):
        for key, val in self.table.items():
            if key in sql:
                if isinstance(val, Exception):
                    raise val
                return SimpleNamespace(rows=val, columns=["c"], elapsed_ms=1.0)
        raise AssertionError(f"unexpected sql {sql}")


@pytest.fixture
def scripted(monkeypatch):
    def install(replies, table):
        s = Script(replies)
        monkeypatch.setattr(pipeline.llm, "chat", s.chat)
        fake = FakeDb(table)
        monkeypatch.setattr(pipeline.db, "run_query", fake.run_query)
        return s
    return install


def fenced(sql):
    return f"```sql\n{sql}\n```"


OPT = dict(extended=False)


def test_a_query_that_runs_is_accepted_without_a_second_call(scripted):
    s = scripted([fenced("SELECT 1 FROM a")], {"FROM a": [(1,)]})
    r = solve("m", "q?", Options(retry=2, **OPT), conn=object())
    assert s.calls == 1 and "FROM a" in r.text and r.info["calls"] == 1


def test_a_database_error_is_sent_back_and_the_fix_is_used(scripted):
    s = scripted([fenced("SELECT x FROM a"), fenced("SELECT y FROM a")], {"SELECT x": RuntimeError("(1054, \"Unknown column 'x' in 'field list'\")"), "SELECT y": [(1,)]})
    r = solve("m", "q?", Options(retry=2, **OPT), conn=object())
    assert s.calls == 2 and "SELECT y" in r.text
    feedback = s.seen[1][0][-1]["content"]
    assert "Unknown column 'x'" in feedback and s.seen[1][0][-2]["role"] == "assistant"
    assert r.tokens_in == 20 and r.latency_s == 2.0                         # cost of every call is counted


def test_the_retry_budget_is_respected(scripted):
    s = scripted([fenced("SELECT x FROM a")], {"SELECT x": RuntimeError("boom")})
    solve("m", "q?", Options(retry=2, **OPT), conn=object())
    assert s.calls == 3


def test_an_empty_result_is_accepted_unless_empty_retries_are_on(scripted):
    s = scripted([fenced("SELECT 1 FROM a")], {"FROM a": []})
    solve("m", "q?", Options(retry=2, **OPT), conn=object())
    assert s.calls == 1
    s = scripted([fenced("SELECT 1 FROM a"), fenced("SELECT 2 FROM a")], {"SELECT 1": [], "SELECT 2": [(7,)]})
    r = solve("m", "q?", Options(retry=2, retry_empty=True, **OPT), conn=object())
    assert s.calls == 2 and "SELECT 2" in r.text


def test_a_repair_that_turns_an_empty_answer_into_an_error_is_discarded(scripted):
    scripted([fenced("SELECT 1 FROM a"), fenced("SELECT bad FROM a")], {"SELECT 1": [], "SELECT bad": RuntimeError("no")})
    r = solve("m", "q?", Options(retry=1, retry_empty=True, **OPT), conn=object())
    assert "SELECT 1" in r.text


def test_a_refusal_is_not_retried(scripted):
    s = scripted(["-- UNANSWERABLE: no such data"], {})
    r = solve("m", "q?", Options(retry=2, **OPT), conn=object())
    assert s.calls == 1 and r.text.startswith("-- UNANSWERABLE")


def test_voting_picks_the_result_most_candidates_agree_on(scripted):
    s = scripted([fenced("SELECT 1 FROM a"), fenced("SELECT 2 FROM a"), fenced("SELECT 2 FROM a")], {"SELECT 1": [(1,)], "SELECT 2": [(2,)]})
    r = solve("m", "q?", Options(vote=3, **OPT), conn=object())
    assert "SELECT 2" in r.text and r.info["votes"] == [2, 1] and s.calls == 3
    assert [t for _, t in s.seen] == [0.0, 0.7, 0.7]                         # the first candidate is greedy, the others sampled


def test_voting_ties_go_to_the_greedy_candidate_and_errors_do_not_vote(scripted):
    scripted([fenced("SELECT 1 FROM a"), fenced("SELECT 2 FROM a"), fenced("SELECT bad FROM a")], {"SELECT 1": [(1,)], "SELECT 2": [(2,)], "SELECT bad": RuntimeError("x")})
    assert "SELECT 1" in solve("m", "q?", Options(vote=3, **OPT), conn=object()).text


def test_result_signatures_ignore_row_and_column_order():
    assert signature([(1, "a"), (2, "b")]) == signature([("b", 2), ("a", 1)])
    assert signature([(1,)]) != signature([(2,)])


# ---- the worked examples against the real database and the evaluation sets
def _words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def test_no_example_question_is_a_near_copy_of_an_evaluation_question():
    eval_qs = [q.question for f in ("questions.json", "questions_hard.json", "questions_hard2.json") for q in load_questions(ROOT / "data" / f)]
    for e in load_fewshot():
        a = _words(e["question"])
        worst = max(len(a & _words(q)) / len(a | _words(q)) for q in eval_qs)
        assert worst < 0.6, (e["id"], worst)


def test_no_example_query_equals_an_evaluation_gold_query():
    def norm(sql):
        return re.sub(r"\s+", " ", sql.lower()).strip().rstrip(";")
    gold = {norm(q.gold_sql) for f in ("questions.json", "questions_hard.json", "questions_hard2.json") for q in load_questions(ROOT / "data" / f) if q.gold_sql}
    for e in load_fewshot():
        if e.get("sql"):
            assert norm(e["sql"]) not in gold, e["id"]


@pytest.mark.integration
def test_every_worked_example_passes_the_safety_check_and_returns_rows(reader):
    for e in load_fewshot():
        if e.get("sql"):
            assert check_select(e["sql"]).ok, e["id"]
            assert db.run_query(reader, e["sql"]).rows, e["id"]
