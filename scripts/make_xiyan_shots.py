"""Pick worked examples for the XiYan prompt from the TRAINING pairs only, keeping them clear of every test question.

    python scripts/make_xiyan_shots.py

Pool: train/data/train.jsonl. A pair is eligible only when
  - nlsql.traindata.LeakFilter finds no overlap with any question in the core, hard, hard2 or decline files (wording or gold query), and
  - an answerable pair's query filters on no (table, column, value) cell that a test gold query filters on (the rule of make_terse_data.py), and
  - an answerable pair runs on the database and returns rows.
Selection is by a fixed seed, never by looking at a model's score. Writes data/xiyan_shots.json.
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_terse_data import test_cells            # noqa: E402
from make_training_data import run_sql, tests_for_leaks   # noqa: E402
from nlsql import db                              # noqa: E402
from nlsql.schema_link import parse_schema        # noqa: E402
from nlsql.traindata import LeakFilter, filter_cells     # noqa: E402

SEED = 7
N_UNANSWERABLE, N_CLARIFY, N_ANSWER = 3, 3, 8


def main() -> int:
    rows = [json.loads(l) for l in (ROOT / "train" / "data" / "train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    leak = LeakFilter(tests_for_leaks())
    held = test_cells()
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    conn = db.connect("reader")
    pools = {"U": [], "C": [], "S": []}
    for r in rows:
        q, a = r["messages"][1]["content"], r["messages"][-1]["content"]
        kind = "U" if a.startswith("-- UNANSWERABLE") else "C" if a.startswith("-- CLARIFY") else "S"
        sql = None
        if kind == "S":
            sql = a.removeprefix("```sql").removesuffix("```").strip()
            if leak.why(q, sql) or (filter_cells(sql, cols) & held):
                continue
        elif leak.why(q, None):
            continue
        pools[kind].append((q, a, sql))
    print({k: len(v) for k, v in pools.items()})
    rng = random.Random(SEED)
    out = []
    for kind, n in (("U", N_UNANSWERABLE), ("C", N_CLARIFY)):
        pool = [p for p in pools[kind] if len(p[1]) < 170 and len(p[0]) < 140]
        for q, a, _ in rng.sample(pool, n):
            out.append({"id": f"X{len(out) + 1:02d}", "question": q, "decline": a})
    rng.shuffle(pools["S"])
    seen_tables: set = set()
    from nlsql.pipeline import _tables_of
    for q, a, sql in pools["S"]:
        if len(out) >= N_UNANSWERABLE + N_CLARIFY + N_ANSWER:
            break
        if len(sql) > 330:
            continue
        try:
            tabs = tuple(_tables_of(sql))
        except Exception:
            continue
        status, _ = run_sql(conn, sql)
        if status != "ok" or tabs in seen_tables:
            continue
        seen_tables.add(tabs)
        out.append({"id": f"X{len(out) + 1:02d}", "question": q, "sql": sql})
    path = ROOT / "data" / "xiyan_shots.json"
    path.write_text(json.dumps({"note": "Worked examples for the XiYan prompt, drawn from the training pairs only (seed 7) and cleared by LeakFilter and the held-out-cell rule against the core, hard, hard2 and decline sets. Built by scripts/make_xiyan_shots.py.",
                                "examples": out}, indent=1), encoding="utf-8")
    for e in out:
        print(e["id"], e["question"], "=>", (e.get("sql") or e["decline"])[:100])
    return 0


if __name__ == "__main__":
    sys.exit(main())
