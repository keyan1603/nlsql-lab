"""Leak and overlap checks for the held-out set (data/questions_heldout.json).

    python scripts/heldout_checks.py

1. Wording and query overlap with every existing evaluation file (core, hard, hard2, decline, dev, dev2), using nlsql.traindata.LeakFilter.
2. Wording and query overlap with every training question in train/data/*.jsonl (the assistant reply is the training query).
3. How many gold queries filter on a (table, column, value) cell (nlsql.traindata.filter_cells) that some training query also filters on.
   Those queries are reported, not dropped: a shared cell is a weak form of leakage the report has to state.
Writes docs/results/heldout_checks.json and prints a summary.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nlsql.schema_link import parse_schema                    # noqa: E402
from nlsql.traindata import LeakFilter, filter_cells          # noqa: E402

EVAL_FILES = ["questions.json", "questions_hard.json", "questions_hard2.json", "questions_decline.json", "dev_terse.json", "dev_counter.json"]
FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def load_set(name: str) -> list[dict]:
    d = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d["questions"]


def training_pairs() -> list[tuple[str, str | None, str]]:
    """(question, sql or None for a decline, source file) for every chat example in train/data/*.jsonl."""
    out = []
    for p in sorted((ROOT / "train" / "data").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            msgs = row.get("messages")
            if not msgs:
                continue
            user = next((m["content"] for m in msgs if m["role"] == "user"), None)
            asst = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
            if user is None:
                continue
            m = FENCE.search(asst)
            out.append((user, m.group(1).strip() if m else None, p.name))
    return out


def check(heldout: list[dict] | None = None) -> dict:
    held = heldout if heldout is not None else load_set("questions_heldout.json")
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    res: dict = {"questions": len(held)}

    # 1. against the existing evaluation sets
    existing = [q for f in EVAL_FILES for q in load_set(f)]
    lf = LeakFilter(existing)
    res["vs_eval_sets"] = [{"id": q["id"], "why": w} for q in held if (w := lf.why(q["question"], q.get("gold_sql")))]

    # 2. against the training questions (the filter is built from the held-out set)
    hf = LeakFilter(held)
    pairs = training_pairs()
    res["training_pairs"] = len(pairs)
    res["vs_training"] = [{"train_file": f, "question": q[:100], "why": w} for q, s, f in pairs if (w := hf.why(q, s))]

    # 3. shared filter cells
    train_cells: set = set()
    for _, sql, _ in pairs:
        if sql:
            train_cells |= filter_cells(sql, cols)
    shared = {}
    for q in held:
        if q.get("gold_sql"):
            cells = filter_cells(q["gold_sql"], cols)
            hit = sorted(map(list, cells & train_cells))
            if hit:
                shared[q["id"]] = hit
    gold = [q for q in held if q.get("gold_sql")]
    res["gold_queries"] = len(gold)
    res["gold_with_filter_cells"] = sum(1 for q in gold if filter_cells(q["gold_sql"], cols))
    res["gold_sharing_a_training_cell"] = len(shared)
    res["shared_cells"] = shared
    return res


def main() -> int:
    res = check()
    (ROOT / "docs" / "results" / "heldout_checks.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"held-out questions: {res['questions']}; training pairs scanned: {res['training_pairs']}")
    print(f"overlap with existing evaluation sets: {len(res['vs_eval_sets'])}")
    for r in res["vs_eval_sets"]:
        print("  ", r)
    print(f"overlap with training pairs: {len(res['vs_training'])}")
    for r in res["vs_training"][:20]:
        print("  ", r)
    print(f"gold queries: {res['gold_queries']}; with at least one filter cell: {res['gold_with_filter_cells']}; sharing a cell with training: {res['gold_sharing_a_training_cell']}")
    for k, v in res["shared_cells"].items():
        print("  ", k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
