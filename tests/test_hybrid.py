"""Offline tests for nlsql.hybrid: every tier is a fake, so no model, database or network is involved.

The fakes count their calls, which is how the tests prove which tiers ran (and, for the sealed policy, that the hosted one did not).
"""
import json

import pytest

from nlsql.hybrid import AuditLog, CostEstimator, ExecOutcome, HybridPipeline, Policy, TierOutput

ROUTINE = "How many customers are there?"                                       # no router family matches
HARD = "What is the running total of order value for each month?"             # window + time_bucket families
OK_SQL = "```sql\nSELECT COUNT(*) FROM cust_master\n```"


class Fake:
    """A tier that returns canned text and counts calls."""
    def __init__(self, text="", tin=10, tout=5, boom=None):
        self.text, self.tin, self.tout, self.boom, self.calls = text, tin, tout, boom, 0

    def __call__(self, question):
        self.calls += 1
        if self.boom:
            raise self.boom
        return TierOutput(self.text, 0.01, self.tin, self.tout, 1)


def executor(status="ok", rows=1, decision="allowed"):
    calls = []

    def run(question, sql):
        calls.append((question, sql))
        return ExecOutcome(status, "", rows if status == "ok" else 0, decision, "")
    run.calls = calls
    return run


def build(gate=None, sql=None, hosted=None, ex=None, **kw):
    gate = gate or Fake("```sql\nSELECT 1\n```")
    sql = sql or Fake(OK_SQL)
    hosted = hosted or Fake("```sql\nSELECT COUNT(*) FROM cust_master\n```", 100, 20)
    ex = ex or executor()
    return HybridPipeline(gate, sql, hosted, ex, **kw), gate, sql, hosted, ex


# ---------------------------------------------------------------- the happy path stays inside the boundary
def test_routine_question_is_answered_by_the_7b_and_never_leaves():
    p, gate, sql, hosted, _ = build(policy="open")
    r = p.answer("Q1", ROUTINE)
    assert r.answered_by == "sql" and r.final_kind == "sql" and r.status == "ok"
    assert r.tiers == ["gate", "sql"]
    assert r.left_boundary is False and hosted.calls == 0
    assert r.escalation_source == "" and not r.withheld


def test_record_carries_latency_tokens_and_cost_per_tier():
    p, *_ = build(cost=CostEstimator())
    r = p.answer("Q1", ROUTINE)
    assert set(r.latency_s) == {"gate", "sql", "total"}
    assert r.tokens["gate"] == {"in": 10, "out": 5, "calls": 1}
    assert r.cost_usd["hosted"] == 0 and r.cost_usd["local"] >= 0 and r.cost_usd["total"] == r.cost_usd["local"]


# ---------------------------------------------------------------- the gate declines
@pytest.mark.parametrize("text,kind", [("-- UNANSWERABLE: no such column", "refusal"), ("-- CLARIFY: which period?", "clarify")])
def test_gate_decline_is_final_and_nothing_else_runs(text, kind):
    p, gate, sql, hosted, ex = build(gate=Fake(text), policy="open")
    r = p.answer("Q2", ROUTINE)
    assert r.answered_by == "gate" and r.final_kind == kind and r.gate_decision == kind
    assert r.tiers == ["gate"] and sql.calls == 0 and hosted.calls == 0 and not ex.calls
    assert r.left_boundary is False


def test_gate_decline_wins_over_the_rules_in_gate_first_order():
    """A question the rules would escalate is still declined locally when the gate says it cannot be answered."""
    p, gate, sql, hosted, _ = build(gate=Fake("-- UNANSWERABLE: x"), policy="open", order="gate_first")
    r = p.answer("Q2", HARD)
    assert r.answered_by == "gate" and hosted.calls == 0


def test_a_failing_gate_fails_open():
    p, gate, sql, hosted, _ = build(gate=Fake(boom=RuntimeError("down")), policy="open")
    r = p.answer("Q3", ROUTINE)
    assert r.gate_decision == "error" and r.answered_by == "sql" and r.error == "RuntimeError"


# ---------------------------------------------------------------- the rules escalate
def test_rules_escalate_a_reasoning_heavy_question_without_calling_the_7b():
    p, gate, sql, hosted, _ = build(policy="open")
    r = p.answer("Q4", HARD)
    assert r.tiers == ["gate", "hosted"] and sql.calls == 0 and hosted.calls == 1
    assert r.answered_by == "hosted" and r.left_boundary is True
    assert r.escalation_source == "rules" and "window" in r.escalation_reason
    assert r.rules_families


def test_rules_first_order_skips_the_gate_for_flagged_questions():
    p, gate, sql, hosted, _ = build(policy="open", order="rules_first")
    r = p.answer("Q4", HARD)
    assert r.tiers == ["hosted"] and gate.calls == 0 and r.gate_decision == "skipped"


def test_threshold_two_keeps_a_one_family_question_local():
    one_family = "Show the latest order for each customer."
    p, *_ = build(policy="open", rules_threshold=2)
    assert p.answer("Q5", one_family).answered_by == "sql"


# ---------------------------------------------------------------- post-checks escalate
@pytest.mark.parametrize("status,needle", [("error", "rejected"), ("empty", "no rows")])
def test_database_error_or_empty_result_escalates(status, needle):
    p, gate, sql, hosted, ex = build(ex=executor(status), policy="open")
    r = p.answer("Q6", ROUTINE)
    assert r.tiers == ["gate", "sql", "hosted"] and r.answered_by == "hosted" and r.left_boundary
    assert r.escalation_source == "postcheck" and needle in r.escalation_reason
    assert r.local_candidate_sql == "SELECT COUNT(*) FROM cust_master"


def test_invented_value_in_the_sql_escalates():
    p, gate, sql, hosted, _ = build(sql=Fake("```sql\nSELECT * FROM ord_hdr WHERE ord_total > 500\n```"), policy="open")
    r = p.answer("Q7", "Which orders are large?")
    assert r.answered_by == "hosted" and "500" in r.escalation_reason


def test_a_stated_value_is_not_invented():
    p, gate, sql, hosted, _ = build(sql=Fake("```sql\nSELECT * FROM ord_hdr WHERE ord_total > 500\n```"), policy="open")
    assert p.answer("Q7b", "Which orders are over 500?").answered_by == "sql"


def test_a_7b_decline_is_accepted_by_default_and_escalated_when_asked():
    p, gate, sql, hosted, _ = build(sql=Fake("-- CLARIFY: which period?"), policy="open")
    r = p.answer("Q8", ROUTINE)
    assert r.answered_by == "sql" and r.final_kind == "clarify" and hosted.calls == 0
    p2, gate2, sql2, hosted2, _ = build(sql=Fake("-- CLARIFY: which period?"), policy="open", escalate_on_decline=True)
    assert p2.answer("Q8", ROUTINE).answered_by == "hosted" and hosted2.calls == 1


def test_no_sql_in_the_reply_counts_as_an_error():
    p, gate, sql, hosted, ex = build(sql=Fake("I am not sure."), policy="open")
    r = p.answer("Q9", ROUTINE)
    assert r.answered_by == "hosted"
    assert len(ex.calls) == 1                                  # only the hosted answer was executed; the local reply had no statement
    assert r.guard["local"]["layer"] == "extract" and r.guard["local"]["status"] == "error"


def test_sql_tier_failure_escalates_when_open():
    p, gate, sql, hosted, _ = build(sql=Fake(boom=TimeoutError()), policy="open")
    r = p.answer("Q10", ROUTINE)
    assert r.answered_by == "hosted" and r.escalation_source == "tier_error" and r.error == "TimeoutError"


def test_hosted_failure_is_recorded_without_its_message():
    p, gate, sql, hosted, _ = build(hosted=Fake(boom=RuntimeError("secret-key-abc in message")), policy="open")
    r = p.answer("Q11", HARD)
    assert r.final_kind == "error" and r.error == "RuntimeError" and r.left_boundary
    assert "secret" not in json.dumps(r.as_dict()["error"])


# ---------------------------------------------------------------- sealed policy
@pytest.mark.parametrize("question,ex_status", [(HARD, "ok"), (ROUTINE, "error"), (ROUTINE, "empty")])
def test_sealed_policy_withholds_and_never_calls_the_hosted_tier(question, ex_status):
    p, gate, sql, hosted, _ = build(ex=executor(ex_status), policy="sealed")
    r = p.answer("S1", question)
    assert hosted.calls == 0
    assert r.withheld and r.answered_by == "withheld" and r.final_kind == "withheld"
    assert r.left_boundary is False and "hosted" not in r.tiers
    assert r.withheld_result["status"] == "escalation_required" and r.withheld_result["withheld_by_policy"] is True
    assert r.withheld_result["reason"] == r.escalation_reason


def test_sealed_policy_keeps_the_untrusted_local_candidate_for_a_human():
    p, *_ = build(ex=executor("empty"), policy="sealed")
    r = p.answer("S2", ROUTINE)
    assert r.local_candidate_sql == "SELECT COUNT(*) FROM cust_master" and r.withheld_result["local_candidate_available"] is True
    assert r.final_sql is None


def test_sealed_policy_still_answers_what_stays_inside():
    p, gate, sql, hosted, _ = build(policy="sealed")
    assert p.answer("S3", ROUTINE).answered_by == "sql"
    p2, *_ = build(gate=Fake("-- UNANSWERABLE: x"), policy="sealed")
    assert p2.answer("S4", HARD).answered_by == "gate"


def test_redacted_policy_is_refused_loudly():
    with pytest.raises(NotImplementedError):
        HybridPipeline(Fake(), Fake(), Fake(), executor(), policy="redacted")


def test_unknown_policy_and_order_are_rejected():
    with pytest.raises(ValueError):
        Policy.parse("whatever")
    with pytest.raises(ValueError):
        HybridPipeline(Fake(), Fake(), Fake(), executor(), order="sideways")


# ---------------------------------------------------------------- hosted cost
def test_hosted_cost_uses_the_standard_tier_price_and_left_boundary_is_true_only_then():
    est = CostEstimator()
    p, *_ = build(policy="open", cost=est)
    r = p.answer("C1", HARD)
    assert r.cost_usd["hosted"] == pytest.approx(est.hosted(100, 20), abs=1e-6) and r.left_boundary
    inside = p.answer("C2", ROUTINE)
    assert inside.cost_usd["hosted"] == 0 and inside.left_boundary is False


# ---------------------------------------------------------------- audit log
def test_audit_log_is_append_only_jsonl_with_the_whitelisted_fields(tmp_path):
    path = tmp_path / "audit.jsonl"
    p, *_ = build(policy="sealed", audit=AuditLog(path, run="t1"), ex=executor("error"))
    p.answer("A1", ROUTINE)
    p.answer("A2", HARD)
    p2, *_ = build(policy="open", audit=AuditLog(path, run="t2"))           # a second writer appends, it does not truncate
    p2.answer("A3", HARD)
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [l["qid"] for l in lines] == ["A1", "A2", "A3"]
    assert set(lines[0]) == set(AuditLog.FIELDS)
    assert lines[0]["withheld"] is True and lines[0]["left_boundary"] is False and lines[0]["tiers"] == ["gate", "sql"]
    assert lines[1]["escalation_source"] == "rules" and lines[1]["tiers"] == ["gate"]
    assert lines[2]["left_boundary"] is True and lines[2]["tiers"] == ["gate", "hosted"] and lines[2]["run"] == "t2"


def test_audit_log_holds_no_question_text_sql_or_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test-key-should-never-appear")
    path = tmp_path / "audit.jsonl"
    p, *_ = build(policy="open", audit=AuditLog(path), ex=executor("error"))
    p.answer("A4", "How many customers are there in the secret region?")
    raw = path.read_text(encoding="utf-8")
    assert "secret region" not in raw and "SELECT" not in raw and "AIza" not in raw and "api_key" not in raw.lower()
    rec = json.loads(raw)
    assert len(rec["question_sha256"]) == 16


# ---------------------------------------------------------------- the report aggregation (scripts/hybrid_report.py)
def test_report_aggregation_counts_withheld_escalation_and_cost():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import hybrid_report as hr
    est = CostEstimator()
    p, *_ = build(policy="sealed", cost=est, ex=executor("ok"))
    rows = []
    for qid, q in (("a", ROUTINE), ("b", HARD)):
        r = p.answer(qid, q)
        rows.append({"set": "core", "qid": qid, "expected": "answer", "category": "x", "rec": r.as_dict(), "candidate": None,
                     "verdict": {"outcome": "withheld" if r.withheld else "correct", "passed": not r.withheld, "match": None, "detail": ""}})
    a = hr.aggregate(rows)
    assert a["n"] == 2 and a["passed"] == 1 and a["withheld"] == 1 and a["answered"] == 1
    assert a["escalated"] == 1 and a["escalation_by_source"] == {"rules": 1} and a["left_boundary"] == 0 and a["hosted_calls"] == 0
    assert a["usd_per_1000"]["hosted"] == 0


# ---------------------------------------------------------------- agreement between the 3B gate and the 7B
GATE_SQL = "```sql\nSELECT COUNT(*) FROM cust_master\n```"
SQL7 = "```sql\nSELECT COUNT(*) AS n FROM cust_master\n```"


def result_executor(by_sql):
    """An executor whose result rows depend on the SQL text: by_sql maps a substring to (status, rows)."""
    calls = []

    def run(question, sql):
        calls.append(sql)
        for key, (status, rows) in by_sql.items():
            if key in sql:
                return ExecOutcome(status, "", len(rows), "allowed", "", rows)
        return ExecOutcome("error", "unknown", 0, "refused", "")
    run.calls = calls
    return run


def agree_pipe(gate_text=GATE_SQL, sql_text=SQL7, ex=None, policy="open", **kw):
    ex = ex or result_executor({"AS n": ("ok", [(60,)]), "COUNT(*) FROM": ("ok", [(60,)])})
    gate, sql, hosted = Fake(gate_text), Fake(sql_text), Fake(OK_SQL, 100, 20)
    return HybridPipeline(gate, sql, hosted, ex, policy=policy, agreement=True, **kw), gate, sql, hosted, ex


def test_agreement_accepts_the_7b_when_both_result_sets_match():
    p, gate, sql, hosted, ex = agree_pipe()
    r = p.answer("G1", ROUTINE)
    assert r.agree is True and r.gate_sql_present and r.answered_by == "sql" and hosted.calls == 0 and len(ex.calls) == 2


def test_agreement_compares_order_insensitively():
    ex = result_executor({"AS n": ("ok", [(1,), (2,)]), "FROM cust_master": ("ok", [(2,), (1,)])})
    r = agree_pipe(ex=ex)[0].answer("G2", ROUTINE)
    assert r.agree is True


def test_disagreement_escalates_to_hosted_with_the_reason():
    ex = result_executor({"AS n": ("ok", [(60,)]), "COUNT(*) FROM": ("ok", [(59,)])})
    p, gate, sql, hosted, _ = agree_pipe(ex=ex)
    r = p.answer("G3", ROUTINE)
    assert r.agree is False and r.answered_by == "hosted" and r.left_boundary and hosted.calls == 1
    assert r.escalation_source == "agreement" and r.escalation_reason == "the 3B and 7B disagree"


def test_sealed_policy_withholds_on_disagreement_and_never_calls_hosted():
    ex = result_executor({"AS n": ("ok", [(60,)]), "COUNT(*) FROM": ("ok", [(59,)])})
    p, gate, sql, hosted, _ = agree_pipe(ex=ex, policy="sealed")
    r = p.answer("G4", ROUTINE)
    assert hosted.calls == 0 and r.withheld and r.left_boundary is False and r.agree is False
    assert r.withheld_result["reason"] == "the 3B and 7B disagree" and r.local_candidate_sql is not None


def test_gate_decline_is_final_in_agreement_mode_and_the_7b_never_runs():
    p, gate, sql, hosted, _ = agree_pipe(gate_text="-- CLARIFY: which period?")
    r = p.answer("G5", ROUTINE)
    assert r.answered_by == "gate" and sql.calls == 0 and r.agree is None and r.gate_sql_present is False


def test_7b_decline_gives_no_agreement_signal():
    p, gate, sql, hosted, _ = agree_pipe(sql_text="-- UNANSWERABLE: no")
    r = p.answer("G6", ROUTINE)
    assert r.agree is None and r.answered_by == "sql" and r.final_kind == "refusal" and hosted.calls == 0


def test_gate_sql_that_errors_is_not_a_disagreement():
    ex = result_executor({"AS n": ("ok", [(60,)])})                    # the gate's text matches nothing: the fake executor reports an error
    p, gate, sql, hosted, _ = agree_pipe(ex=ex)
    r = p.answer("G7", ROUTINE)
    assert r.agree is None and r.answered_by == "sql" and hosted.calls == 0


def test_7b_error_escalates_through_the_ordinary_check_and_skips_the_comparison():
    ex = result_executor({"AS n": ("error", []), "COUNT(*) FROM": ("ok", [(60,)])})
    p, gate, sql, hosted, _ = agree_pipe(ex=ex)
    r = p.answer("G8", ROUTINE)
    assert r.agree is None and r.escalation_source == "postcheck" and r.answered_by == "hosted"


def test_gate_with_no_sql_text_is_no_signal():
    p, gate, sql, hosted, _ = agree_pipe(gate_text="I think so.")
    r = p.answer("G9", ROUTINE)
    assert r.agree is None and r.gate_sql_present is False and r.answered_by == "sql"


def test_rules_are_off_in_agreement_mode_unless_requested():
    p, gate, sql, hosted, _ = agree_pipe()
    r = p.answer("G10", HARD)
    assert r.answered_by == "sql" and r.rules_families and hosted.calls == 0     # matched but not acted on
    p2, *_ = agree_pipe(rules=True)
    assert p2.answer("G11", HARD).escalation_source == "rules"


def test_agreement_fields_are_in_the_audit_record(tmp_path):
    ex = result_executor({"AS n": ("ok", [(60,)]), "COUNT(*) FROM": ("ok", [(59,)])})
    p, *_ = agree_pipe(ex=ex, audit=AuditLog(tmp_path / "a.jsonl"))
    p.answer("G12", ROUTINE)
    line = json.loads((tmp_path / "a.jsonl").read_text(encoding="utf-8"))
    assert line["agree"] is False and line["gate_sql_present"] is True and line["escalation_source"] == "agreement"
    assert "60" not in json.dumps(line)                                         # result values never reach the log


def test_without_agreement_the_gate_sql_is_ignored():
    p, gate, sql, hosted, ex = build(gate=Fake(GATE_SQL), policy="open")
    r = p.answer("G13", ROUTINE)
    assert r.agree is None and r.gate_sql_present is False and len(ex.calls) == 1


# ---------------------------------------------------------------- single-model mode: the 7B's own token probability decides
class Conf(Fake):
    def __init__(self, text, conf):
        super().__init__(text)
        self.conf = conf

    def __call__(self, question):
        out = super().__call__(question)
        out.confidence = self.conf
        return out


def conf_pipe(conf, policy="open", text=OK_SQL, **kw):
    gate, hosted, ex = Fake("```sql\nSELECT 1\n```"), Fake("```sql\nSELECT COUNT(*) FROM cust_master\n```", 100, 20), executor()
    sql = Conf(text, conf)
    return HybridPipeline(gate, sql, hosted, ex, policy=policy, confidence_threshold=-0.06, **kw), gate, sql, hosted


def test_confident_answer_is_kept_and_the_gate_never_runs():
    p, gate, sql, hosted = conf_pipe(-0.02)
    r = p.answer("Q1", ROUTINE)
    assert r.answered_by == "sql" and r.tiers == ["sql"] and gate.calls == 0 and hosted.calls == 0
    assert r.gate_decision == "skipped" and r.confidence == -0.02


def test_low_confidence_escalates_to_hosted_when_open():
    p, gate, sql, hosted = conf_pipe(-0.2)
    r = p.answer("Q1", ROUTINE)
    assert r.answered_by == "hosted" and r.escalation_source == "confidence" and hosted.calls == 1 and r.left_boundary


def test_low_confidence_is_withheld_when_sealed():
    p, gate, sql, hosted = conf_pipe(-0.2, policy="sealed")
    r = p.answer("Q1", ROUTINE)
    assert r.withheld and hosted.calls == 0 and r.local_candidate_sql and not r.left_boundary


def test_a_decline_is_not_second_guessed_by_confidence():
    p, gate, sql, hosted = conf_pipe(-0.5, text="-- UNANSWERABLE: no such data")
    r = p.answer("Q1", ROUTINE)
    assert r.final_kind == "refusal" and hosted.calls == 0 and r.answered_by == "sql"


def test_audit_line_names_the_strategy_and_confidence(tmp_path):
    audit = AuditLog(tmp_path / "a.jsonl", run="t")
    p, *_ = conf_pipe(-0.02)
    p.audit = audit
    p.answer("Q1", ROUTINE)
    line = json.loads((tmp_path / "a.jsonl").read_text().splitlines()[0])
    assert line["mode"] == "confidence" and line["confidence"] == -0.02


def test_comparator_failure_is_recorded_not_swallowed():
    def boom(a, b):
        raise ValueError("odd value")
    p, *_ = agree_pipe(compare=boom)
    r = p.answer("Q1", ROUTINE)
    assert r.agree is None and r.error == "Comparator:ValueError"
