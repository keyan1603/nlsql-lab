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
