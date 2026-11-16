"""Per-category scores from saved answers, set beside how many training pairs each category had (no model is called).

    python scripts/category_breakdown.py

For each test category (pool = core + hard + hard2, answerable only, and the held-out set separately): the fine-tuned 7B, the prompt-only 7B, the tuned 3B,
the hosted model, and the number of Kaggle training pairs whose technique has the same name. Writes docs/results/category_breakdown.md.
"""

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from route_eval import SETS, jl     # noqa: E402

MODELS = {"tuned 7B": "xiyan7bft-e2", "prompt 7B": "xiyan7b-final", "tuned 3B": "tuned6r2", "hosted": None}


def run_path(model: str | None, s: str) -> Path:
    if model is None:
        return ROOT / "runs" / f"gemini-flashlite{SETS[s][0]}.jsonl"
    if model == "tuned6r2" and s == "heldout":              # the held-out 3B answers were saved from the packaged GGUF run
        model = "tuned6gguf"
    return ROOT / "runs" / f"{model}-{s}.jsonl"


def questions(s: str) -> dict:
    d = json.loads((ROOT / "data" / f"{SETS[s][1]}.json").read_text(encoding="utf-8"))
    return {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}


def main() -> int:
    train = collections.Counter()
    for f in ("strict_train", "hard_train"):                # the two files the Kaggle run trained on
        for line in (ROOT / "train" / "data" / f"{f}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                train[json.loads(line)["technique"]] += 1
    out = ["# Where the fine-tuned 7B loses: per category, with the training pairs each category had", "",
           "Computed from saved single-run answers. Pool = core + hard + hard2 (answerable). Held-out is separate. 'Training pairs' counts the pairs (strict train + the hard continuation file) whose technique has the same name as the test category; a category with no matching technique shows 0.", ""]
    for pool, sets in (("Pool (core, hard, hard2)", ["core", "hard", "hard2"]), ("Held-out (52)", ["heldout"])):
        agg = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
        err = collections.Counter()
        for s in sets:
            qs = questions(s)
            runs = {m: jl(run_path(p, s)) for m, p in MODELS.items()}
            for qid, q in qs.items():
                if q.get("expected") in ("decline", "clarify") or q["category"].startswith(("decline", "unans", "ambig")):
                    continue
                if not all(qid in r for r in runs.values()):
                    continue
                c = q["category"]
                for m, r in runs.items():
                    agg[c][m][1] += 1
                    agg[c][m][0] += bool(r[qid]["passed"])
                if not runs["tuned 7B"][qid]["passed"]:
                    err[(c, runs["tuned 7B"][qid]["outcome"])] += 1
        out += [f"## {pool}", "", "| Category | Questions | Tuned 7B | Prompt 7B | Tuned 3B | Hosted | Training pairs | Tuned 7B misses: wrong result / SQL error |", "|---|---|---|---|---|---|---|---|"]
        for c, d in sorted(agg.items(), key=lambda kv: -(kv[1]["hosted"][1])):
            n = d["hosted"][1]
            wr = sum(v for (cc, o), v in err.items() if cc == c and o != "sql_error")
            se = err[(c, "sql_error")]
            out.append(f"| {c} | {n} | {d['tuned 7B'][0]} | {d['prompt 7B'][0]} | {d['tuned 3B'][0]} | {d['hosted'][0]} | {train.get(c, 0)} | {wr} / {se} |")
        out.append("")
    (ROOT / "docs" / "results" / "category_breakdown.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
