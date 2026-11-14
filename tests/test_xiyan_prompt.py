"""The XiYan prompt options: dialect rules, worked decline examples, and the held-out-cell helper."""
from nlsql.pipeline import DIALECT_RULES, Options, build, xiyan_shots
from nlsql.traindata import NOTNULL, NULL, filter_cells

Q = "How many gold customers are in Europe?"
COLS = {"cust_master": {"tier_cd", "region_cd", "is_actv"}, "support_tkt": {"closed_ts", "cust_id"}}


def test_defaults_keep_the_baseline_messages():
    assert Options().baseline
    assert not Options(dialect=True).baseline and not Options(decline_shots=2).baseline


def test_tag_names_the_new_options():
    assert Options(prompt="tuned", dialect=True, decline_shots=4, answer_shots=2).tag() == "tuned-dialect-dshots4-ashots2"


def test_tuned_dialect_inserts_rules_before_the_schema():
    msgs, _ = build(Q, Options(prompt="tuned", dialect=True))
    s = msgs[0]["content"]
    assert DIALECT_RULES.strip() in s and s.index("Extra rules") < s.index("Schema (the tables")


def test_decline_shots_alternate_and_are_chat_turns():
    msgs, info = build(Q, Options(prompt="tuned", decline_shots=4))
    assert [m["role"] for m in msgs] == ["system"] + ["user", "assistant"] * 4 + ["user"]
    replies = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert [r.split(":")[0] for r in replies] == ["-- UNANSWERABLE", "-- CLARIFY", "-- UNANSWERABLE", "-- CLARIFY"]
    assert msgs[-1]["content"] == Q and len(info["fewshot"]) == 4


def test_answer_shots_only_use_tables_that_are_shown():
    shots = xiyan_shots(0, 3, Q, {"cust_master"})
    assert all(e.get("sql") and set(e["tables"]) <= {"cust_master"} for e in shots)


def test_plain_prompt_gets_shots_after_the_system_message():
    msgs, _ = build(Q, Options(prompt="plain", decline_shots=2))
    assert msgs[0]["role"] == "system" and len(msgs) == 6 and msgs[-1]["content"] == Q


def test_filter_cells_resolves_aliases_in_and_null():
    sql = "SELECT 1 FROM cust_master c JOIN support_tkt t ON t.cust_id = c.cust_id WHERE c.tier_cd = 'G' AND c.region_cd IN ('EU','NA') AND t.closed_ts IS NULL AND c.is_actv IS NOT NULL"
    assert filter_cells(sql, COLS) == {("cust_master", "tier_cd", "G"), ("cust_master", "region_cd", "EU"), ("cust_master", "region_cd", "NA"),
                                       ("support_tkt", "closed_ts", NULL), ("cust_master", "is_actv", NOTNULL)}


def test_filter_cells_unqualified_column_and_bad_sql():
    assert filter_cells("SELECT 1 FROM cust_master WHERE tier_cd = 'P'", COLS) == {("cust_master", "tier_cd", "P")}
    assert filter_cells("SELEKT ((", COLS) == set()


def test_guard_verdict_parses_and_fails_open(monkeypatch):
    from nlsql import pipeline
    from nlsql.llm import Completion
    import inspect
    fields = [f for f in inspect.signature(Completion).parameters]

    def fake(text):
        kw = {f: (text if f == "text" else 0 if f.startswith(("tokens", "latency")) else "" if f in ("finish_reason",) else {}) for f in fields}
        return Completion(**kw)
    for reply, want in [("MISSING - no rating column", "MISSING"), ("vague.", "VAGUE"), ("OK", "OK"), ("banana", "OK"), ("", "OK")]:
        monkeypatch.setattr(pipeline.llm, "chat", lambda *a, **k: fake(reply))
        assert pipeline.guard_verdict("m", Q)[0] == want


def test_guard_option_in_tag_and_baseline():
    assert Options(guard=True).tag().endswith("guard") and not Options(guard=True).baseline
