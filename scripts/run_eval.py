"""Ask a model (served by LM Studio) every question, grade the answers on the real database, and save everything.

    python scripts/run_eval.py --model <served model id> --label xiyan7b-q4km [--schema comments|bare] [--max-tokens 1024]
    python scripts/run_eval.py --label xiyan7b-q4km --regrade        # re-grade saved outputs without calling the model

Outputs, in runs/ (not committed): <label>.jsonl (one line per question with the raw model text, the extracted SQL, timings
and the verdict) and <label>.summary.json. A run that is interrupted resumes where it stopped.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tabulate import tabulate                                   # noqa: E402

from nlsql import db, llm                                       # noqa: E402
from nlsql.config import ROOT                                   # noqa: E402
from nlsql.extract import extract                               # noqa: E402
from nlsql.grader import Prediction, grade, summarize, Verdict  # noqa: E402
from nlsql.prompts import PROMPT_VERSION, build_messages        # noqa: E402
from nlsql.questions import load_questions                      # noqa: E402

RUNS = ROOT / "runs"


def load_records(path: Path) -> dict:
    if not path.exists():
        return {}
    return {r["qid"]: r for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="the model id as LM Studio serves it (see: lms ps)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--schema", choices=["comments", "bare"], default="comments")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--only", help="comma separated question ids")
    ap.add_argument("--set", choices=["core", "hard"], default="core", help="core: the 55 questions on the 11 core tables (prompt p1); hard: the stress set on all 22 tables (prompt p2)")
    ap.add_argument("--regrade", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="ignore saved outputs and ask every question again")
    args = ap.parse_args()

    RUNS.mkdir(exist_ok=True)
    out_path = RUNS / f"{args.label}.jsonl"
    saved = {} if args.fresh else load_records(out_path)
    extended = args.set == "hard"
    questions = load_questions(ROOT / "data" / ("questions_hard.json" if extended else "questions.json"))
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q.id in wanted]
    if not args.regrade and not args.model:
        ap.error("--model is required unless --regrade")
    reader = db.connect("reader")
    gold_cache: dict = {}
    records, verdicts = [], []
    t_start = time.perf_counter()
    for i, q in enumerate(questions, start=1):
        rec = saved.get(q.id)
        if rec is None or (not args.regrade and rec.get("raw") is None):
            if args.regrade:
                continue
            c = llm.chat(args.model, build_messages(q.question, args.schema == "comments", extended), max_tokens=args.max_tokens)
            rec = {"qid": q.id, "raw": c.text, "latency_s": round(c.latency_s, 3), "tokens_in": c.tokens_in, "tokens_out": c.tokens_out,
                   "finish": c.finish_reason, "stats": c.stats}
        pred = extract(rec["raw"], rec["latency_s"], rec["tokens_in"], rec["tokens_out"])
        if q.expected == "answer" and q.id not in gold_cache:
            gold_cache[q.id] = db.run_query(reader, q.gold_sql).rows
        v: Verdict = grade(q, pred, reader, gold_cache.get(q.id))
        rec.update({"kind": pred.kind, "sql": pred.sql, "how": pred.how, "outcome": v.outcome, "match": v.match, "passed": v.passed, "detail": v.detail})
        records.append(rec)
        verdicts.append(v)
        saved[q.id] = rec
        out_path.write_text("\n".join(json.dumps(r) for r in saved.values()) + "\n", encoding="utf-8")
        mark = "ok  " if v.passed else "FAIL"
        print(f"[{i:2d}/{len(questions)}] {q.id} {mark} {v.outcome:16s} {rec['latency_s']:6.1f}s {rec['tokens_out']:4d} tok  {(v.detail or '')[:60]}", flush=True)

    if not verdicts:
        print("nothing graded")
        return 1
    s = summarize(verdicts)
    by_cat: dict = {}
    for q, v in zip(questions, verdicts):
        by_cat.setdefault(q.category, []).append(v.passed)
    lat = [r["latency_s"] for r in records]
    hows = [r.get("how", "") for r in records]
    followed = sum(1 for h in hows if h == "fence")
    tok = sum(r["tokens_out"] for r in records)
    total_latency = sum(lat)
    summary = {"label": args.label, "model": args.model, "schema": args.schema, "prompt_version": "p2" if extended else PROMPT_VERSION, "question_set": args.set, "max_tokens": args.max_tokens,
               **s, "passed": sum(v.passed for v in verdicts), "of": len(verdicts),
               "latency_mean_s": round(statistics.mean(lat), 2), "latency_p95_s": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 2),
               "format_followed": f"{followed}/{len(hows)}", "extraction": {h: hows.count(h) for h in sorted(set(hows))}, "tokens_out_total": tok, "tokens_out_per_s": round(tok / total_latency, 2) if total_latency else None,
               "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in by_cat.items()}, "wall_s": round(time.perf_counter() - t_start, 1)}
    (RUNS / f"{args.label}.summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print()
    print(tabulate([[k, f"{sum(v)}/{len(v)}"] for k, v in by_cat.items()], headers=["category", "passed"], tablefmt="github"))
    print(f"\n{args.label}: execution accuracy {s['execution_accuracy']:.1%} ({s['correct']}/{s['answerable']} answerable), "
          f"declined correctly {s['declined_correctly']}/{s['should_decline']}, errors {s['sql_errors']}, match levels {s['match_levels']}, "
          f"mean {summary['latency_mean_s']}s per question, {summary['tokens_out_per_s']} tok/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
