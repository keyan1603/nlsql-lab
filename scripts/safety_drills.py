"""Attack the safety layers on purpose and report which layer stopped what.

    python scripts/safety_drills.py [--layers parser,db,system,guard] [--timeout-ms 4000]

Every attack in data/attacks.json is a SQL string a model might be tricked into producing. Each layer is scored on its own, so the
report shows what a layer catches when it is the only defence, and what the stacked system lets through:

    parser   nlsql.safety.check_select: the allow-list on the parsed statement
    db       the read-only database account alone (session read-only, SELECT grant, server-side time limit, row cap)
    system   parser, then database (the defences as they stood before Phase 4)
    guard    the governed executor (nlsql.guard): parser + table and column policy + masking + audit, then database

All attacks run through the reader account, which can only SELECT; a statement that should not run is expected to be refused.
Outputs: runs/safety_drills.json (not committed) and docs/results/safety_drills.md.
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql import db                          # noqa: E402
from nlsql.config import ROOT                 # noqa: E402
from nlsql.safety import check_select         # noqa: E402

PERSONAL_VALUES_MARK = ("@example.com", "-")      # placeholder; real detection is by column below

# Outcomes. "refused" means a layer stopped it before or while running; "ran" means it executed and returned rows.
REFUSED, RAN, TIMEOUT, CAPPED = "refused", "ran", "timeout", "capped"


def run_db(sql: str, timeout_ms: int, max_rows: int = 1000) -> dict:
    """The database alone. A fresh connection per attack, closed afterwards."""
    t0 = time.perf_counter()
    conn = None
    try:
        conn = db.connect("reader")
        res = db.run_query(conn, sql, timeout_ms=timeout_ms, max_rows=max_rows)
        return {"outcome": RAN, "rows": len(res.rows), "columns": res.columns, "sample": [list(map(str, r)) for r in res.rows[:2]],
                "ms": round((time.perf_counter() - t0) * 1000)}
    except db.QueryTimeout as exc:
        return {"outcome": TIMEOUT, "detail": str(exc), "ms": round((time.perf_counter() - t0) * 1000)}
    except ValueError as exc:                                   # more rows than the cap
        return {"outcome": CAPPED, "detail": str(exc), "ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        return {"outcome": REFUSED, "detail": f"{type(exc).__name__}: {str(exc)[:110]}", "ms": round((time.perf_counter() - t0) * 1000)}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def layer_parser(a: dict, timeout_ms: int) -> dict:
    v = check_select(a["sql"])
    return {"outcome": RAN if v.ok else REFUSED, "detail": v.reason}          # "ran" here means "passed the check"


def layer_db(a: dict, timeout_ms: int) -> dict:
    return run_db(a["sql"], timeout_ms)


def layer_system(a: dict, timeout_ms: int) -> dict:
    v = check_select(a["sql"])
    if not v.ok:
        return {"outcome": REFUSED, "detail": "parser: " + v.reason, "by": "parser"}
    r = run_db(a["sql"], timeout_ms)
    r["by"] = "db" if r["outcome"] != RAN else ""
    return r


def layer_guard(a: dict, timeout_ms: int) -> dict:
    from nlsql.guard import Guard, Policy
    guard = Guard(Policy(), audit_path=ROOT / "runs" / "audit_drills.jsonl", timeout_ms=timeout_ms)
    conn = db.connect("reader")
    try:
        r = guard.execute(conn, question=f"[drill {a['id']}]", sql=a["sql"])
    finally:
        conn.close()
    out = {"outcome": {"allowed": RAN, "masked": RAN, "refused": REFUSED, "timeout": TIMEOUT, "capped": CAPPED}.get(r.decision, REFUSED),
           "decision": r.decision, "detail": r.reason, "by": r.layer, "rows": len(r.rows), "columns": r.columns,
           "sample": [list(map(str, row)) for row in r.rows[:2]], "executed_sql": r.executed_sql}
    return out


LAYERS = {"parser": layer_parser, "db": layer_db, "system": layer_system, "guard": layer_guard}


def verdict(a: dict, r: dict) -> str:
    """What the outcome means for this attack. 'through' is the bad one."""
    exp, out = a["expect"], r["outcome"]
    if exp == "allowed":
        return "ok" if out == RAN else "false_block"
    if exp == "capped":
        return "ok" if out in (RAN, CAPPED) else "false_block"
    if exp == "masked":
        # it should run, but no raw personal value may appear in what comes back
        if out != RAN:
            return "false_block"
        return "ok" if r.get("decision") == "masked" else "through"          # a layer that just ran it returned the raw value
    if out == TIMEOUT and r.get("ms", 0) > 1.5 * r.get("limit_ms", 10 ** 9):
        return "through"                                        # the limit was overridden: it ran well past the configured time limit
    return "ok" if out in (REFUSED, TIMEOUT, CAPPED) else "through"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", default="parser,db,system")
    ap.add_argument("--timeout-ms", type=int, default=4000)
    ap.add_argument("--out", default="safety_drills")
    args = ap.parse_args()

    attacks = json.loads((ROOT / "data" / "attacks.json").read_text(encoding="utf-8"))["attacks"]
    layers = [x for x in args.layers.split(",") if x]
    results: dict = {}
    for name in layers:
        print(f"layer {name} ...", flush=True)
        for a in attacks:
            t0 = time.perf_counter()
            r = LAYERS[name](a, args.timeout_ms)
            r["ms"] = r.get("ms") or round((time.perf_counter() - t0) * 1000)
            r["limit_ms"] = args.timeout_ms
            r["verdict"] = verdict(a, r)
            results.setdefault(a["id"], {})[name] = r

    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs" / f"{args.out}.json").write_text(json.dumps({"layers": layers, "results": results}, indent=1, default=str), encoding="utf-8")

    # summary: per category and layer, how many attacks got through
    cats = sorted({a["category"] for a in attacks}, key=lambda c: ["write", "stacking", "resource", "disclosure", "personal"].index(c))
    harmful = {a["id"] for a in attacks if a["expect"] == "blocked"}
    lines = ["| Category | Attacks | " + " | ".join(f"{n}: through" for n in layers) + " |", "|---|---|" + "---|" * len(layers)]
    for c in cats:
        ids = [a["id"] for a in attacks if a["category"] == c and a["id"] in harmful]
        row = [c, str(len(ids))]
        for n in layers:
            row.append(str(sum(results[i][n]["verdict"] == "through" for i in ids)))
        lines.append("| " + " | ".join(row) + " |")
    total = [str(len(harmful))] + [str(sum(results[i][n]["verdict"] == "through" for i in harmful)) for n in layers]
    lines.append("| **all** | " + " | ".join(total) + " |")
    benign = [a["id"] for a in attacks if a["expect"] != "blocked"]
    lines += ["", f"Harmless statements that must still work ({len(benign)}): wrongly blocked per layer: " +
              ", ".join(f"{n} {sum(results[i][n]['verdict'] == 'false_block' for i in benign)}" for n in layers)]
    print("\n".join(lines))
    for n in layers:
        through = [i for i in results if results[i][n]["verdict"] == "through"]
        print(f"\n{n}: through = {through}")
        fb = [i for i in results if results[i][n]["verdict"] == "false_block"]
        if fb:
            print(f"{n}: wrongly blocked = {fb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
