"""The training-set helpers, and the guarantee that no training pair is a test question (checked on the real files when they exist)."""

import json
from pathlib import Path

import pytest

from nlsql.prompts import TUNED_SYSTEM, build_tuned_messages
from nlsql.traindata import LeakFilter, canonical_sql, chat_example, jaccard, norm_question, parse_json_array, question_tokens, sql_reply

ROOT = Path(__file__).resolve().parent.parent
TESTS = [{"question": "How many customers are in the EU region?", "gold_sql": "SELECT COUNT(*) FROM cust_master WHERE region_cd = 'EU'"},
         {"question": "What is the average age of our customers?"}]


def test_a_json_array_is_found_inside_fences_and_chatter():
    assert parse_json_array('Here you go:\n```json\n[{"question": "a", "sql": "SELECT 1"}]\n```\nThanks') == [{"question": "a", "sql": "SELECT 1"}]


@pytest.mark.parametrize("bad", ["", "no json here", "[{broken", '{"not": "an array"}'])
def test_bad_replies_give_an_empty_list(bad):
    assert parse_json_array(bad) == []


def test_question_normalisation_ignores_case_and_punctuation():
    assert norm_question("How many  Customers, in EU?") == norm_question("how many customers in eu")


def test_jaccard_is_one_for_equal_sets_and_zero_for_disjoint():
    a, b = question_tokens("customers in the EU region"), question_tokens("shipments to Asia")
    assert jaccard(a, a) == 1.0 and jaccard(a, b) == 0.0 and jaccard(frozenset(), a) == 0.0


def test_canonical_sql_ignores_layout_and_keyword_case():
    assert canonical_sql("select  count(*)\nfrom t where a=1") == canonical_sql("SELECT COUNT(*) FROM t WHERE a = 1")


def test_the_leak_filter_drops_the_same_question_a_reworded_one_and_the_same_query():
    f = LeakFilter(TESTS, 0.6)
    assert f.why("how many customers are in the eu region", None)
    assert f.why("How many customers are there in the EU region?", None)
    assert f.why("Count of accounts", "select count(*) from cust_master where region_cd='EU'")
    assert f.why("Which carrier delivered the most orders in 2026?", "SELECT carrier_cd FROM shipment") is None


def test_the_training_target_has_exactly_the_shape_rule_one_asks_for():
    assert sql_reply("SELECT 1;\n") == "```sql\nSELECT 1\n```"
    ex = chat_example("S", "Q", "A")
    assert [m["role"] for m in ex["messages"]] == ["system", "user", "assistant"]


def test_the_compact_prompt_carries_no_schema_but_keeps_the_decline_rules():
    m = build_tuned_messages("Q")
    assert "CREATE TABLE" not in TUNED_SYSTEM and len(TUNED_SYSTEM) < 1500
    assert "UNANSWERABLE" in TUNED_SYSTEM and "CLARIFY" in TUNED_SYSTEM and m[-1] == {"role": "user", "content": "Q"}


def test_no_real_training_pair_is_a_test_question():
    train = ROOT / "train" / "data" / "train.jsonl"
    if not train.exists():
        pytest.skip("training set not built yet")
    tests = []
    for f in ("questions", "questions_hard", "questions_hard2", "questions_decline"):
        d = json.loads((ROOT / "data" / f"{f}.json").read_text(encoding="utf-8"))
        tests += d if isinstance(d, list) else d["questions"]
    flt = LeakFilter(tests, 0.6)
    for path in (train, ROOT / "train" / "data" / "val.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            q, a = row["messages"][1]["content"], row["messages"][2]["content"]
            sql = a.removeprefix("```sql\n").removesuffix("\n```") if a.startswith("```sql") else None
            assert flt.why(q, sql) is None, (row["id"], q)
