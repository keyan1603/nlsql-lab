"""Extra training pairs aimed at the question types the 7B fails on the stress sets (window, time bucket, defined term, multi-step, set logic, correlated).

    python scripts/make_hard_data.py generate --max-requests 60   # teacher writes hard question/query pairs (resumable; stops at the daily cap)
    python scripts/make_hard_data.py verify                       # keep queries that run and return rows, drop duplicates of the existing pool
    python scripts/make_hard_data.py answer --max-requests 60     # blind second pass by the teacher
    python scripts/make_hard_data.py build                        # agree + LeakFilter + held-out-cell rule + replay mix, write hard_train/hard_val.jsonl

Same method as scripts/make_training_data.py (verified distillation: the query runs on the real database, a blind second answer from the
teacher returns the same result, and the pair is not a test look-alike), with two additions: the held-out-cell rule of
scripts/make_terse_data.py (no pair filters on a (table, column, value) cell that a test gold query filters on) and a replay of decline,
terse and easy pairs from the existing training files so a pass on hard pairs does not unlearn them. Nothing is written to the existing
train.jsonl, val.jsonl or candidates.jsonl, so the 3B results stay reproducible. Test gold queries are used only to throw pairs away.
The teacher sees only the lab's synthetic schema. No test question or hard-set failure text is shown to the teacher.
"""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_terse_data import test_cells                     # noqa: E402
from make_training_data import (CLUSTERS, PERSONAS, answer_prompt, generation_prompt, jl_append, jl_read, run_sql,   # noqa: E402
                                tables_of, tests_for_leaks)
from nlsql import db, llm_gemini                           # noqa: E402
from nlsql.grader import compare_results                   # noqa: E402
from nlsql.llm import LLMUnavailable                       # noqa: E402
from nlsql.prompts import tuned_system                     # noqa: E402
from nlsql.router import families_of                       # noqa: E402
from nlsql.schema_link import m_schema, parse_schema       # noqa: E402
from nlsql.traindata import (LeakFilter, canonical_sql, chat_example, filter_cells, norm_question, parse_json_array, sql_reply)   # noqa: E402

DATA = ROOT / "train" / "data"
MODEL = "gemini-3.5-flash-lite"
ROUND0 = 100            # round numbers start here so the variation seeds differ from the first training-set generation

HARD = {
    "window": "window functions, hard variants: top N per group with explicit tie handling, running or cumulative totals per partition, LAG/LEAD gaps between consecutive rows, percent of a group total, rank within a group then filter on the rank, first and last row per entity",
    "time_bucket": "time bucketing, hard variants: one row per month, week or quarter with explicit date ranges, buckets that must include empty periods or compare with the previous bucket, trailing windows of N days written as explicit dates, year-over-year comparisons by DATE_FORMAT",
    "evidence": "the question first DEFINES a business term in one sentence (a 'late shipment', a 'high-value order', an 'at-risk customer', an 'active week') with exact thresholds, and then asks something that needs the definition; the definition must map to real columns and codes",
    "cte_multistep": "WITH clauses that build the answer in two or three steps: aggregate first then filter or rank on the aggregate, percentages of a filtered subset, cohort comparisons, ratios of two groups, a funnel from one group to the next",
    "set_ops": "set logic, hard variants: entities in both of two groups, in A but never in B (NOT EXISTS), in at least one of several groups, UNION of two differently shaped sources, INTERSECT and EXCEPT written as MySQL-8 compatible queries",
    "correlated": "correlated subqueries and EXISTS, hard variants: rows above or below the average of their own group, the latest or largest row per entity, entities whose value exceeds their own previous value, entities with no matching rows in a related table",
}
FAMILY_OF = {"window": "window", "time_bucket": "time_bucket", "evidence": "defined_term", "cte_multistep": "multi_step", "set_ops": "set_logic", "correlated": "correlated"}


def jobs() -> list[dict]:
    out = []
    for ti, (tech, desc) in enumerate(HARD.items()):
        for ci, (cl, tabs) in enumerate(CLUSTERS.items()):
            out.append({"id": f"hard_{tech}.{cl}", "kind": "sql", "technique": tech, "technique_desc": desc + ". Every pair should be at the hard end: several steps, not a single aggregate", "cluster": cl, "tables": tabs,
                        "persona": PERSONAS[(ti * 3 + ci + 1) % len(PERSONAS)]})
    return out


def cmd_generate(a) -> None:
    values = json.loads((DATA / "values.json").read_text(encoding="utf-8"))
    schema = m_schema(parse_schema(True))
    done = Counter(r["job"] for r in jl_read(DATA / "hard_gen_raw.jsonl"))
    sent = 0
    for rnd in range(ROUND0, ROUND0 + a.rounds):
        for job in jobs():
            key = f"{job['id']}#{rnd}"
            if done[key] or sent >= a.max_requests:
                continue
            seed = int(hashlib.sha1(key.encode()).hexdigest()[:6], 16)
            try:
                c = llm_gemini.chat(MODEL, generation_prompt(job, schema, values, seed), max_tokens=12000, temperature=1.0)
            except llm_gemini.DailyQuotaExhausted as exc:
                print("stopped:", exc)
                return
            except LLMUnavailable as exc:
                print("request failed:", exc)
                continue
            sent += 1
            items = parse_json_array(c.text)
            jl_append(DATA / "hard_gen_raw.jsonl", {"job": key, "technique": job["technique"], "cluster": job["cluster"], "items": items, "finish": c.finish_reason})
            print(f"{key}: {len(items)} items ({c.finish_reason})", flush=True)
    print(f"{sent} requests sent")


def cmd_verify(_a) -> None:
    conn = db.connect("reader")
    seen = {norm_question(c["question"]) for c in jl_read(DATA / "candidates.jsonl")}
    seen_sql = {canonical_sql(c["sql"]) for c in jl_read(DATA / "candidates.jsonl") if c.get("sql")}
    out, stats = [], Counter()
    for rec in jl_read(DATA / "hard_gen_raw.jsonl"):
        for it in rec["items"]:
            q, sql = (it.get("question") or "").strip(), (it.get("sql") or "").strip().rstrip(";")
            if not q or not sql:
                stats["missing field"] += 1
                continue
            if norm_question(q) in seen or canonical_sql(sql) in seen_sql:
                stats["duplicate of the pool"] += 1
                continue
            seen.add(norm_question(q))
            seen_sql.add(canonical_sql(sql))
            status, info = run_sql(conn, sql)
            if status != "ok":
                stats[f"query {status}"] += 1
                continue
            out.append({"question": q, "technique": rec["technique"], "cluster": rec["cluster"], "difficulty": it.get("difficulty", ""), "job": rec["job"], "kind": "sql", "sql": sql, "rows": len(info)})
            stats["kept"] += 1
    for i, r in enumerate(out):
        r["id"] = f"H{i:05d}"
    (DATA / "hard_candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(dict(stats))


def cmd_answer(a) -> None:
    cands = jl_read(DATA / "hard_candidates.jsonl")
    done = {i["id"] for r in jl_read(DATA / "hard_blind_raw.jsonl") for i in r["items"] if i["reply"]}
    todo = [c for c in cands if c["id"] not in done]
    sent = 0
    for k in range(0, len(todo), 24):
        if sent >= a.max_requests:
            break
        batch = todo[k:k + 24]
        try:
            c = llm_gemini.chat(MODEL, answer_prompt(batch), max_tokens=12000, temperature=0.0)
        except llm_gemini.DailyQuotaExhausted as exc:
            print("stopped:", exc)
            return
        except LLMUnavailable as exc:
            print("request failed:", exc)
            continue
        sent += 1
        got = {str(d.get("id")): str(d.get("reply", "")) for d in parse_json_array(c.text)}
        jl_append(DATA / "hard_blind_raw.jsonl", {"items": [{"id": b["id"], "reply": got.get(b["id"], "")} for b in batch], "finish": c.finish_reason})
        print(f"batch {k // 24}: {len(got)}/{len(batch)} answered", flush=True)
    print(f"{sent} requests sent, {max(len(todo) - sent * 24, 0)} questions still to answer")


def _row(r: dict, source: str) -> dict:
    reply = sql_reply(r["sql"]) if r["kind"] == "sql" else r["reply"]
    return {**chat_example(tuned_system(r["question"], tables_of(r.get("sql"))), r["question"], reply), "id": r["id"], "technique": r["technique"], "kind": r["kind"], "source": source}


def cmd_build(a) -> None:
    conn = db.connect("reader")
    cands = jl_read(DATA / "hard_candidates.jsonl")
    blind = {i["id"]: i["reply"] for r in jl_read(DATA / "hard_blind_raw.jsonl") for i in r["items"]}
    leak = LeakFilter(tests_for_leaks(), 0.6)
    held = test_cells()
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    stats, kept = Counter(), []
    for c in cands:
        if c["id"] not in blind:
            stats["not yet answered"] += 1
            continue
        reply = blind[c["id"]].strip().strip("`").removeprefix("sql").strip()
        if reply.startswith("--"):
            stats["blind pass declined"] += 1
            continue
        status, info = run_sql(conn, reply)
        gstatus, ginfo = run_sql(conn, c["sql"])
        if status != "ok" or gstatus != "ok" or compare_results([tuple(r) for r in ginfo], [tuple(r) for r in info], False, 0.01) is None:
            stats["blind pass disagrees"] += 1
            continue
        if leak.why(c["question"], c["sql"]):
            stats["dropped: test look-alike"] += 1
            continue
        if filter_cells(c["sql"], cols) & held:
            stats["dropped: filters on a held-out cell"] += 1
            continue
        kept.append(c)
        stats["kept"] += 1
    rng = random.Random(17)
    rng.shuffle(kept)
    n_val = max(int(len(kept) * 0.06), 20)
    val_new, train_new = kept[:n_val], kept[n_val:]

    old = jl_read(DATA / "train.jsonl")
    cont2 = jl_read(DATA / "cont2_train.jsonl")
    dec = [r for r in old if r["messages"][-1]["content"].startswith("--")]
    easy = [r for r in old if not r["messages"][-1]["content"].startswith("--") and r.get("technique") in ("lookup_filter", "aggregate", "state_codes", "multi_join")]
    rng.shuffle(dec), rng.shuffle(easy), rng.shuffle(cont2)
    train_rows = [_row(r, "new_hard_teacher_verified") for r in train_new]
    train_rows += [{**r, "source": "replay_decline_train.jsonl"} for r in dec[:a.replay_decline]]
    train_rows += [{**r, "source": "replay_terse_cont2"} for r in cont2[:a.replay_cont2]]
    train_rows += [{**r, "source": "replay_easy_train.jsonl"} for r in easy[:a.replay_easy]]
    rng.shuffle(train_rows)
    val_rows = [_row(r, "new_hard_teacher_verified") for r in val_new]
    old_val = jl_read(DATA / "val.jsonl")
    val_rows += [{**r, "source": "replay_val.jsonl"} for r in rng.sample(old_val, min(len(old_val), 40))]
    for name, rows in (("hard_train", train_rows), ("hard_val", val_rows)):
        (DATA / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    by_source = Counter(r["source"] for r in train_rows)
    by_tech = Counter(r["technique"] for r in train_rows if r["source"].startswith("new_hard"))
    by_fam: Counter = Counter()
    for r in train_rows:
        if r["source"].startswith("new_hard"):
            by_fam[FAMILY_OF.get(r["technique"], r["technique"])] += 1
    rx: Counter = Counter()
    for r in train_rows:
        if r["source"].startswith("new_hard"):
            for f in families_of(r["messages"][1]["content"]) or ("no_router_cue",):
                rx[f] += 1
    report = {"filters": dict(stats), "train_rows": len(train_rows), "val_rows": len(val_rows), "by_source": dict(by_source), "new_hard_by_technique": dict(by_tech),
              "new_hard_by_family": dict(by_fam), "new_hard_by_router_regex_family": dict(rx)}
    (DATA / "hard_build_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--max-requests", type=int, default=30)
    g.add_argument("--rounds", type=int, default=2)
    sub.add_parser("verify")
    an = sub.add_parser("answer")
    an.add_argument("--max-requests", type=int, default=30)
    b = sub.add_parser("build")
    b.add_argument("--replay-decline", type=int, default=150)
    b.add_argument("--replay-cont2", type=int, default=120)
    b.add_argument("--replay-easy", type=int, default=100)
    a = ap.parse_args()
    {"generate": cmd_generate, "verify": cmd_verify, "answer": cmd_answer, "build": cmd_build}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
