"""Terse-question training data: the fix for a model that learned "short question means decline".

    python scripts/make_terse_data.py

The first training set had almost no short answerable questions (2 of 107 questions with eight words or fewer), because the teacher was
told to write fully specified questions, while the vague (CLARIFY) questions were short. The model picked up the shortcut. This script
writes what was missing, with no teacher call, so every label is certain:
  * terse counts by a coded value ("How many cancelled orders?"), the query written from a template and executed on the real database
  * short two-table lookups ("Who placed order O-5002?")
  * short questions that really are vague, and short ones the schema cannot answer, so shortness alone no longer predicts a decline
Then it assembles a continuation set: these new pairs plus a replay of the old training pairs (with the short vague ones capped).

Test hygiene: a (column, value) cell that any test gold query filters on is never used for training, and the dev set (data/dev_terse.json,
which measures generalisation to cells the model has never seen) uses cells the training set does not touch either.
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlglot                                                       # noqa: E402
from sqlglot import exp                                               # noqa: E402

from make_training_data import DATA, ROOT, db, run_sql, tables_of, tests_for_leaks    # noqa: E402
from nlsql.prompts import tuned_system                                # noqa: E402
from nlsql.traindata import LeakFilter, chat_example, norm_question, sql_reply   # noqa: E402

NULL, NOTNULL = "NULL", "NOTNULL"
# (table, column, value, noun phrase). Value NULL / NOTNULL means IS NULL / IS NOT NULL. Numbers are written without quotes.
CELLS = [
    ("ord_hdr", "ord_status", "N", "new orders"), ("ord_hdr", "ord_status", "S", "shipped orders"), ("ord_hdr", "ord_status", "D", "delivered orders"),
    ("ord_hdr", "ord_status", "C", "cancelled orders"), ("ord_hdr", "ord_status", "R", "returned orders"),
    ("ord_hdr", "channel_cd", "WEB", "orders placed on the website"), ("ord_hdr", "channel_cd", "APP", "orders placed in the mobile app"),
    ("ord_hdr", "channel_cd", "PHN", "orders placed by phone"), ("ord_hdr", "channel_cd", "STR", "orders placed in store"),
    ("refund_req", "status_cd", "P", "pending refund requests"), ("refund_req", "status_cd", "A", "approved refund requests"), ("refund_req", "status_cd", "D", "denied refund requests"),
    ("refund_req", "reason_cd", "DMG", "refund requests for damaged goods"), ("refund_req", "reason_cd", "DUP", "refund requests for duplicate charges"),
    ("refund_req", "reason_cd", "LAT", "refund requests for late delivery"), ("refund_req", "reason_cd", "OTH", "refund requests for other reasons"),
    ("refund_req", "decided_dt", NULL, "refund requests nobody has decided yet"),
    ("cust_master", "tier_cd", "P", "platinum customers"), ("cust_master", "tier_cd", "G", "gold customers"), ("cust_master", "tier_cd", "S", "standard-tier customers"),
    ("cust_master", "region_cd", "NA", "customers in North America"), ("cust_master", "region_cd", "EU", "customers in Europe"),
    ("cust_master", "region_cd", "AP", "customers in Asia Pacific"), ("cust_master", "region_cd", "LA", "customers in Latin America"),
    ("cust_master", "is_actv", "1", "active customers"), ("cust_master", "is_actv", "0", "inactive customers"),
    ("prod_catalog", "categ_cd", "KIT", "kitchen products"), ("prod_catalog", "categ_cd", "HOM", "home products"),
    ("prod_catalog", "categ_cd", "OFC", "office products"), ("prod_catalog", "categ_cd", "ELC", "electronics products"),
    ("prod_catalog", "disc_flag", "1", "discontinued products"), ("prod_catalog", "disc_flag", "0", "products that are still sold"),
    ("support_tkt", "categ_cd", "BILL", "billing tickets"), ("support_tkt", "categ_cd", "SHIP", "shipping tickets"), ("support_tkt", "categ_cd", "TECH", "technical tickets"),
    ("support_tkt", "categ_cd", "ACCT", "account tickets"), ("support_tkt", "categ_cd", "REFD", "refund tickets"),
    ("support_tkt", "sev_lvl", "1", "critical tickets"), ("support_tkt", "sev_lvl", "2", "high-severity tickets"), ("support_tkt", "sev_lvl", "3", "medium-severity tickets"),
    ("support_tkt", "sev_lvl", "4", "low-severity tickets"), ("support_tkt", "closed_ts", NULL, "tickets that are still open"),
    ("support_tkt", "closed_ts", NOTNULL, "tickets that have been closed"), ("support_tkt", "assigned_emp_id", NULL, "tickets nobody is assigned to"),
    ("support_tkt", "channel_cd", "WEB", "tickets raised on the website"), ("support_tkt", "channel_cd", "PHN", "tickets raised by phone"),
    ("shipment", "carrier_cd", "UPS", "UPS shipments"), ("shipment", "carrier_cd", "DHL", "DHL shipments"), ("shipment", "carrier_cd", "FDX", "FedEx shipments"),
    ("shipment", "carrier_cd", "USP", "USPS shipments"), ("shipment", "ship_status", "I", "shipments in transit"), ("shipment", "ship_status", "D", "delivered shipments"),
    ("payment", "method_cd", "CC", "card payments"), ("payment", "method_cd", "PP", "PayPal payments"), ("payment", "method_cd", "BT", "bank transfer payments"),
    ("payment", "method_cd", "GC", "gift card payments"), ("payment", "pay_status", "S", "settled payments"), ("payment", "pay_status", "F", "failed payments"),
    ("payment", "pay_status", "R", "refunded payments"),
    ("web_event", "evt_type", "VIEW", "product view events"), ("web_event", "evt_type", "CART", "add-to-cart events"),
    ("web_event", "evt_type", "CHECKOUT", "checkout events"), ("web_event", "evt_type", "PURCHASE", "purchase events"),
    ("warehouse", "region_cd", "NA", "warehouses serving North America"), ("warehouse", "region_cd", "EU", "warehouses serving Europe"),
    ("warehouse", "region_cd", "AP", "warehouses serving Asia Pacific"),
    ("inv_move", "mv_type", "IN", "restock movements"), ("inv_move", "mv_type", "OUT", "outgoing stock movements"), ("inv_move", "mv_type", "ADJ", "stock count corrections"),
    ("tkt_event", "evt_type", "OPEN", "ticket opening events"), ("tkt_event", "evt_type", "ASSIGN", "ticket assignment events"),
    ("tkt_event", "evt_type", "REPLY", "ticket reply events"), ("tkt_event", "evt_type", "ESCAL", "ticket escalation events"), ("tkt_event", "evt_type", "CLOSE", "ticket closing events"),
    ("cust_segment_hist", "segment_cd", "NEW", "new-segment customer records"), ("cust_segment_hist", "segment_cd", "VIP", "VIP-segment customer records"),
    ("cust_segment_hist", "segment_cd", "RISK", "at-risk customer records"),
    ("emp", "dept_cd", "BIL", "employees in billing"), ("emp", "dept_cd", "ENG", "employees in engineering"), ("emp", "dept_cd", "FIN", "employees in finance"),
    ("emp", "dept_cd", "MGT", "employees in management"), ("emp", "dept_cd", "SUP", "employees in support"),
]
# Cells kept for the dev set only: the training set never touches a cell whose (column, value) appears here.
DEV_CELLS = {("payment", "pay_status", "F"), ("shipment", "carrier_cd", "DHL"), ("tkt_event", "evt_type", "ESCAL"), ("emp", "dept_cd", "FIN"),
             ("inv_move", "mv_type", "ADJ"), ("warehouse", "region_cd", "AP"), ("prod_catalog", "categ_cd", "OFC"), ("cust_master", "region_cd", "LA"),
             ("web_event", "evt_type", "PURCHASE"), ("support_tkt", "sev_lvl", "1"), ("ord_hdr", "channel_cd", "STR"), ("refund_req", "reason_cd", "DMG"),
             ("payment", "method_cd", "GC"), ("cust_segment_hist", "segment_cd", "VIP"), ("web_event", "evt_type", "CART"), ("tkt_event", "evt_type", "REPLY"),
             ("payment", "method_cd", "BT")}
PHRASES = ["How many {n}?", "How many {n} are there?", "Count the {n}.", "What is the number of {n}?", "Number of {n}?", "How many {n} do we have?"]
FREEFORM = {("payment", "method_cd", "BT"): "Any idea how many bank transfer payments we have?", ("web_event", "evt_type", "CART"): "Add-to-cart events, how many?",
            ("tkt_event", "evt_type", "REPLY"): "Total ticket replies logged?", ("emp", "dept_cd", "FIN"): "How many people work in finance?",
            ("payment", "pay_status", "F"): "Failed payments: how many?", ("prod_catalog", "categ_cd", "OFC"): "Office product count?"}

# Two-table lookups. (name, split, query for ids, question formats, sql format)
HOPS = [
    ("order_customer", "train", "SELECT ord_id FROM ord_hdr", ["What is the name of the customer behind order {x}?", "Who placed order {x}?", "Which customer placed order {x}?"],
     "SELECT c.cust_nm FROM ord_hdr o JOIN cust_master c ON c.cust_id = o.cust_id WHERE o.ord_id = '{x}'"),
    ("ticket_customer", "train", "SELECT tkt_id FROM support_tkt", ["Who raised ticket {x}?", "Which customer opened ticket {x}?"],
     "SELECT c.cust_nm FROM support_tkt t JOIN cust_master c ON c.cust_id = t.cust_id WHERE t.tkt_id = '{x}'"),
    ("shipment_warehouse", "train", "SELECT ship_id FROM shipment", ["Which warehouse did shipment {x} leave from?", "What is the name of the warehouse that sent shipment {x}?"],
     "SELECT w.wh_nm FROM shipment s JOIN warehouse w ON w.wh_id = s.wh_id WHERE s.ship_id = '{x}'"),
    ("refund_approver", "train", "SELECT rfd_id FROM refund_req WHERE approver_emp_id IS NOT NULL", ["Who approved refund request {x}?", "Which employee decided refund request {x}?"],
     "SELECT e.emp_nm FROM refund_req r JOIN emp e ON e.emp_id = r.approver_emp_id WHERE r.rfd_id = '{x}'"),
    ("employee_manager", "train", "SELECT emp_id FROM emp WHERE mgr_emp_id IS NOT NULL", ["Who is the manager of employee {x}?", "Who does employee {x} report to?"],
     "SELECT m.emp_nm FROM emp e JOIN emp m ON m.emp_id = e.mgr_emp_id WHERE e.emp_id = '{x}'"),
    ("order_carrier", "train", "SELECT ord_id FROM shipment", ["Which carrier shipped order {x}?", "What carrier handled order {x}?"],
     "SELECT carrier_cd FROM shipment WHERE ord_id = '{x}'"),
    ("ticket_assignee", "train", "SELECT tkt_id FROM support_tkt WHERE assigned_emp_id IS NOT NULL", ["Who is working on ticket {x}?", "Which employee is assigned to ticket {x}?"],
     "SELECT e.emp_nm FROM support_tkt t JOIN emp e ON e.emp_id = t.assigned_emp_id WHERE t.tkt_id = '{x}'"),
    ("payment_customer", "dev", "SELECT pay_id FROM payment", ["What is the name of the customer behind payment {x}?", "Who made payment {x}?"],
     "SELECT c.cust_nm FROM payment p JOIN ord_hdr o ON o.ord_id = p.ord_id JOIN cust_master c ON c.cust_id = o.cust_id WHERE p.pay_id = '{x}'"),
    ("product_supplier", "dev", "SELECT sku FROM prod_supplier WHERE is_primary = 1", ["Which supplier is the main one for product {x}?"],
     "SELECT s.sup_nm FROM prod_supplier ps JOIN supplier s ON s.sup_id = ps.sup_id WHERE ps.sku = '{x}' AND ps.is_primary = 1"),
    ("order_promotion", "dev", "SELECT ord_id FROM ord_promo", ["Which promotion was used on order {x}?"],
     "SELECT p.promo_nm FROM ord_promo op JOIN promo p ON p.promo_id = op.promo_id WHERE op.ord_id = '{x}'"),
]

VAGUE = [  # short questions that cannot be answered without guessing the measure, the period or the group
    ("Show me the sales.", "Which measure do you mean (order count, order value, units sold), and for which period?"),
    ("How are customers doing?", "What do you want to know about customers: how many, how much they spent, or how many are active?"),
    ("Top customers?", "Top by what measure (total spend, number of orders) and for which period?"),
    ("What about returns?", "Do you want the number of returned orders, their value, or the return rate, and for which period?"),
    ("Show revenue.", "Revenue for which period, and in which currency (the order currency or USD)?"),
    ("Give me the numbers.", "Which numbers do you need: orders, revenue, tickets or stock, and for which period?"),
    ("Biggest orders?", "Biggest by order total or by number of units, and how many orders do you want?"),
    ("How is support performing?", "Which measure of support performance: tickets opened, time to close, or open backlog, and for which period?"),
    ("Best products?", "Best by units sold, revenue or number of orders, and for which period?"),
    ("Show me trends.", "Trends in which measure (orders, revenue, tickets), by which period (month, quarter), and over what date range?"),
    ("Average value?", "The average of what: order total, line price or payment amount, and over which period?"),
    ("Recent orders?", "How recent do you mean (a date range or a number of orders), and which columns do you want to see?"),
    ("Which region is best?", "Best by which measure (order count, revenue, customer count) and for which period?"),
    ("Compare channels.", "Compare the sales channels on which measure (orders, revenue) and for which period?"),
    ("Who are our best employees?", "Best by which measure, for example refunds approved or tickets handled, and for which period?"),
    ("Is stock healthy?", "What counts as healthy: units on hand below the reorder point, or days of stock left, and for which warehouses?"),
    ("Worst products?", "Worst by which measure (units sold, revenue, returns) and for which period?"),
    ("Tell me about growth.", "Growth in which measure (orders, revenue, customers), between which two periods?"),
    ("What is our best month?", "Best by which measure (orders, revenue, new customers) and in which year?"),
    ("Show the leaders.", "Leaders among customers, products, regions or carriers, and by which measure?"),
    ("Which carrier is better?", "Better by which measure: delivery time, number of shipments or delivered share, and for which period?"),
    ("Customer value?", "What measure of customer value do you mean (total spend, order count, tier) and for which customers?"),
    ("How is delivery going?", "Which delivery measure: shipments in transit, average days to deliver or delivered share, and for which period?"),
    ("Most important tickets?", "Important by severity, by age, or by customer tier, and how many tickets do you want?"),
    ("Show me the totals.", "Totals of what (orders, revenue, payments, units) and for which period?"),
    ("Who buys the most?", "Most by number of orders, total spend or units, and for which period?"),
    ("What sells well?", "Well by units sold or revenue, over which period, and how many products do you want?"),
    ("Slow movers?", "Slow by which measure (units sold, days since the last sale) and for which period?"),
    ("Which warehouse matters most?", "Matters by which measure: stock held, shipments sent or orders served, and for which period?"),
    ("Top regions?", "Top regions by which measure (customers, orders, revenue) and for which period?"),
    ("Show activity.", "Activity of what: orders, web events or tickets, and for which period?"),
    ("Any problems?", "Which problems do you mean: failed payments, open critical tickets, late shipments or low stock?"),
    ("How big are orders?", "Big in order total or in number of lines, as an average, a maximum or a distribution, and for which period?"),
    ("Which promotions work?", "Work by which measure (orders that used it, discount given, revenue), and for which period?"),
    ("What is typical?", "Typical what: order total, ticket age or delivery time, and as a mean or a median?"),
    ("Find the outliers.", "Outliers in which measure (order total, payment amount, ticket age) and by what rule?"),
    ("Summarise the quarter.", "Which quarter, and which figures do you want in the summary (orders, revenue, tickets)?"),
    ("Busiest day?", "Busiest by orders, web events or tickets, and over which period?"),
    ("Who is behind?", "Behind on what: open tickets, late shipments or pending refunds, and by how many days?"),
    ("Performance by region?", "Which performance measure (orders, revenue, delivery time) and for which period?"),
]
ABSENT = [  # short questions the schema cannot answer
    ("What is the weather in Paris?", "The database holds no weather data."),
    ("Show employee birthdays.", "Employees have a hire date but no birth date."),
    ("What is our stock price?", "The database has no share price or market data."),
    ("List customer shoe sizes.", "The database has no clothing or shoe size data."),
    ("Show competitor prices.", "The database has only our own prices, no competitor data."),
    ("How many employees work remotely?", "Employees have no work location or remote flag."),
    ("What colour is each product?", "The product catalog has no colour attribute."),
    ("What are the warehouse temperatures?", "The database has no sensor or temperature data."),
    ("Show customer ages.", "Customers have a signup date but no birth date or age."),
    ("What is the weight of each parcel?", "Shipments have no weight or dimension data."),
    ("Which customers follow us on social media?", "The database has no social media data."),
    ("What did marketing spend last year?", "Promotions record discounts only, not marketing spend."),
    ("Show customer satisfaction scores.", "The database has no survey or satisfaction scores."),
    ("What is our profit margin?", "The database has prices but no product cost, so margin cannot be computed."),
    ("Rate our suppliers.", "Suppliers have a name, country and lead times but no rating."),
    ("List employee phone extensions.", "Employees have an email address but no phone extension."),
    ("Which products are on back order?", "The database has no back order data, only stock on hand."),
    ("Show delivery addresses.", "The database stores no street addresses for orders or shipments."),
    ("Which orders were gift wrapped?", "Orders have no gift wrap flag."),
    ("What are the customers' favourite brands?", "Products have no brand attribute and no preference data exists."),
]
DEV_VAGUE = [("Show me the performance.", "Performance of what, by which measure, and for which period?"), ("Which customers matter most?", "Matter by which measure, spend or order count, and for which period?"),
             ("Give me the highlights.", "Highlights of which area (sales, support, logistics) and for which period?"), ("What changed recently?", "Changed in which measure, and compared with which earlier period?"),
             ("Compare the regions.", "Compare regions on which measure and for which period?"), ("How is fulfilment?", "Which fulfilment measure: shipments in transit, days to deliver or delivered share?")]
DEV_ABSENT = [("What is the average customer rating?", "The database has no ratings."), ("Show product weights.", "Products have no weight data."),
              ("How many employees are over 50?", "Employees have no birth date or age."), ("Which suppliers are certified?", "Suppliers have no certification data."),
              ("List customer birthdays.", "Customers have no birth date."), ("What is the carbon footprint per order?", "The database has no emissions data.")]
NOISY = ("How many stock movements happened last month", "refund requests waiting for manager approval above the threshold", "lowest average transit delay", "VIP customers not logged in")


def cond(col, val):
    return f"{col} IS NULL" if val == NULL else f"{col} IS NOT NULL" if val == NOTNULL else f"{col} = {val}" if val.isdigit() else f"{col} = '{val}'"


def sqlfor(table, *conds):
    return f"SELECT COUNT(*) FROM {table}" + (" WHERE " + " AND ".join(conds) if conds else "")


WHOLE = [("cust_master", "customers"), ("emp", "employees"), ("prod_catalog", "products"), ("ord_hdr", "orders"), ("support_tkt", "support tickets"),
         ("shipment", "shipments"), ("payment", "payment attempts"), ("promo", "promotions"), ("supplier", "suppliers"), ("warehouse", "warehouses"),
         ("refund_req", "refund requests"), ("web_event", "web events")]
WHOLE_PHRASES = ["How many {n} are there?", "How many {n} do we have?", "Count all {n}.", "Total number of {n}?"]
COMBOS = [("ord_hdr", ("ord_status", "S"), ("channel_cd", "PHN"), "How many shipped orders were placed by phone?"),
          ("ord_hdr", ("ord_status", "N"), ("channel_cd", "WEB"), "How many new orders came from the website?"),
          ("ord_hdr", ("ord_status", "R"), ("channel_cd", "PHN"), "How many returned orders were placed by phone?"),
          ("ord_hdr", ("ord_status", "S"), ("channel_cd", "APP"), "How many shipped orders came from the app?"),
          ("ord_hdr", ("ord_status", "R"), ("channel_cd", "WEB"), "How many returned orders came from the website?"),
          ("support_tkt", ("categ_cd", "BILL"), ("closed_ts", NULL), "How many billing tickets are still open?"),
          ("support_tkt", ("categ_cd", "TECH"), ("closed_ts", NULL), "How many technical tickets are still open?"),
          ("support_tkt", ("categ_cd", "SHIP"), ("closed_ts", NOTNULL), "How many shipping tickets are closed?"),
          ("support_tkt", ("categ_cd", "ACCT"), ("sev_lvl", "2"), "How many high-severity account tickets are there?"),
          ("support_tkt", ("categ_cd", "REFD"), ("closed_ts", NULL), "How many refund tickets are still open?"),
          ("cust_master", ("tier_cd", "G"), ("region_cd", "EU"), "How many gold customers are in Europe?"),
          ("cust_master", ("tier_cd", "S"), ("region_cd", "NA"), "How many standard customers are in North America?"),
          ("cust_master", ("tier_cd", "G"), ("is_actv", "1"), "How many gold customers are active?"),
          ("cust_master", ("region_cd", "AP"), ("is_actv", "1"), "How many active customers are in Asia Pacific?"),
          ("refund_req", ("status_cd", "A"), ("reason_cd", "LAT"), "How many late-delivery refunds were approved?"),
          ("refund_req", ("status_cd", "D"), ("reason_cd", "DUP"), "How many duplicate-charge refunds were denied?"),
          ("shipment", ("carrier_cd", "UPS"), ("ship_status", "I"), "How many UPS shipments are in transit?"),
          ("shipment", ("carrier_cd", "FDX"), ("ship_status", "D"), "How many FedEx shipments were delivered?"),
          ("payment", ("method_cd", "CC"), ("pay_status", "F"), "How many card payments failed?"),
          ("payment", ("method_cd", "PP"), ("pay_status", "S"), "How many PayPal payments settled?")]


def test_cells() -> set:
    """(table, column, value) cells that any test gold query filters on, so training never uses them. Aliases are resolved to tables;
    an unqualified column counts for every table in the query that has a column of that name."""
    from nlsql.schema_link import parse_schema
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    cells = set()
    for q in tests_for_leaks():
        if not q.get("gold_sql"):
            continue
        try:
            tree = sqlglot.parse_one(q["gold_sql"], read="mysql")
        except Exception:
            continue
        alias = {(t.alias or t.name): t.name for t in tree.find_all(exp.Table)}
        names = set(alias.values())

        def tables_for(c):
            if c.table and c.table in alias:
                return {alias[c.table]}
            return {t for t in names if c.name in cols.get(t, ())}

        def put(c, v):
            cells.update((t, c.name, v) for t in tables_for(c))
        for n in tree.find_all(exp.EQ):
            a, b = n.this, n.expression
            if isinstance(b, exp.Column):
                a, b = b, a
            if isinstance(a, exp.Column) and isinstance(b, exp.Literal):
                put(a, str(b.this))
        for n in tree.find_all(exp.In):
            if isinstance(n.this, exp.Column):
                for e in n.expressions:
                    if isinstance(e, exp.Literal):
                        put(n.this, str(e.this))
        for n in tree.find_all(exp.Is):
            if isinstance(n.this, exp.Column) and isinstance(n.expression, exp.Null):
                put(n.this, NOTNULL if isinstance(n.parent, exp.Not) else NULL)
    return cells


def main() -> int:
    rng = random.Random(23)
    conn = db.connect("reader")
    held = test_cells()
    dev_t = set(DEV_CELLS)
    leak = LeakFilter(tests_for_leaks(), 0.6)
    stats: Counter = Counter()
    train, dev = [], []

    def add(bucket, **kw):
        kw.setdefault("cluster", "terse")
        kw.setdefault("difficulty", "easy")
        bucket.append(kw)

    for table, col, val, noun in CELLS:
        cell = (table, col, val)
        sql = sqlfor(table, cond(col, val))
        status, rows = run_sql(conn, sql)
        if status != "ok" or not rows[0][0]:
            stats["cell: empty or failed"] += 1
            continue
        is_dev = cell in dev_t
        if cell in held:
            stats["dev cell dropped: test cell" if is_dev else "cell held out (a test query filters on it)"] += 1
            continue
        qs = [FREEFORM[cell]] if is_dev and cell in FREEFORM else []
        qs += [p.format(n=noun) for p in rng.sample(PHRASES, 2 if is_dev else 4)]
        for q in qs:
            if len(q.split()) <= 10:
                add(dev if is_dev else train, question=q, technique="terse_count", kind="sql", sql=sql)
    for table, noun in WHOLE:
        sql = sqlfor(table)
        for p in rng.sample(WHOLE_PHRASES, 3):
            add(train, question=p.format(n=noun), technique="terse_count", kind="sql", sql=sql)
    for table, (ca, va), (cb, vb), q in COMBOS:
        parts = {(table, ca, va), (table, cb, vb)}
        if parts & held or parts & dev_t:
            stats["combo held out"] += 1
            continue
        sql = sqlfor(table, cond(ca, va), cond(cb, vb))
        status, rows = run_sql(conn, sql)
        if status == "ok" and rows[0][0]:
            add(train, question=q, technique="terse_count", kind="sql", sql=sql)
    for name, split, id_q, qfmts, sfmt in HOPS:
        status, rows = run_sql(conn, id_q)
        ids = [r[0] for r in rows]
        rng.shuffle(ids)
        n_ok = 0
        for x in ids:
            if n_ok >= (9 if split == "train" else 2):
                break
            sql = sfmt.format(x=x)
            status, res = run_sql(conn, sql)
            if status != "ok":
                continue
            add(dev if split == "dev" else train, question=qfmts[n_ok % len(qfmts)].format(x=x), technique="hop_lookup", kind="sql", sql=sql)
            n_ok += 1
    for q, why in VAGUE:
        add(train, question=q, technique="short_clarify", kind="clarify", reply=f"-- CLARIFY: {why}")
    for q, why in ABSENT:
        add(train, question=q, technique="short_unanswerable", kind="unanswerable", reply=f"-- UNANSWERABLE: {why}")
    for q, why in DEV_VAGUE:
        add(dev, question=q, technique="short_clarify", kind="clarify", reply=f"-- CLARIFY: {why}")
    for q, why in DEV_ABSENT:
        add(dev, question=q, technique="short_unanswerable", kind="unanswerable", reply=f"-- UNANSWERABLE: {why}")

    kept, seen = [], set()
    for r in train:
        key = norm_question(r["question"])
        why = key in seen and "duplicate question" or leak.why(r["question"], r.get("sql"))
        if why:
            stats["dropped: " + why] += 1
            continue
        seen.add(key)
        kept.append(r)
    train = kept
    # the dev set must not overlap training or the test questions either
    train_q = {norm_question(r["question"]) for r in train}
    dev = [r for r in dev if norm_question(r["question"]) not in train_q and not leak.why(r["question"], r.get("sql"))]

    # data/dev_terse.json in the same format as the other question sets
    out_q = []
    for i, r in enumerate(dev, 1):
        exp_kind = {"sql": "answer", "clarify": "clarify", "unanswerable": "unanswerable"}[r["kind"]]
        out_q.append({"id": f"DT{i:02d}", "category": r["technique"], "difficulty": "easy", "expected": exp_kind, "order_matters": False, "question": r["question"],
                      **({"gold_sql": r["sql"]} if r["kind"] == "sql" else {}), "tests": "terse question on a cell, shape or topic the training set never used"})
    (ROOT / "data" / "dev_terse.json").write_text(json.dumps({"as_of": "2026-10-31", "note": "Dev set for the terse-question fix. Short answerable questions on (column, value) cells that no training pair and no test gold query uses, three two-table lookup shapes not trained on, and short vague and unanswerable questions. Written before the fix was trained and scored.", "questions": out_q}, indent=1, ensure_ascii=False), encoding="utf-8")

    # the continuation set: the new pairs plus a replay of the old ones (short vague ones capped, four noisy declines removed)
    old = [json.loads(l) for l in (DATA / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    replay, short_clar = [], []
    for r in old:
        q, a = r["messages"][1]["content"], r["messages"][2]["content"]
        if any(s in q for s in NOISY) and not a.startswith("```sql"):
            stats["replay: noisy decline removed"] += 1
            continue
        if a.startswith("-- CLARIFY") and len(q.split()) <= 8:
            short_clar.append(r)
        else:
            replay.append(r)
    rng.shuffle(short_clar)
    stats["replay: short CLARIFY dropped by the cap of 40"] = max(len(short_clar) - 40, 0)
    rng.shuffle(replay)
    replay = replay[:400] + short_clar[:40]

    def to_row(r):
        reply = sql_reply(r["sql"]) if r["kind"] == "sql" else r["reply"]
        return {**chat_example(tuned_system(r["question"], tables_of(r.get("sql"))), r["question"], reply), "id": f"X{abs(hash(r['question'])) % 10**8:08d}", "technique": r["technique"], "kind": r["kind"]}
    new_rows = [to_row(r) for r in train]
    rng.shuffle(new_rows)
    val_new, train_new = new_rows[:30], new_rows[30:]
    cont = train_new + replay
    rng.shuffle(cont)
    old_val = [json.loads(l) for l in (DATA / "val.jsonl").read_text(encoding="utf-8").splitlines()]
    (DATA / "cont_train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cont), encoding="utf-8")
    (DATA / "cont_val.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val_new + old_val), encoding="utf-8")

    short = Counter()
    for r in cont:
        q, a = r["messages"][1]["content"], r["messages"][2]["content"]
        if len(q.split()) <= 10:
            short["sql" if a.startswith("```sql") else "clarify" if a.startswith("-- CLARIFY") else "unanswerable"] += 1
    print(dict(stats))
    print("new training pairs", len(train_new), "by technique", dict(Counter(r["technique"] for r in train)), "| replay", len(replay), "| continuation train", len(cont),
          "val", len(val_new) + len(old_val))
    print("questions of 10 words or fewer in the continuation set:", dict(short))
    print("dev questions", len(out_q), dict(Counter(q["category"] for q in out_q)), "held-out test cells", len(held))
    return 0


if __name__ == "__main__":
    sys.exit(main())
