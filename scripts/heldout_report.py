"""Assemble docs/results/heldout.md and heldout.json from the held-out runs and the earlier pool results (no model is called).

    python scripts/route_eval.py --local-run tuned6gguf
    python scripts/gate_eval.py --gate tuned6gguf --sql xiyan7b-final
    python scripts/heldout_report.py

The router rules and the invented-value check are frozen (git tag router-frozen). This script only reads their results.
Each strategy on the held-out set is set beside the same strategy on the original 181-question pool, once with the published
numbers (3B served from the Hugging Face weights, docs/results/routing.json and gate.json) and once recomputed with the Q8_0 GGUF
that the held-out run used, so the change of server is not mistaken for a change of questions.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import route_eval                                              # noqa: E402
from nlsql.router import FRONTIER, route                       # noqa: E402
from route_eval import wilson                                  # noqa: E402

RES = ROOT / "docs" / "results"
HELD = "held-out set ({n} questions)"
# (label, file kind, strategy-name prefix)
STRATS = [
    ("All hosted (gemini-3.5-flash-lite)", "route", "All hosted"),
    ("3B alone", "gate", "3B alone"),
    ("7B alone", "gate", "7B alone"),
    ("3B decline gate + 7B", "gate", "3B decline gate + 7B SQL"),
    ("3B decline gate + 7B, escalate on error, empty or invented value", "gate", "3B decline gate + 7B SQL, escalate"),
    ("Rules 1+ first, then 3B gate, then 7B with escalation", "gate", "Rules 1+ first"),
    ("3B gate first, then rules 1+, then 7B with escalation", "gate", "3B gate first, then rules 1+"),
    ("3B-only router: rules 1+, escalate on error, empty, decline or invented value", "route", "Rules 1+, plus escalate on error, empty, decline or invented"),
]


def pick(d: dict, prefix: str) -> dict:
    for k, v in d.items():
        if k.startswith(prefix):
            return v
    raise KeyError(prefix)


def pool_of(d: dict, start: str) -> dict:
    return next(v for k, v in d.items() if k.startswith(start))


def fmt(c: int, n: int) -> str:
    lo, hi = wilson(c, n)
    return f"{c} of {n} ({c / n:.1%}; {lo:.1%} to {hi:.1%})"


def rule_stats(rows: list[dict], t: int = 1) -> dict:
    routed = [r for r in rows if route(r["question"], t).target == FRONTIER]
    wrong = [r for r in rows if not r["local"]["passed"]]
    hit = [r for r in routed if not r["local"]["passed"]]
    rescued = [r for r in hit if r["hosted"]["passed"]]
    return {"n": len(rows), "routed": len(routed), "local_wrong": len(wrong), "local_wrong_routed": len(hit),
            "local_wrong_routed_hosted_right": len(rescued), "local_wrong_hosted_right": sum(1 for r in wrong if r["hosted"]["passed"]),
            "recall": len(hit) / len(wrong) if wrong else None, "precision": len(hit) / len(routed) if routed else None,
            "missed_ids": [r["qid"] for r in wrong if r not in routed], "false_alarm_ids": [r["qid"] for r in routed if r["local"]["passed"]]}


def main() -> int:
    local = sys.argv[sys.argv.index("--local-run") + 1] if "--local-run" in sys.argv else "tuned6gguf"
    route_new = json.loads((RES / f"routing_{local}.json").read_text(encoding="utf-8"))["strategies"]
    gate_new = json.loads((RES / f"gate_{local}_xiyan7b-final.json").read_text(encoding="utf-8"))
    route_old = json.loads((RES / "routing.json").read_text(encoding="utf-8"))["strategies"]
    gate_old = json.loads((RES / "gate.json").read_text(encoding="utf-8"))
    held_rows = route_eval.load_heldout(local)
    n = len(held_rows)
    hp = HELD.format(n=n)

    def get(kind: str, src: str, prefix: str, pool: str) -> dict:
        d = {("route", "new"): route_new, ("gate", "new"): gate_new, ("route", "old"): route_old, ("gate", "old"): gate_old}[(kind, src)]
        return pick(pool_of(d, pool), prefix)

    out: dict = {"local_run": local, "n_heldout": n, "frozen_commit": frozen_commit(), "strategies": {}, "splits": {}, "rules": {}}
    L: list[str] = []
    L += ["| Strategy | Held-out set | Original 181, published (3B from HF weights) | Original 181, recomputed with the same GGUF | Change vs published (points) | Cost per 1,000, held-out | Cost per 1,000, original |", "|---|---|---|---|---|---|---|"]
    for label, kind, prefix in STRATS:
        h = get(kind, "new", prefix, hp[:12])
        o_pub = get(kind, "old", prefix, "core + stress")
        o_new = get(kind, "new", prefix, "core + stress")
        delta = 100 * (h["correct"] / h["n"] - o_pub["correct"] / o_pub["n"])
        L.append(f"| {label} | {fmt(h['correct'], h['n'])} | {fmt(o_pub['correct'], o_pub['n'])} | {fmt(o_new['correct'], o_new['n'])} | {delta:+.1f} | ${h['usd_per_1000']:.2f} | ${o_pub['usd_per_1000']:.2f} |")
        out["strategies"][label] = {"heldout": h, "original_published": o_pub, "original_recomputed": o_new, "delta_points_vs_published": round(delta, 1)}
    main_table = L

    # splits of the held-out set
    S = ["| Strategy | Routine | Complex | Should decline | Answerable controls |", "|---|---|---|---|---|"]
    parts = [k for k in pool_of_keys(gate_new) if k.startswith("held-out, ")]
    for label, kind, prefix in STRATS:
        cells = []
        for part in ("routine", "complex", "should decline", "answerable controls"):
            key = next(k for k in parts if k.startswith(f"held-out, {part}"))
            d = get(kind, "new", prefix, key)
            cells.append(f"{d['correct']} of {d['n']}")
            out["splits"].setdefault(label, {})[part] = d
        S.append(f"| {label} | " + " | ".join(cells) + " |")

    # rules: recall and precision on the held-out set and on the original pool
    R = ["| Pool (local model) | Threshold | Routed to hosted | Local wrong | Local-wrong caught (recall) | Routed that were local-wrong (precision) | Caught and hosted right |", "|---|---|---|---|---|---|---|"]
    pools = {}
    for run in ("tuned6r2", local):
        route_eval.LOCAL_RUN = run
        pools[f"original 181 ({run})"] = [r for r in route_eval.load_all() if r["set"] != "decline"]
    pools[f"held-out, all {n} ({local})"] = held_rows
    pools[f"held-out, answerable only ({local})"] = [r for r in held_rows if not r["qid"].startswith(("HU", "HM"))]
    for name, rows in pools.items():
        for t in (1, 2):
            st = rule_stats(rows, t)
            out["rules"][f"{name} / {t}+"] = st
            R.append(f"| {name} | {t}+ | {st['routed']} of {st['n']} | {st['local_wrong']} | {st['local_wrong_routed']} of {st['local_wrong']} ({st['recall']:.0%}) | {st['local_wrong_routed']} of {st['routed']} ({(st['precision'] or 0):.0%}) | {st['local_wrong_routed_hosted_right']} |")

    head = ["# Held-out test of the frozen routing design", "",
            f"Frozen commit (last change to `nlsql/router.py` and `nlsql/invented.py`): `{out['frozen_commit']}`. Git tag `router-frozen` marks the HEAD at which the freeze was declared.", ""]
    body = ["## Held-out set, all strategies", ""] + main_table + ["", "## The held-out set by part", ""] + S + ["", "## Rule recall and precision (1+ and 2+ families)", ""] + R + [""]
    (RES / "heldout_tables.md").write_text("\n".join(head + body) + "\n", encoding="utf-8")
    (RES / "heldout.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(head + body))
    return 0


def pool_of_keys(d: dict):
    return list(d.keys())


def frozen_commit() -> str:
    r = subprocess.run(["git", "log", "-1", "--format=%H", "--", "nlsql/router.py", "nlsql/invented.py"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
