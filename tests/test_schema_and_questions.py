"""The schema file, the prompt text built from it, and the labelled question set are all well formed."""

import sqlglot
from sqlglot import exp

from nlsql import db
from nlsql.questions import load_questions, problems
from nlsql.safety import check_select
from nlsql.schema_text import schema_ddl, schema_for_prompt
from nlsql.seed import COLUMNS, TABLE_ORDER

QUESTIONS = load_questions()
CREATES = [s for s in db._split_statements(schema_ddl()) if s.strip().upper().startswith("CREATE TABLE")]


def test_the_schema_splits_into_eleven_drops_and_eleven_creates():
    statements = [s for s in db._split_statements(schema_ddl()) if s.strip()]
    assert len(statements) == 22
    assert sum(1 for s in statements if s.strip().upper().startswith("DROP TABLE")) == 11
    assert len(CREATES) == 11


def test_every_create_table_parses_and_matches_the_seed_columns():
    for stmt in CREATES:
        tree = sqlglot.parse_one(stmt, read="mysql")
        table = tree.this.this.name
        columns = [c.name for c in tree.find_all(exp.ColumnDef)]
        assert columns == COLUMNS[table], table
    assert {sqlglot.parse_one(s, read="mysql").this.this.name for s in CREATES} == set(TABLE_ORDER)


def test_the_prompt_schema_has_only_create_statements():
    text = schema_for_prompt(True)
    assert text.count("CREATE TABLE") == 11 and "DROP" not in text and "--" not in text


def test_stripping_comments_leaves_a_valid_bare_schema():
    bare = schema_for_prompt(False)
    assert "COMMENT" not in bare
    assert "disc_flag" in bare and "DISCONTINUED" not in bare
    for stmt in [s for s in bare.split(";\n") if s.strip()]:
        sqlglot.parse_one(stmt.strip().rstrip(";"), read="mysql")
    assert "DISCONTINUED" in schema_for_prompt(True)


def test_the_question_set_is_well_formed():
    assert problems(QUESTIONS) == []


def test_the_question_set_has_the_intended_mix():
    from collections import Counter
    by_cat = Counter(q.category for q in QUESTIONS)
    assert len(QUESTIONS) == 55
    assert by_cat["unanswerable"] == 4 and by_cat["ambiguous"] == 2
    assert Counter(q.expected for q in QUESTIONS) == {"answer": 49, "unanswerable": 4, "clarify": 2}
    assert {q.difficulty for q in QUESTIONS} == {"easy", "medium", "hard"}
    assert all(by_cat[c] >= 3 for c in ("lookup", "filter_aggregate", "join", "group_by", "date_time", "nulls_state", "fanout_trap", "hierarchy", "policy_dates"))


def test_question_text_is_unique():
    texts = [q.question for q in QUESTIONS]
    assert len(texts) == len(set(texts))


def test_every_gold_query_is_a_safe_select_that_parses_and_uses_real_tables():
    known = set(TABLE_ORDER)
    for q in QUESTIONS:
        if q.expected != "answer":
            continue
        assert check_select(q.gold_sql).ok, q.id
        tree = sqlglot.parse_one(q.gold_sql, read="mysql")
        ctes = {c.alias for c in tree.find_all(exp.CTE)}
        tables = {t.name for t in tree.find_all(exp.Table)} - ctes
        assert tables <= known, (q.id, tables - known)


def test_date_relative_questions_name_their_reference_date():
    for q in QUESTIONS:
        if q.expected == "answer":
            assert "CURDATE" not in q.gold_sql.upper() and "NOW()" not in q.gold_sql.upper(), q.id


def test_hard_questions_are_a_real_share():
    hard = [q for q in QUESTIONS if q.difficulty == "hard"]
    assert len(hard) >= 8
