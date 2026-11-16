"""Collect the model's own token probabilities for each answer, one attempt per question (no repair), and grade it.

    python scripts/confidence_run.py --model xiyan7bft --sets heldout,hard,hard2,core

For every question: the first-attempt reply with the per-token log-probabilities, the SQL, whether it ran (probe), and the grade against the gold answer.
Resumable. Writes runs/confidence-<label>.jsonl. scripts/confidence_eval.py turns this into the signal analysis.
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nlsql import db, llm                                       # noqa: E402
from nlsql.extract import extract                               # noqa: E402
from nlsql.grader import grade                                  # noqa: E402
from nlsql.pipeline import Options, build, probe                # noqa: E402
from nlsql.questions import load_questions                      # noqa: E402

FILES = {"core": "questions.json", "hard": "questions_hard.json", "hard2": "questions_hard2.json", "heldout": "questions_heldout.json", "decline": "questions_decline.json"}


def chat_logprobs(model: str, messages: list, max_tokens: int) -> dict:
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.0, "max_tokens": max_tokens, "stream": False, "logprobs": True}).encode()
    req = urllib.request.Request(f"{llm.BASE_URL}/chat/completions", data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.load(r)
    ch = data["choices"][0]
    toks = [(t["token"], round(t["logprob"], 4)) for t in (ch.get("logprobs") or {}).get("content", [])]
    return {"text": ch["message"].get("content") or "", "latency_s": round(time.perf_counter() - t0, 2), "tokens": toks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="xiyan7bft")
    ap.add_argument("--label", default="xiyan7bft-e2")
    ap.add_argument("--sets", default="heldout,hard,hard2,core")
    ap.add_argument("--max-tokens", type=int, default=1024)
    a = ap.parse_args()
    out_path = ROOT / "runs" / f"confidence-{a.label}.jsonl"
    saved = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                saved[(r["set"], r["qid"])] = r
    reader = db.connect("reader")
    for s in a.sets.split(","):
        extended = s in ("hard", "hard2", "decline", "heldout")
        opts = Options(prompt="tuned", decline_shots=4, retry=0, extended=extended, comments=True)
        qs = load_questions(ROOT / "data" / FILES[s])
        for i, q in enumerate(qs, start=1):
            if (s, q.id) in saved:
                continue
            messages, _ = build(q.question, opts)
            c = chat_logprobs(a.model, messages, a.max_tokens)
            pred = extract(c["text"], c["latency_s"], 0, len(c["tokens"]))
            gold = db.run_query(reader, q.gold_sql).rows if q.expected == "answer" else None
            v = grade(q, pred, reader, gold)
            status = probe(reader, pred.sql)[0] if pred.kind == "sql" else "n/a"
            rec = {"set": s, "qid": q.id, "category": q.category, "expected": q.expected, "kind": pred.kind, "sql": pred.sql, "passed": bool(v.passed),
                   "outcome": v.outcome, "status": status, "latency_s": c["latency_s"], "tokens": c["tokens"], "question": q.question}
            saved[(s, q.id)] = rec
            out_path.write_text("\n".join(json.dumps(r) for r in saved.values()) + "\n", encoding="utf-8")
            print(f"[{s} {i:3d}/{len(qs)}] {q.id} {'ok  ' if v.passed else 'FAIL'} {v.outcome:14s} {status:6s} {c['latency_s']:6.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
