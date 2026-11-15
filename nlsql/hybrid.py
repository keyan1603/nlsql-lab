"""The hybrid pipeline: a small gate, deterministic rules, a 7B SQL model, post-checks, and a hosted model only when needed.

Per question, in order (the default `order="gate_first"`):

    1. gate     the tuned 3B model reads the question and either declines it (UNANSWERABLE / CLARIFY) or lets it through.
                A decline is final: nothing else runs and nothing leaves the machine.
    2. rules    nlsql.router.route(question, threshold): plain regular expressions that spot multi-step reasoning (windows,
                time buckets, defined terms, sets, correlated comparisons). A match means "too hard for the 7B": escalate.
    3. sql      the 7B SQL model (the configuration of the final XiYan run: tuned prompt, 4 decline examples, retry 2).
    4. execute  the SQL runs through the governed executor (nlsql.guard) and the outcome is classified ok / empty / error.
    5. checks   nlsql.router.escalate decides whether the local answer is trusted: a database error, an empty result, or a
                filter on a number/date the question never states (nlsql.invented) sends the question up.
    6. hosted   the frontier model answers, if the POLICY allows it.

`order="rules_first"` swaps steps 1 and 2 (rules can escalate before the gate has looked at the question). It is the other
strategy that scripts/gate_eval.py simulates, and it exists so the live run can be compared with either simulated row.

POLICY decides what step 6 may do:
    OPEN     the hosted tier may be called.
    SEALED   the hosted tier may NOT be called, ever. A question that would escalate returns a structured
             "escalation required, withheld by policy" result instead, so it can be routed to a person or to a model inside
             the boundary. The hosted callable is not invoked; the egress monitor (nlsql/egress.py) is the independent proof.
    REDACTED is not implemented. Hosted-after-masking would have to mask the literal values in the QUESTION (ids such as C-1002,
             dates, numbers), and those are exactly what the question is about; a masked question cannot be answered correctly.
             Masking only the schema text would protect nothing, because the schema is the same synthetic text for everyone.
             Anything that requested it would be silently weaker than it sounds, so it raises instead.

Every tier is an injectable callable, so the whole control flow is testable offline with fakes. The live tiers (LM Studio, Gemini,
MySQL) are built in nlsql/hybrid_live.py.

Every question returns a HybridRecord and appends one line to the audit log. `left_boundary` is True only when the hosted
callable was invoked (even if the call then failed: the conservative reading, since a failed call may still have sent bytes).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from nlsql import router
from nlsql.config import ROOT
from nlsql.egress import EgressBlocked
from nlsql.extract import extract

GATE, SQL, HOSTED, WITHHELD = "gate", "sql", "hosted", "withheld"      # tier names used in records


class Policy(str, Enum):
    SEALED = "sealed"
    OPEN = "open"

    @classmethod
    def parse(cls, value: str) -> "Policy":
        v = (value or "").strip().lower()
        if v == "redacted":
            raise NotImplementedError("policy 'redacted' is not implemented: masking the literal values in a question makes it unanswerable "
                                      "(see the module docstring of nlsql/hybrid.py). Use 'sealed' or 'open'.")
        return cls(v)


# ---------------------------------------------------------------- what the injectable tiers exchange
@dataclass
class TierOutput:
    """What a model tier returns: the raw text and what the call cost. `latency_s` is the model's own time; the pipeline also
    measures wall time around the call and reports that (it includes retries and database probes inside the tier)."""
    text: str
    latency_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 1                      # model calls made inside the tier (the SQL tier's retry loop can make up to 3)


@dataclass
class ExecOutcome:
    """The result of running a SQL statement through the governed executor. Row VALUES are never kept, only the count."""
    status: str                         # ok | empty | error
    detail: str = ""
    rows: int = 0
    decision: str = ""                  # the guard's decision: allowed | masked | refused | timeout | capped
    layer: str = ""


GateTier = Callable[[str], TierOutput]
SqlTier = Callable[[str], TierOutput]
HostedTier = Callable[[str], TierOutput]
Executor = Callable[[str, str], ExecOutcome]            # (question, sql) -> outcome


# ---------------------------------------------------------------- cost
class CostEstimator:
    """Hosted price and local electricity, from the same helper and assumptions as scripts/cost_model.py (and scripts/gate_eval.py).

    hosted: input and output tokens at the Standard tier (thinking tokens are already in tokens_out, see llm_gemini.parse_response).
    local:  seconds of local compute * (measured GPU draw under load + assumed CPU/system draw) * assumed electricity price.
            The GPU figure is measured (docs/results/power_measurement.json); the CPU and the price are ASSUMPTIONS and are
            labelled as such in the report. Seconds are wall time of the local tiers, so they include the database probes."""

    def __init__(self, tier: str = "Standard", cost_model_path: Path | None = None, power_path: Path | None = None):
        spec = importlib.util.spec_from_file_location("nlsql_cost_model", cost_model_path or ROOT / "scripts" / "cost_model.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                      # cost_model.py only defines things at import; main() is guarded
        self._usd = mod.usd
        self.tier = tier
        power = json.loads((power_path or ROOT / "docs" / "results" / "power_measurement.json").read_text(encoding="utf-8"))
        self.watts = power["load_w_mean"] + mod.ASSUMPTIONS["cpu_and_system_w"][0]
        self.usd_per_kwh = mod.ASSUMPTIONS["usd_per_kwh"][0]

    def hosted(self, tokens_in: int, tokens_out: int) -> float:
        return self._usd(tokens_in, tokens_out, self.tier)

    def local(self, seconds: float) -> float:
        return self.watts * seconds / 3600 / 1000 * self.usd_per_kwh


# ---------------------------------------------------------------- audit log
class AuditLog:
    """Append-only JSON-lines log. One line per question; opened in append mode and flushed per line, so a crash loses nothing
    already answered. It holds ids, hashes, tier names and reasons, never the question text, the SQL text, result values, or any
    key: the fields are a fixed whitelist (`FIELDS`), so a new piece of data cannot leak in by accident."""

    FIELDS = ("ts", "run", "qid", "question_sha256", "policy", "order", "tiers", "answered_by", "final_kind", "status",
              "escalation_source", "escalation_reason", "withheld", "left_boundary", "gate_decision", "latency_s", "tokens",
              "cost_usd", "error")

    def __init__(self, path: Path, run: str = ""):
        self.path = Path(path)
        self.run = run
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, rec: "HybridRecord") -> dict:
        line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": self.run, "qid": rec.qid,
                "question_sha256": hashlib.sha256(rec.question.encode("utf-8")).hexdigest()[:16], "policy": rec.policy, "order": rec.order,
                "tiers": rec.tiers, "answered_by": rec.answered_by, "final_kind": rec.final_kind, "status": rec.status,
                "escalation_source": rec.escalation_source, "escalation_reason": rec.escalation_reason, "withheld": rec.withheld,
                "left_boundary": rec.left_boundary, "gate_decision": rec.gate_decision, "latency_s": rec.latency_s, "tokens": rec.tokens,
                "cost_usd": rec.cost_usd, "error": rec.error}
        assert set(line) == set(self.FIELDS)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return line


# ---------------------------------------------------------------- the record
@dataclass
class HybridRecord:
    qid: str
    question: str
    policy: str
    order: str
    tiers: list = field(default_factory=list)            # every tier touched, in order: gate, sql, hosted
    answered_by: str = ""                                # gate | sql | hosted | withheld
    final_kind: str = ""                                 # sql | refusal | clarify | withheld | error
    final_text: str = ""                                 # the raw model text of the answering tier (empty when withheld)
    final_sql: str | None = None
    status: str = "n/a"                                  # execution status of the final SQL: ok | empty | error | n/a
    escalation_source: str = ""                          # rules | postcheck | tier_error | "" when nothing escalated
    escalation_reason: str = ""
    withheld: bool = False
    withheld_result: dict | None = None                  # the structured "escalation required" result in sealed mode
    local_candidate_sql: str | None = None               # the local SQL that was not trusted (kept for a human or in-boundary model)
    local_candidate_kind: str = ""
    left_boundary: bool = False
    gate_decision: str = ""                              # sql (let through) | refusal | clarify | skipped | error
    rules_families: list = field(default_factory=list)
    latency_s: dict = field(default_factory=dict)        # wall seconds per tier
    tokens: dict = field(default_factory=dict)           # per tier: {"in": n, "out": n, "calls": n}
    cost_usd: dict = field(default_factory=dict)         # local, hosted, total
    guard: dict = field(default_factory=dict)            # decision/layer for the local and final executions
    error: str = ""                                      # the type name of a tier failure, never its message

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- the pipeline
class HybridPipeline:
    def __init__(self, gate: GateTier, sql: SqlTier, hosted: HostedTier, executor: Executor, policy: Policy | str = Policy.OPEN,
                 rules_threshold: int = 1, order: str = "gate_first", escalate_on_decline: bool = False,
                 cost: CostEstimator | None = None, audit: AuditLog | None = None, clock: Callable[[], float] = time.perf_counter):
        """gate, sql, hosted: callables question -> TierOutput. executor: (question, sql) -> ExecOutcome.
        escalate_on_decline: when False (default, as in the saved-answer simulation) a decline from the 7B after the gate let the
        question through is accepted as the answer; when True it escalates like any other untrusted local result."""
        if order not in ("gate_first", "rules_first"):
            raise ValueError("order must be 'gate_first' or 'rules_first'")
        self.gate, self.sql_tier, self.hosted_tier, self.executor = gate, sql, hosted, executor
        self.policy = Policy.parse(policy) if not isinstance(policy, Policy) else policy
        self.rules_threshold, self.order, self.escalate_on_decline = rules_threshold, order, escalate_on_decline
        self.cost, self.audit, self.clock = cost, audit, clock

    # -- helpers
    def _timed(self, rec: HybridRecord, tier: str, fn: Callable, *args) -> TierOutput:
        """Call a tier, record that it was touched, its wall time, tokens and calls. Exceptions propagate after the bookkeeping."""
        rec.tiers.append(tier)
        t0 = self.clock()
        try:
            out = fn(*args)
        finally:
            rec.latency_s[tier] = round(self.clock() - t0, 4)
        rec.tokens[tier] = {"in": out.tokens_in, "out": out.tokens_out, "calls": out.calls}
        return out

    def _finish(self, rec: HybridRecord) -> HybridRecord:
        local_s = sum(v for k, v in rec.latency_s.items() if k in (GATE, SQL))
        tok = rec.tokens.get(HOSTED, {"in": 0, "out": 0})
        if self.cost is not None:
            local, hosted = self.cost.local(local_s), self.cost.hosted(tok["in"], tok["out"]) if HOSTED in rec.tiers else 0.0
            rec.cost_usd = {"local": round(local, 6), "hosted": round(hosted, 6), "total": round(local + hosted, 6)}
        rec.latency_s["total"] = round(sum(v for k, v in rec.latency_s.items() if k != "total"), 4)
        if self.audit is not None:
            self.audit.write(rec)
        return rec

    def _escalate(self, rec: HybridRecord, source: str, reason: str, question: str) -> HybridRecord:
        """Step 6. Under SEALED the hosted callable is never reached; the structured result is returned instead."""
        rec.escalation_source, rec.escalation_reason = source, reason
        if self.policy is Policy.SEALED:
            rec.withheld, rec.answered_by, rec.final_kind = True, WITHHELD, "withheld"
            rec.status = "n/a"
            rec.withheld_result = {"status": "escalation_required", "withheld_by_policy": True, "policy": Policy.SEALED.value,
                                   "reason": reason, "source": source,
                                   "route_to": "a person or a model inside the boundary",
                                   "local_candidate_available": rec.local_candidate_sql is not None}
            return self._finish(rec)
        rec.left_boundary = True                      # set BEFORE the call: if the call fails midway, bytes may still have left
        try:
            out = self._timed(rec, HOSTED, self.hosted_tier, question)
        except EgressBlocked:                         # a policy violation is never absorbed into a record
            raise
        except Exception as exc:                      # LLMUnavailable, DailyQuotaExhausted, network errors: keep the run alive, record the type only
            rec.answered_by, rec.final_kind, rec.error = HOSTED, "error", type(exc).__name__
            return self._finish(rec)
        pred = extract(out.text)
        rec.answered_by, rec.final_kind, rec.final_text, rec.final_sql = HOSTED, pred.kind, out.text, pred.sql
        if pred.kind == "sql":
            res = self._execute(rec, question, pred.sql, "hosted")
            rec.status = res.status
        return self._finish(rec)

    def _execute(self, rec: HybridRecord, question: str, sql: str | None, which: str) -> ExecOutcome:
        if not sql or not sql.strip():
            res = ExecOutcome("error", "no SQL statement was found in the reply", decision="refused", layer="extract")
        else:
            try:
                res = self.executor(question, sql)
            except Exception as exc:
                res = ExecOutcome("error", f"executor failed: {type(exc).__name__}", decision="refused", layer="executor")
        rec.guard[which] = {"decision": res.decision, "layer": res.layer, "status": res.status, "rows": res.rows}
        return res

    # -- the flow
    def answer(self, qid: str, question: str) -> HybridRecord:
        rec = HybridRecord(qid=qid, question=question, policy=self.policy.value, order=self.order)
        route = router.route(question, self.rules_threshold)
        rec.rules_families = list(route.families)

        if self.order == "rules_first" and route.target == router.FRONTIER:
            rec.gate_decision = "skipped"
            return self._escalate(rec, "rules", route.reason, question)

        # 1. gate
        try:
            g = self._timed(rec, GATE, self.gate, question)
            gp = extract(g.text)
            rec.gate_decision = gp.kind
            if gp.kind in ("refusal", "clarify"):
                rec.answered_by, rec.final_kind, rec.final_text = GATE, gp.kind, g.text
                return self._finish(rec)
        except EgressBlocked:
            raise
        except Exception as exc:                      # fail open: a broken gate must not block answering; the SQL tier and checks still run
            rec.gate_decision, rec.error = "error", type(exc).__name__

        # 2. rules (in gate_first order the gate has already had its say)
        if self.order == "gate_first" and route.target == router.FRONTIER:
            return self._escalate(rec, "rules", route.reason, question)

        # 3. the 7B SQL tier
        try:
            s = self._timed(rec, SQL, self.sql_tier, question)
        except EgressBlocked:
            raise
        except Exception as exc:
            rec.error = type(exc).__name__
            return self._escalate(rec, "tier_error", f"the local SQL tier failed ({type(exc).__name__})", question)
        pred = extract(s.text)
        rec.local_candidate_kind, rec.local_candidate_sql = pred.kind, pred.sql

        # 4./5. execute and post-check
        if pred.kind != "sql":
            reason = router.escalate(pred.kind, "n/a") if self.escalate_on_decline else None
            if reason:
                return self._escalate(rec, "postcheck", reason, question)
            rec.answered_by, rec.final_kind, rec.final_text = SQL, pred.kind, s.text
            return self._finish(rec)
        res = self._execute(rec, question, pred.sql, "local")
        reason = router.escalate("sql", res.status, question, pred.sql)
        if reason:
            return self._escalate(rec, "postcheck", reason, question)
        rec.answered_by, rec.final_kind, rec.final_text, rec.final_sql, rec.status = SQL, "sql", s.text, pred.sql, res.status
        return self._finish(rec)
