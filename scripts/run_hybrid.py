"""Run question sets through the LIVE hybrid pipeline (gate 3B -> rules -> 7B SQL -> checks -> hosted) and grade the answers.

    python scripts/run_hybrid.py --label sealed-heldout --policy sealed --sets heldout
    python scripts/run_hybrid.py --label open-all --policy open --sets core,hard,hard2,decline,heldout

Needs LM Studio serving BOTH models (see docs/results/hybrid.md for how they are loaded on a 4 GB GPU) and the lab MySQL database.
The open policy also needs the Gemini key (read by nlsql/llm_gemini.py from the environment or the lab's .env; this script never
reads or prints it) and respects the daily request cap enforced in that module: when the cap is reached the run stops, keeps
what it has, and says so; running the same command again after the cap resets resumes where it stopped.

Outputs (runs/ is not committed):
  runs/hybrid-<label>.jsonl         one line per question: the pipeline record, the verdict, and the verdict of the untrusted local candidate
  runs/hybrid-<label>.summary.json  per-set and pooled numbers
  runs/hybrid-<label>.audit.jsonl   the append-only audit log (ids, tiers, reasons, left_boundary; no text, no keys)
  runs/hybrid-<label>.egress.jsonl  one egress report per invocation (what the socket monitor saw)
  docs/results/hybrid.md            regenerated from every runs/hybrid-*.summary.json by scripts/hybrid_report.py

Grading is the existing grader on the existing reader account, as in scripts/run_eval.py. A question the sealed policy withheld has
no answer, so it counts as NOT correct (it is reported separately, and the accuracy among answered questions is given too).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
# LM Studio runs on 1235 here. nlsql.pipeline.solve calls nlsql.llm.chat, which reads this variable once at import, so set it first.
os.environ.setdefault("LMSTUDIO_BASE_URL", "http://127.0.0.1:1235/v1")

from nlsql import db, llm                                         # noqa: E402
from nlsql.egress import EgressBlocked, EgressMonitor              # noqa: E402
from nlsql.extract import extract                                  # noqa: E402
from nlsql.grader import Prediction, grade                         # noqa: E402
from nlsql.guard import Guard                                      # noqa: E402
from nlsql.hybrid import AuditLog, CostEstimator, HybridPipeline, Policy  # noqa: E402
from nlsql import hybrid_live                                      # noqa: E402
from nlsql.questions import load_questions                         # noqa: E402

RUNS = ROOT / "runs"
SET_FILES = {"core": "questions.json", "hard": "questions_hard.json", "hard2": "questions_hard2.json", "decline": "questions_decline.json",
             "heldout": "questions_heldout.json"}
EXTENDED = {"core": False, "hard": True, "hard2": True, "decline": True, "heldout": True}      # 22 tables for the hosted prompt
GATE_MODEL, SQL_MODEL = "nlsql-tuned-run6-3b", "xiyansql-qwencoder-7b-2504@q4_k_m"


def load_saved(path: Path) -> dict:
    if not path.exists():
        return {}
    rows = (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())
    return {(r["set"], r["qid"]): r for r in rows}


def grade_candidate(q, rec, conn, gold):
    """Grade the local answer the pipeline did not trust (what a sealed system could only hand to a human). None if there was none."""
    if not rec.local_candidate_kind:
        return None
    pred = Prediction(rec.local_candidate_kind, sql=rec.local_candidate_sql)
    v = grade(q, pred, conn, gold)
    return {"outcome": v.outcome, "passed": v.passed}


def run_question(pipe, q, conn, gold_cache):
    rec = pipe.answer(q.id, q.question)
    if q.expected == "answer" and q.id not in gold_cache:
        gold_cache[q.id] = db.run_query(conn, q.gold_sql).rows
    gold = gold_cache.get(q.id)
    if rec.withheld:
        verdict = {"outcome": "withheld", "match": None, "passed": False, "detail": rec.escalation_reason[:120]}
    elif rec.final_kind == "error":
        verdict = {"outcome": "tier_error", "match": None, "passed": False, "detail": rec.error}
    else:
        v = grade(q, extract(rec.final_text), conn, gold)
        verdict = {"outcome": v.outcome, "match": v.match, "passed": v.passed, "detail": (v.detail or "")[:160]}
    return rec, verdict, grade_candidate(q, rec, conn, gold)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--policy", choices=["sealed", "open", "redacted"], required=True)
    ap.add_argument("--sets", default="heldout", help="comma separated: core,hard,hard2,decline,heldout")
    ap.add_argument("--order", choices=["gate_first", "rules_first"], default="gate_first")
    ap.add_argument("--rules-threshold", type=int, default=1)
    ap.add_argument("--agreement", action="store_true", help="escalate when the 3B gate's SQL and the 7B's SQL return different result sets. "
                    "The gate then writes its full answer (512 tokens) instead of a clipped one, and the wording rules are OFF unless --with-rules")
    ap.add_argument("--confidence-threshold", type=float, default=None, help="single-model mode: the SQL model is its own gate (no 3B), and a SQL answer whose mean token "
                    "log-probability is below this value escalates. Chosen on the pool: -0.062 (docs/results/confidence_signal.md)")
    ap.add_argument("--with-rules", action="store_true", help="with --agreement: also apply the wording rules")
    ap.add_argument("--gate-model", default=GATE_MODEL)
    ap.add_argument("--sql-model", default=SQL_MODEL)
    ap.add_argument("--base-url", default=llm.BASE_URL)
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions of each set (smoke test)")
    ap.add_argument("--only", help="comma separated question ids")
    ap.add_argument("--fresh", action="store_true", help="ignore saved lines and ask everything again")
    ap.add_argument("--report", action="store_true", help="only regenerate docs/results/hybrid.md and exit")
    args = ap.parse_args()

    from hybrid_report import write_report
    if args.report:
        print(write_report())
        return 0
    policy = Policy.parse(args.policy)                              # raises for 'redacted' with the reason
    if args.base_url != llm.BASE_URL:
        ap.error(f"--base-url {args.base_url} differs from nlsql.llm.BASE_URL {llm.BASE_URL}; set LMSTUDIO_BASE_URL instead")

    sets = [s for s in args.sets.split(",") if s]
    missing = [s for s in sets if not (ROOT / "data" / SET_FILES[s]).exists()]
    if missing:
        ap.error(f"question file missing for: {', '.join(missing)}")

    RUNS.mkdir(exist_ok=True)
    out_path, audit_path = RUNS / f"hybrid-{args.label}.jsonl", RUNS / f"hybrid-{args.label}.audit.jsonl"
    cfg = {"policy": args.policy, "order": args.order, "agreement": args.agreement, "with_rules": args.with_rules, "rules_threshold": args.rules_threshold,
           "confidence_threshold": args.confidence_threshold, "gate_model": args.gate_model, "sql_model": args.sql_model}
    cfg_path = RUNS / f"hybrid-{args.label}.config.json"
    if cfg_path.exists() and not args.fresh and json.loads(cfg_path.read_text(encoding="utf-8")) != cfg:
        ap.error(f"{args.label}: saved answers were produced with different settings ({cfg_path.name}); use a new --label or --fresh")
    cfg_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    saved = {} if args.fresh else load_saved(out_path)
    if args.fresh:
        for p in (out_path, audit_path, RUNS / f"hybrid-{args.label}.egress.jsonl"):
            p.unlink(missing_ok=True)

    served = llm.list_models(args.base_url)
    conf = args.confidence_threshold is not None
    for m in ((args.sql_model,) if conf else (args.gate_model, args.sql_model)):
        if m not in served:
            print(f"model {m!r} is not loaded in LM Studio (served: {served}); load it first", file=sys.stderr)
            return 2
    if policy is Policy.OPEN:
        from nlsql import llm_gemini
        print(f"Gemini requests used today: {llm_gemini.requests_today()} (daily cap {int(llm_gemini._setting('GEMINI_DAILY_CAP', 450))})", flush=True)

    conn = db.connect("reader")
    cost, audit = CostEstimator(), AuditLog(audit_path, run=args.label)
    guard = Guard(audit_path=RUNS / f"hybrid-{args.label}.guard.jsonl")
    gate = hybrid_live.make_gate(args.gate_model, args.base_url, hybrid_live.GATE_FULL_MAX_TOKENS if args.agreement else hybrid_live.GATE_MAX_TOKENS)
    executor = hybrid_live.make_executor(conn, guard)

    # Warm-up: make sure both models answer before the clock starts (weights are paged in lazily). Excluded from every latency.
    for m in ((args.sql_model,) if conf else (args.gate_model, args.sql_model)):
        w = llm.chat(m, [{"role": "user", "content": "Reply with the word ready."}], max_tokens=4, base_url=args.base_url)
        print(f"warm-up {m}: {w.latency_s:.1f}s", flush=True)

    mon = EgressMonitor("sealed" if policy is Policy.SEALED else "observe")
    stopped = None
    with mon:
        canary = None
        if policy is Policy.SEALED:
            # A deliberate attempt to a documentation-range public address (RFC 5737 TEST-NET-1). It is refused BEFORE any packet is
            # sent. It proves the monitor is live in this very process, so "zero blocked attempts" below cannot mean "not watching".
            import socket
            try:
                socket.create_connection(("192.0.2.1", 80), timeout=1)
                canary = {"blocked": False}
            except EgressBlocked as exc:
                canary = {"blocked": True, "attempt": "192.0.2.1:80", "message": str(exc)[:160]}
            mon.clear()
            print(f"egress canary: {canary}", flush=True)

        for s in sets:
            questions = load_questions(ROOT / "data" / SET_FILES[s])
            if args.only:
                wanted = set(args.only.split(","))
                questions = [q for q in questions if q.id in wanted]
            if args.limit:
                questions = questions[: args.limit]
            hosted = hybrid_live.make_hosted(EXTENDED[s])
            sql = (hybrid_live.make_sql_confidence(args.sql_model, args.base_url, extended=EXTENDED[s]) if conf
                   else hybrid_live.make_sql(args.sql_model, conn, extended=EXTENDED[s]))
            pipe = HybridPipeline(gate, sql, hosted, executor, policy=policy, rules_threshold=args.rules_threshold, order=args.order,
                                  agreement=args.agreement, rules=(True if args.with_rules else None), cost=cost, audit=audit,
                                  confidence_threshold=args.confidence_threshold)
            gold_cache: dict = {}
            for i, q in enumerate(questions, start=1):
                if (s, q.id) in saved:
                    continue
                conn.ping(reconnect=True)
                rec, verdict, cand = run_question(pipe, q, conn, gold_cache)
                if rec.error == "DailyQuotaExhausted":
                    stopped = f"Gemini daily cap reached at {s}:{q.id}; stopped, rerun the same command later to resume"
                    break
                saved[(s, q.id)] = {"set": s, "qid": q.id, "expected": q.expected, "category": q.category, "rec": rec.as_dict(), "verdict": verdict, "candidate": cand}
                out_path.write_text("\n".join(json.dumps(r) for r in saved.values()) + "\n", encoding="utf-8")
                mark = "ok  " if verdict["passed"] else "FAIL"
                print(f"[{s} {i:3d}/{len(questions)}] {q.id} {mark} {verdict['outcome']:16s} {'>'.join(rec.tiers):16s} {rec.latency_s['total']:6.1f}s"
                      f"{'  ESC:' + rec.escalation_source if rec.escalation_source else ''}{'  agree=' + str(rec.agree) if args.agreement else ''}{'  conf=%.3f' % rec.confidence if conf and rec.confidence is not None else ''}", flush=True)
            if stopped:
                print(stopped, flush=True)
                break
    egress = mon.report()
    egress["canary"] = canary
    egress["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with (RUNS / f"hybrid-{args.label}.egress.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(egress) + "\n")

    from hybrid_report import summarize_run
    summary = summarize_run(args.label, policy.value, args.order + ("+agreement" + ("+rules" if args.with_rules else "") if args.agreement else "") + ("+confidence" if conf else ""), saved, stopped, sets, {"gate": args.gate_model, "sql": args.sql_model})
    (RUNS / f"hybrid-{args.label}.summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report()
    print(json.dumps({k: summary[k] for k in ("label", "policy", "pools")}, indent=1))
    print("egress:", json.dumps({k: egress[k] for k in ("mode", "attempts_total", "blocked_count", "non_loopback_allowed")}))
    if policy is Policy.SEALED:
        leaked = sum(1 for r in saved.values() if r["rec"]["left_boundary"])
        print(f"sealed check: questions with left_boundary=True: {leaked}; non-loopback destinations: {len(egress['non_loopback_allowed'])}; blocked attempts: {egress['blocked_count']}")
    return 0 if not stopped else 3


if __name__ == "__main__":
    sys.exit(main())
