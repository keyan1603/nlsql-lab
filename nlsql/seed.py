"""Deterministic synthetic data for the lab database.

Everything is generated from one fixed random seed, so the gold answers are the same on every machine and every run.
Real-looking, entirely fake: names are combined from lists, emails use the reserved example.com domain, national ids and
phone numbers are made up. A few facts are planted on purpose (C-1002, O-5002, E-007 and so on) because the labelled
questions refer to them by id.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

SEED = 20261107
AS_OF = dt.date(2026, 10, 31)
AS_OF_TS = dt.datetime(2026, 10, 31, 18, 0, 0)

TABLE_ORDER = ["code_lookup", "emp", "cust_master", "prod_catalog", "fx_rate", "ord_hdr", "ord_line",
               "refund_req", "support_tkt", "tkt_event", "policy_rule"]

COLUMNS = {
    "code_lookup": ["code_type", "code_val", "code_desc"],
    "emp": ["emp_id", "emp_nm", "dept_cd", "mgr_emp_id", "hire_dt", "salary_amt", "natl_id", "email_addr"],
    "cust_master": ["cust_id", "cust_nm", "tier_cd", "region_cd", "signup_dt", "is_actv", "email_addr", "phone_no"],
    "prod_catalog": ["sku", "prod_nm", "categ_cd", "list_prc", "disc_flag"],
    "fx_rate": ["currency_cd", "eff_dt", "rate_to_usd"],
    "ord_hdr": ["ord_id", "cust_id", "ord_dt", "ord_status", "ord_total_amt", "currency_cd", "channel_cd"],
    "ord_line": ["ord_id", "line_no", "sku", "qty", "unit_prc", "disc_pct"],
    "refund_req": ["rfd_id", "ord_id", "req_dt", "rfd_amt", "reason_cd", "status_cd", "approver_emp_id", "decided_dt"],
    "support_tkt": ["tkt_id", "cust_id", "opened_ts", "closed_ts", "sev_lvl", "categ_cd", "assigned_emp_id", "channel_cd"],
    "tkt_event": ["evt_id", "tkt_id", "evt_ts", "evt_type", "actor_emp_id"],
    "policy_rule": ["rule_id", "rule_key", "rule_val", "eff_from", "eff_to"],
}

CODES = [
    ("ORD_STATUS", "N", "New"), ("ORD_STATUS", "S", "Shipped"), ("ORD_STATUS", "D", "Delivered"),
    ("ORD_STATUS", "C", "Cancelled"), ("ORD_STATUS", "R", "Returned"),
    ("TIER", "P", "Platinum"), ("TIER", "G", "Gold"), ("TIER", "S", "Standard"),
    ("REFUND_STATUS", "P", "Pending"), ("REFUND_STATUS", "A", "Approved"), ("REFUND_STATUS", "D", "Denied"),
    ("REFUND_REASON", "DMG", "Damaged"), ("REFUND_REASON", "DUP", "Duplicate charge"),
    ("REFUND_REASON", "LAT", "Late delivery"), ("REFUND_REASON", "OTH", "Other"),
    ("TKT_CATEG", "BILL", "Billing"), ("TKT_CATEG", "SHIP", "Shipping"), ("TKT_CATEG", "TECH", "Technical"),
    ("TKT_CATEG", "ACCT", "Account"), ("TKT_CATEG", "REFD", "Refunds"),
    ("REGION", "NA", "North America"), ("REGION", "EU", "Europe"), ("REGION", "AP", "Asia Pacific"), ("REGION", "LA", "Latin America"),
    ("CHANNEL", "WEB", "Website"), ("CHANNEL", "APP", "Mobile app"), ("CHANNEL", "PHN", "Phone"), ("CHANNEL", "STR", "In store"),
    ("DEPT", "SUP", "Support"), ("DEPT", "BIL", "Billing operations"), ("DEPT", "FIN", "Finance"),
    ("DEPT", "ENG", "Engineering"), ("DEPT", "MGT", "Management"),
]

# (emp_id, name, dept, manager, hire date, salary)
EMPLOYEES = [
    ("E-001", "Marta Vasquez", "MGT", None, "2018-03-12", 240000), ("E-002", "Devon Okafor", "SUP", "E-001", "2019-06-03", 165000),
    ("E-003", "Ines Larsen", "BIL", "E-001", "2019-09-16", 158000), ("E-004", "Rahul Menon", "FIN", "E-001", "2020-01-20", 162000),
    ("E-005", "Chloe Whitaker", "ENG", "E-001", "2020-04-06", 171000), ("E-006", "Tomas Brandt", "SUP", "E-002", "2020-08-24", 96000),
    ("E-007", "Amara Singh", "SUP", "E-002", "2021-02-15", 94000), ("E-008", "Jonas Keller", "SUP", "E-002", "2021-05-10", 95000),
    ("E-009", "Lucia Ferrer", "SUP", "E-006", "2022-01-17", 61000), ("E-010", "Omar Haddad", "SUP", "E-006", "2022-03-28", 62000),
    ("E-011", "Greta Lindqvist", "SUP", "E-006", "2022-07-11", 60500), ("E-012", "Wei Zhang", "SUP", "E-007", "2022-09-05", 63000),
    ("E-013", "Nadia Petrov", "SUP", "E-007", "2023-01-23", 59000), ("E-014", "Samuel Ortiz", "SUP", "E-007", "2023-04-17", 58500),
    ("E-015", "Hana Kobayashi", "SUP", "E-008", "2023-06-12", 60000), ("E-016", "Idris Bello", "SUP", "E-008", "2023-10-02", 57500),
    ("E-017", "Freya Nilsson", "BIL", "E-003", "2021-11-08", 72000), ("E-018", "Pavel Novak", "BIL", "E-003", "2022-05-30", 70500),
    ("E-019", "Layla Mansour", "FIN", "E-004", "2021-08-23", 88000), ("E-020", "Diego Alvarez", "FIN", "E-004", "2022-10-17", 86000),
    ("E-021", "Sofia Rossi", "ENG", "E-005", "2020-11-02", 128000), ("E-022", "Kenji Watanabe", "ENG", "E-005", "2021-03-22", 131000),
    ("E-023", "Beatrice Owusu", "ENG", "E-005", "2022-02-14", 124000), ("E-024", "Mateo Costa", "ENG", "E-005", "2023-08-07", 118000),
]
SUPPORT_AGENTS = ["E-006", "E-007", "E-008", "E-009", "E-010", "E-011", "E-012", "E-013", "E-014", "E-015", "E-016"]
APPROVERS = ["E-002", "E-003", "E-004", "E-006", "E-007", "E-008"]

FIRST = ["Priya", "Liam", "Sofia", "Noah", "Aisha", "Mateo", "Hannah", "Kenji", "Isabel", "Omar", "Elena", "Jack", "Mei", "Lucas", "Zara",
         "Ethan", "Fatima", "Oscar", "Nina", "Arjun", "Clara", "Rafael", "Yuki", "Hugo", "Leila", "Samir", "Anika", "Felix", "Tara", "Viktor"]
LAST = ["Nair", "Walker", "Moreau", "Chen", "Haddad", "Silva", "Becker", "Tanaka", "Romero", "Khan", "Petrov", "Murphy", "Zhou", "Costa",
        "Ahmed", "Larsen", "Okoye", "Sharma", "Dubois", "Novak", "Reyes", "Hughes", "Ito", "Vargas", "Berg", "Mishra", "Fischer", "Lopez"]

PRODUCTS = [  # (name, category)
    ("Aurora Kettle", "KIT"), ("Borealis Toaster", "KIT"), ("Cascade Blender", "KIT"), ("Delta Knife Set", "KIT"), ("Ember Air Fryer", "KIT"),
    ("Fjord Coffee Grinder", "KIT"), ("Glacier Water Filter", "KIT"), ("Harbor Cutting Board", "KIT"), ("Ivory Dinner Plates", "KIT"),
    ("Juniper Floor Lamp", "HOM"), ("Kestrel Bookshelf", "HOM"), ("Lumen Desk Lamp", "HOM"), ("Maple Throw Blanket", "HOM"),
    ("Nimbus Pillow", "HOM"), ("Onyx Wall Clock", "HOM"), ("Pebble Storage Baskets", "HOM"),
    ("Quartz Notebook", "OFC"), ("Ridge Desk Organizer", "OFC"), ("Summit Standing Desk", "OFC"), ("Tidal Ergonomic Chair", "OFC"),
    ("Umber Whiteboard", "OFC"), ("Vertex Monitor Arm", "OFC"), ("Willow Pen Set", "OFC"),
    ("Xenon Webcam", "ELC"), ("Yonder Bluetooth Speaker", "ELC"), ("Zephyr Wireless Charger", "ELC"), ("Atlas USB Hub", "ELC"),
    ("Beacon Smart Plug", "ELC"), ("Comet Noise-Cancelling Headset", "ELC"), ("Dune Portable Battery", "ELC"),
]
DISCONTINUED = {"Ember Air Fryer", "Nimbus Pillow", "Umber Whiteboard", "Atlas USB Hub", "Dune Portable Battery"}
NEVER_ORDERED = {"Willow Pen Set", "Pebble Storage Baskets"}      # the anti-join question needs products nobody bought


@dataclass
class SeedData:
    tables: dict = field(default_factory=dict)

    def rows(self, table: str) -> list[tuple]:
        return self.tables[table]


def _money(x: float | Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _weighted(rng: random.Random, pairs: list[tuple]) -> str:
    total = sum(w for _, w in pairs)
    pick = rng.uniform(0, total)
    upto = 0.0
    for value, weight in pairs:
        upto += weight
        if pick <= upto:
            return value
    return pairs[-1][0]


def _date_between(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    return start + dt.timedelta(days=rng.randint(0, (end - start).days))


def build_seed(seed: int = SEED) -> SeedData:
    rng = random.Random(seed)
    data = SeedData()

    data.tables["code_lookup"] = [tuple(c) for c in CODES]
    data.tables["emp"] = [(eid, nm, dept, mgr, dt.date.fromisoformat(hire), _money(sal), f"NID-{rng.randint(100000, 999999)}",
                           f"{nm.split()[0].lower()}.{nm.split()[1].lower()}@example.com")
                          for eid, nm, dept, mgr, hire, sal in EMPLOYEES]

    # ---- customers
    names: set = set()
    customers = []
    for i in range(1, 61):
        cid = f"C-{1000 + i}"
        while True:
            nm = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if nm not in names:
                names.add(nm)
                break
        if cid == "C-1002":
            names.discard(nm)
            nm = "Priya Nair"
            names.add(nm)
        tier = "P" if cid == "C-1002" else _weighted(rng, [("P", 10), ("G", 25), ("S", 65)])
        region = "EU" if cid == "C-1002" else _weighted(rng, [("NA", 40), ("EU", 30), ("AP", 20), ("LA", 10)])
        signup = _date_between(rng, dt.date(2022, 1, 1), dt.date(2026, 9, 30))
        active = 1 if (cid == "C-1002" or rng.random() < 0.9) else 0
        email = f"{nm.split()[0].lower()}.{nm.split()[1].lower()}{i}@example.com"
        phone = None if rng.random() < 0.15 else f"+1-555-01{rng.randint(10, 99)}"
        customers.append((cid, nm, tier, region, signup, active, email, phone))
    data.tables["cust_master"] = customers
    home_currency = {}
    for cid, _, _, region, *_ in customers:
        if region == "EU":
            home_currency[cid] = _weighted(rng, [("EUR", 60), ("GBP", 25), ("USD", 15)])
        else:
            home_currency[cid] = "USD"
    home_currency["C-1002"] = "EUR"

    # ---- products and exchange rates
    products = []
    for i, (name, categ) in enumerate(PRODUCTS, start=1):
        products.append((f"{categ}-{i:03d}", name, categ, _money(rng.uniform(8, 450)), 1 if name in DISCONTINUED else 0))
    data.tables["prod_catalog"] = products
    fx = {"USD": [(dt.date(2025, 1, 1), 1.0)],
          "EUR": [(dt.date(2025, 1, 1), 1.05), (dt.date(2025, 7, 1), 1.09), (dt.date(2026, 1, 1), 1.12), (dt.date(2026, 7, 1), 1.10)],
          "GBP": [(dt.date(2025, 1, 1), 1.25), (dt.date(2025, 7, 1), 1.31), (dt.date(2026, 1, 1), 1.27), (dt.date(2026, 7, 1), 1.29)]}
    data.tables["fx_rate"] = [(cur, d, Decimal(str(r))) for cur, series in fx.items() for d, r in series]

    def rate_on(cur: str, day: dt.date) -> float:
        applicable = [r for d, r in fx[cur] if d <= day]
        return applicable[-1]

    # ---- orders and lines
    never_ordered_customers = {f"C-{1000 + i}" for i in (55, 56, 57, 58, 59, 60)}
    buyers = [c[0] for c in customers if c[0] not in never_ordered_customers]
    sellable = [p for p in products if p[1] not in NEVER_ORDERED]
    start = dt.date(2025, 11, 1)
    order_dates = sorted(_date_between(rng, start, AS_OF) for _ in range(260))
    # O-5002 is planted on 2025-11-03; keep order ids chronological by pinning the first two dates and clamping the rest
    order_dates[0], order_dates[1] = dt.date(2025, 11, 1), dt.date(2025, 11, 3)
    order_dates[2:] = [max(d, dt.date(2025, 11, 3)) for d in order_dates[2:]]
    orders, lines = [], []
    for n, day in enumerate(order_dates, start=1):
        oid = f"O-{5000 + n}"
        cid = "C-1002" if oid == "O-5002" else rng.choice(buyers)
        age = (AS_OF - day).days
        if oid == "O-5002":
            status = "D"
        elif age <= 5:
            status = _weighted(rng, [("N", 60), ("S", 40)])
        elif age <= 20:
            status = _weighted(rng, [("S", 30), ("D", 55), ("C", 10), ("R", 5)])
        else:
            status = _weighted(rng, [("D", 82), ("C", 8), ("R", 10)])
        cur = home_currency[cid]
        channel = _weighted(rng, [("WEB", 45), ("APP", 30), ("PHN", 10), ("STR", 15)])
        n_lines = 3 if oid == "O-5002" else int(_weighted(rng, [("1", 40), ("2", 30), ("3", 20), ("4", 10)]))
        chosen = rng.sample([p for p in sellable if (p[4] == 0 or day < dt.date(2026, 6, 1))], n_lines)
        total = Decimal("0.00")
        for line_no, p in enumerate(chosen, start=1):
            qty = rng.randint(1, 5)
            unit = _money(float(p[3]) / rate_on(cur, day))
            disc = Decimal(str(rng.choice([0, 0, 0, 0, 0, 5, 10, 15, 20])))
            lines.append((oid, line_no, p[0], qty, unit, disc))
            total += _money(qty * unit * (Decimal("1") - disc / Decimal("100")))
        orders.append((oid, cid, day, status, total, cur, channel))
    data.tables["ord_hdr"] = orders
    data.tables["ord_line"] = lines

    # ---- refunds
    candidates = [o for o in orders if o[3] in ("D", "R")]
    refunds_raw = []
    for o in rng.sample(candidates, 44):
        req = min(o[2] + dt.timedelta(days=rng.randint(3, 30)), AS_OF)
        refunds_raw.append([o[0], req, o[4], o[5]])
    # plant: the duplicate-charge refund on O-5002, still pending
    o5002 = next(o for o in orders if o[0] == "O-5002")
    refunds_raw = [r for r in refunds_raw if r[0] != "O-5002"] + [["O-5002", dt.date(2025, 11, 6), o5002[4], o5002[5]]]
    refunds_raw.sort(key=lambda r: (r[1], r[0]))
    refunds = []
    for k, (oid, req, total, cur) in enumerate(refunds_raw, start=1):
        rid = f"R-{9000 + k}"
        amount = total if oid == "O-5002" else _money(float(total) * rng.uniform(0.3, 1.0))
        reason = "DUP" if oid == "O-5002" else _weighted(rng, [("DMG", 30), ("DUP", 15), ("LAT", 30), ("OTH", 25)])
        recent = (AS_OF - req).days < 7
        if oid == "O-5002":
            status = "P"
        elif recent:
            status = _weighted(rng, [("P", 60), ("A", 25), ("D", 15)])
        else:
            status = _weighted(rng, [("P", 15), ("A", 55), ("D", 30)])
        if status == "P":
            approver, decided = None, None
        else:
            approver = rng.choice(APPROVERS)
            decided = min(req + dt.timedelta(days=rng.randint(1, 6)), AS_OF)
        refunds.append((rid, oid, req, amount, reason, status, approver, decided))
    data.tables["refund_req"] = refunds

    # ---- tickets and events
    t_start = dt.datetime(2026, 4, 1, 8, 0, 0)
    span = int((AS_OF_TS - t_start).total_seconds())
    opened = sorted(t_start + dt.timedelta(seconds=rng.randint(0, span)) for _ in range(140))
    all_cust = [c[0] for c in customers]
    tickets, events = [], []
    evt_id = 0
    stuck = set(rng.sample(range(0, 90), 6))               # old tickets that were never closed
    for n, ots in enumerate(opened, start=1):
        tid = f"T-{70000 + n}"
        cid = rng.choice(all_cust)
        sev = int(_weighted(rng, [("1", 10), ("2", 25), ("3", 40), ("4", 25)]))
        categ = _weighted(rng, [("BILL", 25), ("SHIP", 25), ("TECH", 25), ("ACCT", 10), ("REFD", 15)])
        channel = _weighted(rng, [("WEB", 40), ("APP", 25), ("PHN", 25), ("STR", 10)])
        age_days = (AS_OF_TS - ots).total_seconds() / 86400
        agent = rng.choice(SUPPORT_AGENTS)
        if n > 135:
            agent = None                                     # the newest tickets have not been picked up yet
        if (n - 1) in stuck:
            closed = None
        elif age_days < 10:
            closed = None if rng.random() < 0.7 else ots + dt.timedelta(hours=rng.uniform(1, 40))
        else:
            hours = rng.uniform(1, 12) if sev == 1 else rng.uniform(2, 96)
            closed = None if rng.random() < 0.06 else ots + dt.timedelta(hours=hours)
        if closed is not None and closed > AS_OF_TS:
            closed = None
        ots_r = ots.replace(microsecond=0)
        closed_r = closed.replace(microsecond=0) if closed else None
        tickets.append((tid, cid, ots_r, closed_r, sev, categ, agent, channel))
        timeline = [(ots_r, "OPEN", None)]
        if agent:
            timeline.append((ots_r + dt.timedelta(minutes=rng.randint(5, 60)), "ASSIGN", agent))
            for _ in range(rng.randint(0, 3)):
                end = closed_r or AS_OF_TS
                when = ots_r + dt.timedelta(seconds=rng.randint(600, max(601, int((end - ots_r).total_seconds()))))
                timeline.append((when.replace(microsecond=0), "REPLY", agent))
            if sev <= 2 and rng.random() < 0.35:
                timeline.append((ots_r + dt.timedelta(hours=rng.randint(1, 6)), "ESCAL", agent))
        if closed_r:
            timeline.append((closed_r, "CLOSE", agent))
        for when, kind, actor in sorted(timeline, key=lambda e: e[0]):
            evt_id += 1
            events.append((evt_id, tid, when, kind, actor))
    data.tables["support_tkt"] = tickets
    data.tables["tkt_event"] = events

    data.tables["policy_rule"] = [
        (1, "refund_approval_threshold", "250.00", dt.date(2025, 1, 1), dt.date(2026, 6, 30)),
        (2, "refund_approval_threshold", "500.00", dt.date(2026, 7, 1), None),
        (3, "sla_hours_sev1", "8", dt.date(2025, 1, 1), dt.date(2026, 3, 31)),
        (4, "sla_hours_sev1", "4", dt.date(2026, 4, 1), None),
    ]
    return data


def insert_all(conn, data: SeedData) -> dict:
    """Insert every table in dependency order and return the row counts."""
    counts = {}
    with conn.cursor() as cur:
        for table in TABLE_ORDER:
            cols = COLUMNS[table]
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
            rows = data.rows(table)
            for i in range(0, len(rows), 500):
                cur.executemany(sql, rows[i:i + 500])
            counts[table] = len(rows)
    return counts
