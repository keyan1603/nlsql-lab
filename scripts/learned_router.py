"""Compare a small LEARNED router with the deterministic rules, from saved answers (no model is called).

    python scripts/learned_router.py [--gate tuned6r2] [--sql xiyan7b-final] [--sets core,hard,hard2]

The question: can a classifier decide "send this to the frontier model" as well as the hand-written regex rules in nlsql/router.py?

The classifier is trained ONLY on the teacher-written training questions (train/data/candidates.jsonl). Each training question
carries the technique it was generated for (window, time_bucket, evidence, cte_multistep, set_ops, correlated, ...), which is a label
that exists before and independent of any test result. The label is "hard" when the technique is one of the six reasoning families the
rules look for. No test question, test result or local-model failure is used in training or in choosing the model's settings, so the
comparison against the rules is fair in both directions (the rules, by contrast, were written after seeing the test categories).

The classifier is TF-IDF (word 1 to 2 grams) with logistic regression: tiny, runs in milliseconds on a CPU, needs no GPU and no
network, so it can sit in front of the local models inside a secure boundary.

Scoring uses the same strategy as scripts/gate_eval.py: router first, then the 3B decline gate, then the 7B with escalation on error,
empty result or invented value. Writes docs/results/learned_router.md and .json.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sklearn.feature_extraction.text import TfidfVectorizer                    # noqa: E402
from sklearn.linear_model import LogisticRegression                            # noqa: E402
from sklearn.metrics import precision_recall_fscore_support                    # noqa: E402
from sklearn.model_selection import cross_val_predict                          # noqa: E402
from sklearn.pipeline import make_pipeline                                     # noqa: E402

from cost_model import ASSUMPTIONS, usd                                        # noqa: E402
from nlsql.invented import invented_values                                     # noqa: E402
from nlsql.router import FRONTIER, route                                       # noqa: E402
from route_eval import SETS, jl, sign_p, status_of, wilson                     # noqa: E402

# The six reasoning families the deterministic rules cover, named by the technique the training generator was asked for.
HARD_TECHNIQUES = {"window", "time_bucket", "evidence", "cte_multistep", "set_ops", "correlated"}


def arg(name: str, default: str) -> str:
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a else default


def train_data() -> tuple[list[str], list[int]]:
    rows = [json.loads(l) for l in (ROOT / "train" / "data" / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r["question"] for r in rows], [int(r["technique"] in HARD_TECHNIQUES) for r in rows]


def build_model():
    # word 1-2 grams capture phrases such as "running total", "each month", "compared with the previous"; balanced class weights because
    # hard questions are a minority of the training pool
    return make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                         LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000))


def main() -> int:
    gate_run, sql_run, hosted_run = arg("--gate", "tuned6r2"), arg("--sql", "xiyan7b-final"), "gemini-flashlite"
    wanted = arg("--sets", "core,hard,hard2").split(",")
    qs_train, y = train_data()
    model = build_model()
    # sanity check on the training pool only: 5-fold cross-validated precision and recall of the "hard" label
    cv = cross_val_predict(model, qs_train, y, cv=5)
    prec, rec, f1, _ = precision_recall_fscore_support(y, cv, average="binary")
    model.fit(qs_train, y)

    power = json.loads((ROOT / "docs" / "results" / "power_measurement.json").read_text(encoding="utf-8"))
    watts = power["load_w_mean"] + ASSUMPTIONS["cpu_and_system_w"][0]
    kwh = ASSUMPTIONS["usd_per_kwh"][0]
    sec_cost = lambda s: watts * s / 3600 / 1000 * kwh
    hcost = lambda x: usd(x["h"]["tokens_in"], x["h"]["tokens_out"], "Standard")

    rows = []
    for s in wanted:
        hs, qf = SETS[s]
        d = json.loads((ROOT / "data" / f"{qf}.json").read_text(encoding="utf-8"))
        qs = {q["id"]: q for q in (d if isinstance(d, list) else d["questions"])}
        g, x, h = jl(ROOT / "runs" / f"{gate_run}-{s}.jsonl"), jl(ROOT / "runs" / f"{sql_run}-{s}.jsonl"), jl(ROOT / "runs" / f"{hosted_run}{hs}.jsonl")
        for qid, q in qs.items():
            if qid in g and qid in x and qid in h:
                rows.append({"set": s, "qid": qid, "question": q["question"], "g": g[qid], "x": x[qid], "h": h[qid]})
    probs = model.predict_proba([r["question"] for r in rows])[:, 1]
    for r, pr in zip(rows, probs):
        r["p"] = float(pr)
        r["rule"] = route(r["question"], 1).target == FRONTIER

    def pipeline(r, send):
        """router first; then the 3B gate; then the 7B, escalating on error, empty result or invented value"""
        if send(r):
            return r["h"]["passed"], hcost(r)
        gc = sec_cost(r["g"]["latency_s"])
        if r["g"]["kind"] != "sql":
            return r["g"]["passed"], gc
        c = gc + sec_cost(r["x"]["latency_s"])
        bad = status_of(r["x"]) in ("error", "empty") or (r["x"]["kind"] == "sql" and invented_values(r["question"], r["x"].get("sql") or ""))
        if bad:
            return r["h"]["passed"], c + hcost(r)
        return r["x"]["passed"], c

    n = len(rows)
    base = [r["h"]["passed"] for r in rows]
    wrong = [r for r in rows if not r["x"]["passed"]]       # questions the 7B alone gets wrong
    L = ["# Learned router versus deterministic rules", "",
         "Classifier: TF-IDF (word 1 to 2 grams) plus logistic regression, trained only on the "
         f"{len(qs_train)} teacher-written training questions (label: generated for a window, time-bucket, defined-term, multi-step, set-logic or correlated technique, "
         f"{sum(y)} of them). Training-pool 5-fold cross-validation: precision {prec:.2f}, recall {rec:.2f}, F1 {f1:.2f}. No test question, test result or local failure was used to train it or choose its settings. "
         f"Strategy: router, then 3B decline gate (`{gate_run}`), then 7B (`{sql_run}`) with escalation on error, empty or invented value; hosted reference `{hosted_run}`. "
         f"Pool: {', '.join(wanted)} ({n} questions). Single runs from saved answers.", "",
         "| Router | Sent to hosted by router | Catches the 7B's wrong answers (recall) | Of those sent, 7B was wrong (precision) | Correct | Accuracy (95% interval) | Cost per 1,000 | vs all hosted, sign test p |",
         "|---|---|---|---|---|---|---|---|"]
    out = {}

    def row(name, send):
        sent = [r for r in rows if send(r)]
        hit = [r for r in sent if not r["x"]["passed"]]
        res = [pipeline(r, send) for r in rows]
        k = sum(1 for pp, _ in res if pp)
        lo, hi = wilson(k, n)
        cost = sum(c for _, c in res) / n * 1000
        up = sum(1 for (pp, _), b in zip(res, base) if pp and not b)
        dn = sum(1 for (pp, _), b in zip(res, base) if b and not pp)
        L.append(f"| {name} | {len(sent)} of {n} ({len(sent) / n:.0%}) | {len(hit)} of {len(wrong)} ({len(hit) / max(len(wrong), 1):.0%}) | "
                 f"{len(hit)} of {len(sent)} ({len(hit) / max(len(sent), 1):.0%}) | {k} of {n} | {k / n:.1%} ({lo:.1%} to {hi:.1%}) | ${cost:.2f} | {sign_p(up, dn):.3f} ({up} up, {dn} down) |")
        out[name] = {"sent": len(sent), "recall_hits": len(hit), "correct": k, "n": n, "usd_per_1000": round(cost, 3)}

    row("No router (gate and 7B only)", lambda r: False)
    row("Deterministic rules, 1+ families", lambda r: r["rule"])
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        row(f"Learned classifier, p >= {t}", lambda r, t=t: r["p"] >= t)
    row("Rules OR classifier p >= 0.5", lambda r: r["rule"] or r["p"] >= 0.5)
    row("Rules AND classifier p >= 0.5", lambda r: r["rule"] and r["p"] >= 0.5)
    row("All hosted", lambda r: True)
    # reference: a router that ignores the question and sends the same share as the rules, picked at random. Exact expectation:
    # each question is sent with probability q, so its expected pass is q * hosted + (1 - q) * pipeline answer.
    q = sum(1 for r in rows if r["rule"]) / n
    exp_k = sum(q * float(r["h"]["passed"]) + (1 - q) * float(pipeline(r, lambda _: False)[0]) for r in rows)
    exp_c = sum(q * hcost(r) + (1 - q) * pipeline(r, lambda _: False)[1] for r in rows) / n * 1000
    L.append(f"| Reference: random router sending {q:.0%} (expected value) | {q * n:.0f} of {n} | {q * len(wrong):.0f} of {len(wrong)} ({q:.0%}) | {q:.0%} base rate | {exp_k:.1f} of {n} | {exp_k / n:.1%} | ${exp_c:.2f} | |")
    out["random router, same share as rules (expected)"] = {"correct": round(exp_k, 2), "n": n, "usd_per_1000": round(exp_c, 3)}
    L += ["", "The classifier threshold was not tuned on any test result: 0.5 is the default and the other rows show the trade-off. "
          "Agreement between rules and classifier on the pool: " + f"{sum(1 for r in rows if r['rule'] == (r['p'] >= 0.5))} of {n} questions get the same decision.", ""]
    (ROOT / "docs" / "results" / "learned_router.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "docs" / "results" / "learned_router.json").write_text(json.dumps({"cv": {"precision": prec, "recall": rec, "f1": f1}, "rows": out}, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
