"""Counter-examples for the terse-question fix: teach "answer exactly what was asked, add no condition nobody asked for".

    python scripts/make_counter_data.py

Run 5 (terse counts and lookups) removed the false declines but introduced a new habit: queries with an invented filter (a severity level,
a ship status, a year) or an invented column (a customer id on a table that has none). The terse training pairs were all "count rows where
a code column equals a value", which probably taught "add a code filter". This script adds, with no teacher call and every query executed
on the real database (nonempty result required):
  * list and join questions with exactly one filter and nothing else
  * lookups that go through an intermediate table (customer behind a shipment or refund; SKUs of a customer)
  * "which X has the most Y" with LIMIT 1 (ties are dropped), distinct counts over a one-to-many join, and a literal date used as given
Test hygiene is the same as make_terse_data.py: a (table, column, value) cell that a test gold query filters on is never used, LeakFilter drops
near-copies of test questions and queries, and the second dev set (data/dev_counter.json) uses values and shapes no training pair touches.
The families were chosen after reading the run-5 failures on the core test set, so the core result is less independent than before; the
second dev set is the independent check.
Writes train/data/cont2_train.jsonl (the run-5 continuation set plus the counter-examples) and cont2_val.jsonl.
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from make_terse_data import DEV_CELLS, cond, test_cells                         # noqa: E402
from make_training_data import DATA, ROOT, db, run_sql, tables_of, tests_for_leaks    # noqa: E402
from nlsql.prompts import tuned_system                                          # noqa: E402
from nlsql.traindata import LeakFilter, chat_example, norm_question, sql_reply  # noqa: E402

# (alias, table, template name, question, query with {c} for the condition)
FILTER_T = [
    ("o", "ord_hdr", ["List the names of the customers who have at least one {p}.", "Which customers have at least one {p}? Show their names."],
     "SELECT DISTINCT c.cust_nm FROM cust_master c JOIN ord_hdr o ON o.cust_id = c.cust_id WHERE {c}"),
    ("o", "ord_hdr", ["Show the order id and the customer name for every {p}.", "For each {p}, list the order id and the customer's name."],
     "SELECT o.ord_id, c.cust_nm FROM ord_hdr o JOIN cust_master c ON c.cust_id = o.cust_id WHERE {c}"),
    ("t", "support_tkt", ["Show the ticket id and the customer name for every {p}.", "For each {p}, list the ticket id and the customer's name."],
     "SELECT t.tkt_id, c.cust_nm FROM support_tkt t JOIN cust_master c ON c.cust_id = t.cust_id WHERE {c}"),
    ("t", "support_tkt", ["Which employees are assigned to {pp}? Show their names."],
     "SELECT DISTINCT e.emp_nm FROM support_tkt t JOIN emp e ON e.emp_id = t.assigned_emp_id WHERE {c}"),
]
# (table, column, value, phrase singular, phrase plural)
TRAIN_VALUES = {
    "ord_hdr": [("ord_status", "S", "shipped order"), ("ord_status", "D", "delivered order"), ("ord_status", "N", "new order"), ("ord_status", "C", "cancelled order"),
                ("channel_cd", "WEB", "order placed on the website"), ("channel_cd", "PHN", "order placed by phone"), ("channel_cd", "APP", "order placed in the mobile app")],
    "support_tkt": [("categ_cd", "BILL", "billing ticket"), ("categ_cd", "SHIP", "shipping ticket"), ("categ_cd", "TECH", "technical ticket"), ("categ_cd", "ACCT", "account ticket"),
                    ("categ_cd", "REFD", "refund ticket"), ("sev_lvl", "2", "high-severity ticket"), ("sev_lvl", "3", "medium-severity ticket"), ("channel_cd", "WEB", "ticket raised on the website")],
}
DEV_VALUES = {"ord_hdr": [("channel_cd", "STR", "order placed in store")], "support_tkt": [("sev_lvl", "4", "low-severity ticket")]}

# tables that reach the customer through the order: (table, alias, id column, train values, dev values)
VIA_ORDER = [
    ("shipment", "s", "ship_id",
     [("carrier_cd", "UPS", "UPS shipment"), ("carrier_cd", "FDX", "FedEx shipment"), ("carrier_cd", "USP", "USPS shipment"), ("ship_status", "I", "shipment in transit"), ("ship_status", "D", "delivered shipment")],
     [("carrier_cd", "DHL", "DHL shipment")]),
    ("payment", "p", "pay_id",
     [("method_cd", "CC", "card payment"), ("method_cd", "PP", "PayPal payment"), ("pay_status", "S", "settled payment"), ("pay_status", "R", "refunded payment")],
     [("pay_status", "F", "failed payment"), ("method_cd", "GC", "gift card payment"), ("method_cd", "BT", "bank transfer payment")]),
    ("refund_req", "r", "rfd_id",
     [("status_cd", "P", "pending refund request"), ("status_cd", "A", "approved refund request"), ("status_cd", "D", "denied refund request"),
      ("reason_cd", "LAT", "refund request for late delivery"), ("reason_cd", "OTH", "refund request for other reasons")],
     [("reason_cd", "DMG", "refund request for damaged goods")]),
]
# lookups through an intermediate table: (name, id query, question formats, query)
HOPS = [
    ("shipment_customer", "SELECT ship_id FROM shipment", ["Who is the customer for shipment {x}?", "Which customer is shipment {x} for?"],
     "SELECT c.cust_nm FROM shipment s JOIN ord_hdr o ON o.ord_id = s.ord_id JOIN cust_master c ON c.cust_id = o.cust_id WHERE s.ship_id = '{x}'"),
    ("refund_customer", "SELECT rfd_id FROM refund_req", ["What is the name of the customer behind refund request {x}?", "Which customer asked for refund request {x}?"],
     "SELECT c.cust_nm FROM refund_req r JOIN ord_hdr o ON o.ord_id = r.ord_id JOIN cust_master c ON c.cust_id = o.cust_id WHERE r.rfd_id = '{x}'"),
    ("customer_skus", "SELECT DISTINCT cust_id FROM ord_hdr", ["Which SKUs has customer {x} ordered?", "List the SKUs customer {x} has bought, without repeats."],
     "SELECT DISTINCT l.sku FROM ord_line l JOIN ord_hdr o ON o.ord_id = l.ord_id WHERE o.cust_id = '{x}'"),
    ("customer_line_count", "SELECT DISTINCT cust_id FROM ord_hdr", ["How many order lines does customer {x} have?", "Count the order lines of customer {x}."],
     "SELECT COUNT(*) FROM ord_line l JOIN ord_hdr o ON o.ord_id = l.ord_id WHERE o.cust_id = '{x}'"),
    ("customer_tickets", "SELECT DISTINCT cust_id FROM support_tkt", ["Which tickets has customer {x} raised?", "List the ticket ids of customer {x}."],
     "SELECT tkt_id FROM support_tkt WHERE cust_id = '{x}'"),
    ("customer_orders", "SELECT DISTINCT cust_id FROM ord_hdr", ["List the order ids of customer {x}.", "Which orders did customer {x} place?"],
     "SELECT ord_id FROM ord_hdr WHERE cust_id = '{x}'"),
]
DEV_HOPS = [
    ("ticket_assignee_dept", "SELECT tkt_id FROM support_tkt WHERE assigned_emp_id IS NOT NULL", ["Which department does the employee on ticket {x} work in?"],
     "SELECT e.dept_cd FROM support_tkt t JOIN emp e ON e.emp_id = t.assigned_emp_id WHERE t.tkt_id = '{x}'"),
    ("shipment_order_status", "SELECT ship_id FROM shipment", ["What is the status of the order that shipment {x} belongs to?"],
     "SELECT o.ord_status FROM shipment s JOIN ord_hdr o ON o.ord_id = s.ord_id WHERE s.ship_id = '{x}'"),
]
# "which X has the most/fewest Y": (question, table, column, direction)
TOP1 = [("Which carrier has the most shipments? Show the carrier and the count.", "shipment", "carrier_cd", "DESC"),
        ("Which sales channel has the most orders? Show the channel and the number of orders.", "ord_hdr", "channel_cd", "DESC"),
        ("Which category has the most tickets? Show the category and the count.", "support_tkt", "categ_cd", "DESC"),
        ("Which region has the most customers? Show the region and the count.", "cust_master", "region_cd", "DESC"),
        ("Which department has the most employees? Show the department and the headcount.", "emp", "dept_cd", "DESC"),
        ("Which event type is the most common in the web event log? Show the type and the count.", "web_event", "evt_type", "DESC"),
        ("Which customer tier has the fewest customers? Show the tier and the count.", "cust_master", "tier_cd", "ASC"),
        ("Which reason code is used most in refund requests? Show the code and the count.", "refund_req", "reason_cd", "DESC")]
DEV_TOP1 = [("Which payment method has the most payments? Show the method and the count.", "payment", "method_cd", "DESC"),
            ("Which warehouse has sent the most shipments? Show the warehouse id and the count.", "shipment", "wh_id", "DESC")]
# distinct counts over a one-to-many join: (question, query)
DISTINCT = [(f"How many orders have at least one line with quantity above {k}?", f"SELECT COUNT(DISTINCT ord_id) FROM ord_line WHERE qty > {k}") for k in (2, 3, 5)]
DISTINCT += [(f"How many customers have raised at least one {p} ticket?", f"SELECT COUNT(DISTINCT cust_id) FROM support_tkt WHERE categ_cd = '{v}'")
             for v, p in (("BILL", "billing"), ("TECH", "technical"), ("SHIP", "shipping"))]
DEV_DISTINCT = [("How many orders have at least one failed payment?", "SELECT COUNT(DISTINCT ord_id) FROM payment WHERE pay_status = 'F'", ("payment", "pay_status", "F")),
                ("How many orders have at least one line with quantity above 4?", "SELECT COUNT(DISTINCT ord_id) FROM ord_line WHERE qty > 4", None),
                ("How many orders have at least one refund request?", "SELECT COUNT(DISTINCT ord_id) FROM refund_req", None)]
# a literal date in the question is used as given (no NOW())
DATES = [(f"How many orders were placed before {d}?", f"SELECT COUNT(*) FROM ord_hdr WHERE ord_dt < '{d}'") for d in ("2026-03-01", "2026-06-01", "2026-09-01")]
DATES += [(f"How many refund requests were made on or after {d}?", f"SELECT COUNT(*) FROM refund_req WHERE req_dt >= '{d}'") for d in ("2026-04-01", "2026-07-01")]
DATES += [(f"How many tickets were opened on or after {d}?", f"SELECT COUNT(*) FROM support_tkt WHERE opened_ts >= '{d}'") for d in ("2026-05-01", "2026-08-01")]
DEV_DATES = [("How many orders were placed on or after 2026-08-15?", "SELECT COUNT(*) FROM ord_hdr WHERE ord_dt >= '2026-08-15'"),
             ("How many refund requests were made before 2026-05-15?", "SELECT COUNT(*) FROM refund_req WHERE req_dt < '2026-05-15'")]


def main() -> int:
    rng = random.Random(31)
    conn = db.connect("reader")
    held = test_cells()
    dev_t = set(DEV_CELLS)
    leak = LeakFilter(tests_for_leaks(), 0.6)
    stats: Counter = Counter()
    train, dev = [], []

    def ok_rows(sql):
        """(usable, rows): the query runs, returns rows, and a lone count is not zero"""
        status, rows = run_sql(conn, sql)
        usable = status == "ok" and bool(rows) and not (len(rows) == 1 and len(rows[0]) == 1 and not rows[0][0])
        return usable, rows

    def add(bucket, technique, question, sql):
        bucket.append({"question": question, "sql": sql, "technique": technique, "kind": "sql"})

    # one-filter list and join questions
    for values, bucket, is_dev in ((TRAIN_VALUES, train, False), (DEV_VALUES, dev, True)):
        for alias, table, qfmts, sfmt in FILTER_T:
            for col, val, p in values[table]:
                cell = (table, col, val)
                if cell in held or (not is_dev and cell in dev_t):
                    stats["filter cell held out"] += 1
                    continue
                pp = p + "s" if p.endswith("ticket") or p.endswith("order") else None
                for qf in (qfmts[:1] if is_dev else qfmts):
                    if "{pp}" in qf and pp is None:
                        continue
                    sql = sfmt.format(c=f"{alias}.{cond(col, val)}")
                    good, _ = ok_rows(sql)
                    if good:
                        add(bucket, "one_filter_join", qf.format(p=p, pp=pp), sql)
                    else:
                        stats["filter query empty"] += 1
    # the same shapes for tables that reach the customer through the order
    for table, alias, idcol, values, dev_values in VIA_ORDER:
        for vals, bucket, is_dev in ((values, train, False), (dev_values, dev, True)):
            for col, val, p in vals:
                cell = (table, col, val)
                if cell in held or (not is_dev and cell in dev_t):
                    stats["filter cell held out"] += 1
                    continue
                c = f"{alias}.{cond(col, val)}"
                join = f"FROM {table} {alias} JOIN ord_hdr o ON o.ord_id = {alias}.ord_id JOIN cust_master c ON c.cust_id = o.cust_id WHERE {c}"
                for q, sql in ((f"Show the {idcol.replace('_id', ' id')} and the customer name for every {p}.", f"SELECT {alias}.{idcol}, c.cust_nm {join}"),
                               (f"How many customers have at least one {p}?", f"SELECT COUNT(DISTINCT o.cust_id) {join}")):
                    if ok_rows(sql)[0]:
                        add(bucket, "one_filter_join" if "Show" in q else "distinct_count", q, sql)
                    else:
                        stats["filter query empty"] += 1

    # lookups through an intermediate table
    for hops, bucket, n_ids in ((HOPS, train, 8), (DEV_HOPS, dev, 3)):
        for name, id_q, qfmts, sfmt in hops:
            status, rows = run_sql(conn, id_q)
            ids = [r[0] for r in rows]
            rng.shuffle(ids)
            n = 0
            for x in ids:
                if n >= n_ids:
                    break
                sql = sfmt.format(x=x)
                good, _ = ok_rows(sql)
                if good:
                    add(bucket, "hop_through", qfmts[n % len(qfmts)].format(x=x), sql)
                    n += 1

    # top-1 with LIMIT 1, ties dropped
    for items, bucket in ((TOP1, train), (DEV_TOP1, dev)):
        for q, table, col, direction in items:
            status, rows = run_sql(conn, f"SELECT {col}, COUNT(*) AS n FROM {table} GROUP BY {col} ORDER BY n {direction}")
            if status != "ok" or len(rows) < 2 or rows[0][1] == rows[1][1]:
                stats["top1 dropped: tie or empty"] += 1
                continue
            add(bucket, "top_one", q, f"SELECT {col}, COUNT(*) AS n FROM {table} GROUP BY {col} ORDER BY n {direction} LIMIT 1")

    for q, sql in DISTINCT:
        if ok_rows(sql)[0]:
            add(train, "distinct_count", q, sql)
    for q, sql, cellspec in DEV_DISTINCT:
        if (cellspec is None or cellspec not in held) and ok_rows(sql)[0]:
            add(dev, "distinct_count", q, sql)
    for q, sql in DATES:
        if ok_rows(sql)[0]:
            add(train, "literal_date", q, sql)
    for q, sql in DEV_DATES:
        if ok_rows(sql)[0]:
            add(dev, "literal_date", q, sql)

    kept, seen = [], set()
    for r in train:
        key = norm_question(r["question"])
        why = key in seen and "duplicate question" or leak.why(r["question"], r["sql"])
        if why:
            stats["dropped: " + why] += 1
            continue
        seen.add(key)
        kept.append(r)
    train = kept
    train_q = {norm_question(r["question"]) for r in train}
    old_cont = [json.loads(l) for l in (DATA / "cont_train.jsonl").read_text(encoding="utf-8").splitlines()]
    old_q = {norm_question(r["messages"][1]["content"]) for r in old_cont}
    dev = [r for r in dev if norm_question(r["question"]) not in train_q | old_q and not leak.why(r["question"], r["sql"])]

    out_q = [{"id": f"DC{i:02d}", "category": r["technique"], "difficulty": "easy", "expected": "answer", "order_matters": False, "question": r["question"],
              "gold_sql": r["sql"], "tests": "answer exactly the question: no invented filter or column"} for i, r in enumerate(dev, 1)]
    (ROOT / "data" / "dev_counter.json").write_text(json.dumps({"as_of": "2026-10-31", "note": "Second dev set. One-filter joins, lookups through an intermediate table, top-one, distinct counts and literal dates on values and shapes no training pair uses. Written after the run-5 failure analysis and before the fix was trained and scored.", "questions": out_q}, indent=1, ensure_ascii=False), encoding="utf-8")

    def to_row(r):
        return {**chat_example(tuned_system(r["question"], tables_of(r["sql"])), r["question"], sql_reply(r["sql"])),
                "id": f"Y{abs(hash(r['question'])) % 10**8:08d}", "technique": r["technique"], "kind": "sql"}
    new_rows = [to_row(r) for r in train]
    rng.shuffle(new_rows)
    val_new, train_new = new_rows[:12], new_rows[12:]
    cont2 = old_cont + train_new
    rng.shuffle(cont2)
    old_val = [json.loads(l) for l in (DATA / "cont_val.jsonl").read_text(encoding="utf-8").splitlines()]
    (DATA / "cont2_train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cont2), encoding="utf-8")
    (DATA / "cont2_val.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old_val + val_new), encoding="utf-8")
    print(dict(stats))
    print("new training pairs", len(train_new), "val", len(val_new), "by technique", dict(Counter(r["technique"] for r in train)), "| continuation set", len(cont2))
    print("dev_counter questions", len(out_q), dict(Counter(q["category"] for q in out_q)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
