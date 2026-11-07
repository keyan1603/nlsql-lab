"""Prompt building and output extraction, offline."""

from nlsql.extract import extract
from nlsql.prompts import PROMPT_VERSION, build_messages, system_prompt


def test_the_prompt_carries_the_rules_and_the_schema():
    p = system_prompt(True)
    assert "-- UNANSWERABLE" in p and "-- CLARIFY" in p and "CREATE TABLE cust_master" in p and "2026-10-31" in p
    assert "DISCONTINUED" in p                       # the column comments are in the commented variant


def test_the_bare_prompt_has_no_column_comments():
    p = system_prompt(False)
    assert "CREATE TABLE cust_master" in p and "DISCONTINUED" not in p and "COMMENT" not in p


def test_messages_are_system_then_user():
    m = build_messages("How many orders?")
    assert [x["role"] for x in m] == ["system", "user"] and m[1]["content"] == "How many orders?"
    assert PROMPT_VERSION


def test_a_fenced_sql_block_is_extracted():
    p = extract("Here you go:\n```sql\nSELECT COUNT(*) FROM cust_master;\n```\nHope that helps")
    assert p.kind == "sql" and p.sql == "SELECT COUNT(*) FROM cust_master;"


def test_the_last_code_block_wins():
    p = extract("```sql\nSELECT 1\n```\nActually:\n```sql\nSELECT 2\n```")
    assert p.sql == "SELECT 2"


def test_a_bare_statement_is_accepted():
    assert extract("SELECT 1").sql == "SELECT 1"
    assert extract("WITH t AS (SELECT 1 a) SELECT a FROM t").sql.startswith("WITH")


def test_reasoning_is_stripped_and_an_answer_wrapper_is_unwrapped():
    p = extract("<think>I should join the tables... SELECT bad</think>\n<answer>```sql\nSELECT 5\n```</answer>")
    assert p.sql == "SELECT 5"


def test_unfinished_reasoning_means_no_answer():
    p = extract("<think>Let me think about this for a very long time and never")
    assert p.kind == "sql" and p.sql is None


def test_an_unclosed_fence_still_yields_the_statement():
    assert extract("```sql\nSELECT 1 FROM emp").sql == "SELECT 1 FROM emp"


def test_decline_markers_are_recognised():
    assert extract("-- UNANSWERABLE: there is no satisfaction column").kind == "refusal"
    assert extract("\n-- CLARIFY: best by what measure?").kind == "clarify"
    assert extract("<think>hm</think>-- UNANSWERABLE: no data").kind == "refusal"


def test_prose_without_sql_is_no_sql_not_a_guess():
    p = extract("I think the answer is about 54 customers.")
    assert p.kind == "sql" and p.sql is None


def test_metadata_is_carried_through():
    p = extract("SELECT 1", latency_s=1.5, tokens_in=10, tokens_out=3)
    assert (p.latency_s, p.tokens_in, p.tokens_out) == (1.5, 10, 3)


def test_a_label_then_statement_with_no_fence_is_recovered_and_flagged():
    raw = "Context:\nCREATE TABLE cust_master (cust_id VARCHAR(8));\n\nSQL Query:\nSELECT region_cd FROM cust_master WHERE cust_id = 'C-1010';"
    p = extract(raw)
    assert p.sql == "SELECT region_cd FROM cust_master WHERE cust_id = 'C-1010';" and p.how == "marker"


def test_only_the_first_statement_after_the_label_is_taken():
    p = extract("SQL Query:\nSELECT 1;\n\nSELECT 2;\nExplanation: ...")
    assert p.sql == "SELECT 1;"


def test_a_multiline_statement_after_a_label_is_kept_whole():
    p = extract("Answer:\nSELECT a,\n       b\nFROM t\nWHERE x = 1;\n")
    assert p.sql.startswith("SELECT a,") and p.sql.endswith("x = 1;") and p.how == "marker"


def test_the_schema_the_model_wrote_back_is_not_mistaken_for_the_answer():
    raw = "Context:\nCREATE TABLE t (a INT);\n\nSQL Query:\nSELECT a FROM t;"
    assert "CREATE" not in extract(raw).sql


def test_how_records_whether_the_instruction_was_followed():
    assert extract("```sql\nSELECT 1\n```").how == "fence"
    assert extract("SELECT 1").how == "bare"
    assert extract("just words").how == "none"
    assert extract("```sql\nSELECT 1 FROM emp").how == "unfinished"
