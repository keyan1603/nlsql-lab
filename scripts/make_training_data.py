"""Build the fine-tuning set: question and query pairs for this lab's database, written by a teacher model and verified on the real database.

    python scripts/make_training_data.py plan                        # the generation jobs (technique x business area), deterministic
    python scripts/make_training_data.py values                      # sample values per column, from the database, for the teacher prompt
    python scripts/make_training_data.py generate --max-requests 40  # ask the teacher (resumable; stops at the free-tier cap)
    python scripts/make_training_data.py verify                      # run every candidate query; keep the ones that run and return rows
    python scripts/make_training_data.py answer --max-requests 40    # a second, blind pass: the teacher answers the questions without seeing its own query
    python scripts/make_training_data.py build                       # keep pairs where the two passes agree, drop test-set look-alikes, split, write

Teacher: gemini-3.5-flash-lite on the free tier, sent only the lab's synthetic schema (no private data exists in this lab).
Three filters stand between the teacher and the training set: the query must run and return rows on the real database; a second blind
answer from the teacher must return the same result (the pair is dropped when the two disagree); and the pair must not look like any
test question (nlsql/traindata.py). The gold queries of the test sets are used ONLY in that last filter, to throw pairs away.
"""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql import db, llm_gemini                            # noqa: E402
from nlsql.config import AS_OF_DATE, ROOT                   # noqa: E402
from nlsql.grader import compare_results                    # noqa: E402
from nlsql.llm import LLMUnavailable                        # noqa: E402
from nlsql.prompts import TUNED_SYSTEM, system_prompt       # noqa: E402
from nlsql.safety import check_select                       # noqa: E402
from nlsql.schema_link import m_schema, parse_schema        # noqa: E402
from nlsql.traindata import LeakFilter, canonical_sql, chat_example, norm_question, parse_json_array, sql_reply  # noqa: E402

DATA = ROOT / "train" / "data"
MODEL = "gemini-3.5-flash-lite"
PER_REQUEST = 24
SENSITIVE = ("email", "phone", "natl", "salary")

TECHNIQUES = {
    "lookup_filter": "single-table lookups and filters: one row by id, rows by status or tier code, date ranges, NULL checks, soft-deleted (inactive) rows, discontinued products",
    "aggregate": "GROUP BY with COUNT, SUM, AVG, MIN, MAX, HAVING, ORDER BY with LIMIT (always add a tie-breaker to the ORDER BY), COUNT(DISTINCT ...)",
    "multi_join": "three to five tables joined, including bridge tables (ord_promo, prod_supplier) and lookup tables; the join keys must be the right ones",
    "fanout": "questions where a careless join multiplies rows (orders joined to lines, payments, shipments or promotions): counts must use DISTINCT or pre-aggregation to stay correct",
    "date_time": "date arithmetic with explicit dates in the question: DATEDIFF, BETWEEN, month and quarter filters, customers who signed up in a period, ages of tickets in days",
    "time_bucket": "bucketing by month, week or quarter with DATE_FORMAT, YEAR, MONTH, QUARTER or DATE_SUB, one row per bucket in time order",
    "window": "window functions: RANK, DENSE_RANK, ROW_NUMBER, running totals, LAG, LEAD, top N per group, percent of total",
    "cte_multistep": "WITH clauses that build the answer in two or three steps: aggregate first then filter on the aggregate, cohort comparisons, percentages of a subset",
    "set_ops": "UNION, INTERSECT, EXCEPT, NOT EXISTS, NOT IN, customers who did A but never B, entities in both of two groups",
    "correlated": "correlated subqueries and EXISTS: rows above the average of their own group, the latest row per entity, entities with no matching rows",
    "pivot": "conditional aggregation, one row with several counts or sums side by side, SUM(CASE WHEN ...), COUNT(DISTINCT CASE WHEN ...), rates and ratios",
    "evidence": "the question first DEFINES a business term in a sentence (for example 'a late shipment is one delivered more than N days after it shipped') and then asks something that needs that definition",
    "hierarchy": "the employee reporting tree (emp.mgr_emp_id): direct reports, managers of managers, depth, chain of command, recursive WITH RECURSIVE queries, and department roll-ups",
    "state_codes": "questions that name a status, tier, region, channel or category in WORDS, so the query must use the stored CODE (read the column comments and the example values)",
}
CLUSTERS = {
    "orders": "cust_master, ord_hdr, ord_line, prod_catalog, fx_rate, code_lookup",
    "support": "support_tkt, tkt_event, refund_req, emp, policy_rule, cust_master, ord_hdr",
    "logistics": "shipment, warehouse, inventory, inv_move, payment, ord_hdr, prod_catalog",
    "marketing": "promo, ord_promo, web_event, cust_segment_hist, cust_master, ord_hdr",
    "supply": "supplier, prod_supplier, prod_catalog, inventory, inv_move, warehouse, ord_line",
}
PERSONAS = ["a finance analyst", "a customer support lead", "a warehouse and logistics manager", "a marketing analyst", "a sales operations manager",
            "a procurement manager", "an executive asking for a quick number", "a data analyst preparing a monthly report"]
DECLINES = {
    "unanswerable": ("questions the database CANNOT answer because the data does not exist in it (a fact, attribute, measure or history that no table or column holds). "
                     "Each reply is exactly one line: -- UNANSWERABLE: <short reason naming what is missing>. Make them sound like realistic business questions, "
                     "and make sure the topic really is absent: check every table and column before you choose it."),
    "ambiguous": ("questions that are TOO VAGUE to answer without guessing: they leave out which measure, period, currency, status or which of several meanings to use. "
                  "Each reply is exactly one line: -- CLARIFY: <the question you need answered>. The missing detail must be genuinely needed; do not pick questions that have an obvious default."),
}


def plan() -> list[dict]:
    jobs = []
    for ti, (tech, tdesc) in enumerate(TECHNIQUES.items()):
        for ci, (cl, tabs) in enumerate(CLUSTERS.items()):
            jobs.append({"id": f"{tech}.{cl}", "kind": "sql", "technique": tech, "technique_desc": tdesc, "cluster": cl, "tables": tabs,
                         "persona": PERSONAS[(ti * 3 + ci) % len(PERSONAS)]})
    for kind, desc in DECLINES.items():
        for ci, (cl, tabs) in enumerate(CLUSTERS.items()):
            for rep in range(2):
                jobs.append({"id": f"decline_{kind}.{cl}.{rep}", "kind": kind, "technique": f"decline_{kind}", "technique_desc": desc, "cluster": cl, "tables": tabs,
                             "persona": PERSONAS[(ci + rep * 4) % len(PERSONAS)]})
    return jobs


# ---------------------------------------------------------------------------------------------------- prompts
SQL_RULES = f"""SQL rules, all mandatory:
- MySQL 8, exactly one read-only statement (SELECT, or WITH ... SELECT). No NOW(), CURDATE() or CURRENT_DATE: the data runs up to {AS_OF_DATE}, and every date a question depends on is written into the question as an explicit date (for example 'since 2026-03-01', 'in Q2 2026').
- Use only tables and columns in the schema. Stored values are CODES (see the column comments and example values), so the query uses the code even when the question says the word.
- The question says exactly which columns to show and in what order ('Show the carrier code and the count'), the way a person briefing an analyst would, so there is one right output shape. Sort the result only when the question asks for an order, and then break ties explicitly.
- Never select salary_amt or natl_id, and avoid email_addr and phone_no. Do not use SELECT *.
- The query must return at least one row on the real data. Use values that appear in the example values or that you can reason exist (ids follow the patterns shown)."""


def generation_prompt(job: dict, schema: str, values: dict, seed: int) -> list[dict]:
    focus = [t.strip() for t in job["tables"].split(",")]
    vals = "\n".join(f"{t}.{c}: {', '.join(map(str, v))}" for t in focus for c, v in (values.get(t) or {}).items())
    head = ("You write training data for a text-to-SQL model that will be specialised for ONE database. Write questions the way busy colleagues really ask them, "
            "in plain business language, and vary the wording, the length and the way each is phrased. Never reuse a question you have already written in this answer.")
    if job["kind"] == "sql":
        task = (f"Write {PER_REQUEST} different question and MySQL query pairs for this database, as {job['persona']} would ask. Technique focus: {job['technique_desc']}.\n"
                f"Business area: the tables {job['tables']} (other tables may be joined in when needed). Mix of difficulty: about a third easy, a third medium, a third hard.\n\n{SQL_RULES}\n\n"
                'Reply with ONLY a JSON array of objects: {"question": "...", "sql": "...", "difficulty": "easy|medium|hard"}.')
    else:
        tag = "UNANSWERABLE" if job["kind"] == "unanswerable" else "CLARIFY"
        task = (f"Write {PER_REQUEST} different {job['kind']} questions for this database, as {job['persona']} would ask: {job['technique_desc']}\n"
                f"Business area: around the tables {job['tables']}. Mix obvious and subtle ones.\n\n"
                'Reply with ONLY a JSON array of objects: {"question": "...", "reply": "-- ' + tag + ': ...", "difficulty": "easy|medium|hard"}.')
    user = f"{head}\n\nDatabase schema with example values:\n{schema}\n\nMore example values for the business area:\n{vals}\n\n{task}\n\n(Variation seed: {seed}.)"
    return [{"role": "user", "content": user}]


def answer_prompt(items: list[dict]) -> list[dict]:
    qs = "\n".join(json.dumps({"id": i["id"], "question": i["question"]}) for i in items)
    user = (f"Answer each of the following {len(items)} questions independently, following the rules above. "
            'Reply with ONLY a JSON array of objects {"id": <the id>, "reply": "<exactly what the rules ask a reply to be: the SQL statement without a code fence, or the one -- UNANSWERABLE / -- CLARIFY line>"}.\n\n' + qs)
    return [{"role": "system", "content": system_prompt(True, True)}, {"role": "user", "content": user}]


# ---------------------------------------------------------------------------------------------------- helpers
def jl_read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def jl_append(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def tests_for_leaks() -> list[dict]:
    out = []
    for f in ("questions", "questions_hard", "questions_hard2", "questions_decline"):
        d = json.loads((ROOT / "data" / f"{f}.json").read_text(encoding="utf-8"))
        out += d if isinstance(d, list) else d["questions"]
    return out


def run_sql(conn, sql: str):
    safe = check_select(sql)
    if not safe.ok:
        return "unsafe", safe.reason
    try:
        r = db.run_query(conn, sql.strip().rstrip(";"), timeout_ms=5000, max_rows=1000)
    except db.QueryTimeout:
        return "timeout", "timeout"
    except Exception as exc:
        return "error", str(exc)[:160]
    return ("ok", r.rows) if r.rows else ("empty", [])


# ---------------------------------------------------------------------------------------------------- stages
def cmd_values(_a) -> None:
    conn = db.connect("reader")
    out = {}
    for t in parse_schema(True):
        cols = {}
        for c in t.columns:
            if any(s in c.name for s in SENSITIVE):
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT {c.name}, COUNT(*) n FROM {t.name} GROUP BY {c.name} ORDER BY n DESC, {c.name} LIMIT 8")
                    vals = [str(r[0]) for r in cur.fetchall() if r[0] is not None]
            except Exception:
                continue
            if vals and max(len(v) for v in vals) <= 40:
                cols[c.name] = vals
        out[t.name] = cols
    (DATA / "values.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"values for {len(out)} tables written")


def cmd_generate(a) -> None:
    jobs = json.loads((DATA / "jobs.json").read_text(encoding="utf-8"))
    values = json.loads((DATA / "values.json").read_text(encoding="utf-8"))
    schema = m_schema(parse_schema(True))
    done = Counter(r["job"] for r in jl_read(DATA / "gen_raw.jsonl"))
    sent = 0
    for job in sorted(jobs, key=lambda j: list(CLUSTERS).index(j["cluster"])):         # business-area-major, so a partial run still covers every technique
        if a.techniques and job["technique"] not in a.techniques.split(","):
            continue
        for rnd in range(a.rounds):
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
            jl_append(DATA / "gen_raw.jsonl", {"job": key, "kind": job["kind"], "technique": job["technique"], "cluster": job["cluster"], "items": items,
                                               "tokens_in": c.tokens_in, "tokens_out": c.tokens_out, "finish": c.finish_reason})
            print(f"{key}: {len(items)} items ({c.finish_reason}, {c.tokens_out} out tokens)", flush=True)
    print(f"{sent} requests sent")


def cmd_verify(_a) -> None:
    conn = db.connect("reader")
    out, seen, stats = [], set(), Counter()
    for rec in jl_read(DATA / "gen_raw.jsonl"):
        for it in rec["items"]:
            q = (it.get("question") or "").strip()
            if not q:
                stats["no question"] += 1
                continue
            key = norm_question(q)
            if key in seen:
                stats["duplicate question"] += 1
                continue
            seen.add(key)
            base = {"question": q, "technique": rec["technique"], "cluster": rec["cluster"], "difficulty": it.get("difficulty", ""), "job": rec["job"]}
            if rec["kind"] == "sql":
                sql = (it.get("sql") or "").strip().rstrip(";")
                if not sql:
                    stats["no sql"] += 1
                    continue
                status, info = run_sql(conn, sql)
                if status != "ok":
                    stats[f"query {status}"] += 1
                    continue
                out.append({**base, "kind": "sql", "sql": sql, "rows": len(info)})
                stats["kept"] += 1
            else:
                reply = (it.get("reply") or "").strip()
                tag = "-- UNANSWERABLE:" if rec["kind"] == "unanswerable" else "-- CLARIFY:"
                if not reply.startswith(tag) or "\n" in reply or len(reply) < len(tag) + 8:
                    stats["bad decline reply"] += 1
                    continue
                out.append({**base, "kind": rec["kind"], "reply": reply})
                stats["kept"] += 1
    for i, r in enumerate(out):
        r["id"] = f"T{i:05d}"
    (DATA / "candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(dict(stats))


def cmd_answer(a) -> None:
    cands = jl_read(DATA / "candidates.jsonl")
    done = {i["id"] for r in jl_read(DATA / "blind_raw.jsonl") for i in r["items"]}
    todo = [c for c in cands if c["id"] not in done]
    sent = 0
    for k in range(0, len(todo), PER_REQUEST):
        if sent >= a.max_requests:
            break
        batch = todo[k:k + PER_REQUEST]
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
        jl_append(DATA / "blind_raw.jsonl", {"items": [{"id": b["id"], "reply": got.get(b["id"], "")} for b in batch], "finish": c.finish_reason})
        print(f"batch {k // PER_REQUEST}: {len(got)}/{len(batch)} answered", flush=True)
    print(f"{sent} requests sent, {max(len(todo) - sent * PER_REQUEST, 0)} questions still to answer")


def cmd_build(a) -> None:
    conn = db.connect("reader")
    cands = jl_read(DATA / "candidates.jsonl")
    blind = {i["id"]: i["reply"] for r in jl_read(DATA / "blind_raw.jsonl") for i in r["items"]}
    leak = LeakFilter(tests_for_leaks(), a.threshold)
    stats, kept = Counter(), []
    seen_sql = set()
    for c in cands:
        if c["id"] not in blind:
            stats["not yet answered"] += 1
            continue
        reply = blind[c["id"]].strip().strip("`").removeprefix("sql").strip()
        if c["kind"] == "sql":
            if reply.startswith("--"):
                stats["blind pass declined"] += 1
                continue
            status, info = run_sql(conn, reply)
            gstatus, ginfo = run_sql(conn, c["sql"])
            if status != "ok" or gstatus != "ok" or compare_results([tuple(r) for r in ginfo], [tuple(r) for r in info], False, 0.01) is None:
                stats["blind pass disagrees"] += 1
                continue
            canon = canonical_sql(c["sql"])
            if canon in seen_sql:
                stats["duplicate query"] += 1
                continue
            seen_sql.add(canon)
        else:
            tag = "-- UNANSWERABLE" if c["kind"] == "unanswerable" else "-- CLARIFY"
            if not reply.startswith(tag):
                stats["blind pass disagrees"] += 1
                continue
        why = leak.why(c["question"], c.get("sql"))
        if why:
            stats["dropped as a test look-alike"] += 1
            continue
        kept.append(c)
        stats["kept"] += 1
    rng = random.Random(7)
    rng.shuffle(kept)
    n_val = max(int(len(kept) * 0.06), 20)
    val, train = kept[:n_val], kept[n_val:]
    for name, rows in (("train", train), ("val", val)):
        text = ""
        for r in rows:
            reply = sql_reply(r["sql"]) if r["kind"] == "sql" else r["reply"]
            text += json.dumps({**chat_example(TUNED_SYSTEM, r["question"], reply), "id": r["id"], "technique": r["technique"], "kind": r["kind"]}, ensure_ascii=False) + "\n"
        (DATA / f"{name}.jsonl").write_text(text, encoding="utf-8")
    by = Counter(r["technique"] for r in train)
    print(dict(stats), "\ntrain", len(train), "val", len(val), "\nby technique", dict(by))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("values")
    g = sub.add_parser("generate")
    g.add_argument("--max-requests", type=int, default=40)
    g.add_argument("--techniques", help="comma separated technique names to run (default: all)")
    g.add_argument("--rounds", type=int, default=1, help="passes over the job list; round 2 asks the same jobs again with a different variation seed")
    sub.add_parser("verify")
    an = sub.add_parser("answer")
    an.add_argument("--max-requests", type=int, default=40)
    b = sub.add_parser("build")
    b.add_argument("--threshold", type=float, default=0.6, help="question word overlap (Jaccard) at or above which a pair counts as a test look-alike")
    a = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    if a.cmd == "plan":
        jobs = plan()
        (DATA / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
        print(len(jobs), "jobs")
    else:
        {"values": cmd_values, "generate": cmd_generate, "verify": cmd_verify, "answer": cmd_answer, "build": cmd_build}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
