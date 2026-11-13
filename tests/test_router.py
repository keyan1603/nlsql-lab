"""The router: question text in, local or frontier out. Plain rules, so every case is a plain assertion."""

import pytest

from nlsql.router import FRONTIER, LOCAL, escalate, families_of, route


@pytest.mark.parametrize("q", [
    "How many customers are in the EU region?",
    "What is the list price of product ELC-026?",
    "Show the order total for order O-1001.",
    "How many shipments are in transit?",
])
def test_routine_questions_stay_local(q):
    assert route(q).target == LOCAL and families_of(q) == ()


@pytest.mark.parametrize("q,family", [
    ("Show a running total of revenue for each customer.", "window"),
    ("Rank the products by revenue within each category.", "window"),
    ("How many orders were placed per month in 2026?", "time_bucket"),
    ("A repeat customer is a customer with at least two delivered orders. How many are there?", "defined_term"),
    ("Of those customers, what percentage placed a second order?", "multi_step"),
    ("Which customers ordered in both January and February?", "set_logic"),
    ("Which orders are above the average order value?", "correlated"),
])
def test_each_family_fires_on_its_own_kind_of_question(q, family):
    assert family in families_of(q) and route(q).target == FRONTIER


def test_the_threshold_decides_how_many_cues_are_needed():
    q = "How many orders were placed per month in 2026?"          # one family only
    assert route(q, 1).target == FRONTIER and route(q, 2).target == LOCAL


def test_the_route_explains_itself():
    r = route("Show a running total of revenue per month.")
    assert r.target == FRONTIER and set(r.families) == {"window", "time_bucket"} and "window" in r.reason


@pytest.mark.parametrize("kind,status,why", [
    ("refusal", "n/a", "declined"), ("clarify", "n/a", "declined"),
    ("sql", "error", "rejected"), ("sql", "empty", "no rows"),
])
def test_a_failed_local_answer_goes_up(kind, status, why):
    assert why in escalate(kind, status)


def test_a_clean_local_answer_is_accepted():
    assert escalate("sql", "ok") is None
