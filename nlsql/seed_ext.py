"""The extension data: fulfilment, payments, inventory, promotions, clickstream, segment history, suppliers.

Derived deterministically from the core seed (same orders, customers and products), with its own fixed random seed. The core tables
are never touched, so the 55 core questions keep their answers. The clickstream is the large table (tens of thousands of rows); the
rest are small to medium. No cost, address or satisfaction data is added, so the four unanswerable questions stay unanswerable.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from decimal import Decimal

from nlsql.seed import AS_OF, AS_OF_TS, SeedData, _money, _weighted, build_seed

SEED_EXT = 20261111

EXT_TABLE_ORDER = ["warehouse", "supplier", "promo", "prod_supplier", "inventory", "inv_move", "shipment", "payment", "ord_promo",
                   "cust_segment_hist", "web_event"]

EXT_COLUMNS = {
    "warehouse": ["wh_id", "wh_nm", "region_cd"],
    "supplier": ["sup_id", "sup_nm", "country"],
    "promo": ["promo_id", "promo_cd", "promo_nm", "disc_pct", "starts_dt", "ends_dt"],
    "prod_supplier": ["sku", "sup_id", "lead_days", "is_primary"],
    "inventory": ["sku", "wh_id", "on_hand_qty", "reorder_pt"],
    "inv_move": ["mv_id", "sku", "wh_id", "mv_ts", "mv_type", "qty", "ord_id"],
    "shipment": ["ship_id", "ord_id", "wh_id", "carrier_cd", "ship_dt", "deliv_dt", "ship_status"],
    "payment": ["pay_id", "ord_id", "method_cd", "pay_amt", "currency_cd", "paid_ts", "pay_status"],
    "ord_promo": ["ord_id", "promo_id"],
    "cust_segment_hist": ["cust_id", "month_dt", "segment_cd"],
    "web_event": ["evt_id", "session_id", "cust_id", "evt_ts", "evt_type", "sku", "ord_id", "channel_cd"],
}

WAREHOUSES = [("W1", "Newark Hub", "NA"), ("W2", "Rotterdam Hub", "EU"), ("W3", "Singapore Hub", "AP"), ("W4", "Sao Paulo Hub", "LA")]
REGION_WH = {r: w for w, _, r in WAREHOUSES}
SUPPLIERS = [(1, "Northwind Ceramics", "DE"), (2, "Pacific Metalworks", "CN"), (3, "Andes Textiles", "PE"), (4, "Baltic Timber", "LT"),
             (5, "Orion Electronics", "TW"), (6, "Harbor Plastics", "US"), (7, "Sakura Glassworks", "JP"), (8, "Cedar Paper Mills", "CA")]
PROMOS = [(1, "WELCOME10", "Welcome offer", "10.00", "2025-11-01", "2026-10-31"), (2, "BF25", "Black Friday", "25.00", "2025-11-24", "2025-11-30"),
          (3, "WINTER15", "Winter sale", "15.00", "2025-12-01", "2026-01-15"), (4, "SPRING20", "Spring clearance", "20.00", "2026-03-01", "2026-03-31"),
          (5, "SUMMER10", "Summer offer", "10.00", "2026-06-15", "2026-08-31"), (6, "BACK2SCH", "Back to school", "12.50", "2026-08-15", "2026-09-30"),
          (7, "LOYAL5", "Loyalty reward", "5.00", "2025-11-01", "2026-10-31"), (8, "FLASH30", "Flash sale", "30.00", "2026-02-14", "2026-02-15"),
          (9, "OCT15", "October offer", "15.00", "2026-10-01", "2026-10-31"), (10, "NEWYEAR", "New year offer", "18.00", "2026-01-01", "2026-01-07")]


@dataclass
class ExtData:
    tables: dict = field(default_factory=dict)

    def rows(self, table: str) -> list[tuple]:
        return self.tables[table]


def _ts(day: dt.date, rng: random.Random, lo_h: int = 8, hi_h: int = 21) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(rng.randint(lo_h, hi_h), rng.randint(0, 59), rng.randint(0, 59)))


def build_ext(core: SeedData | None = None, seed: int = SEED_EXT) -> ExtData:
    core = core or build_seed()
    rng = random.Random(seed)
    out = ExtData()
    customers = {c[0]: c for c in core.rows("cust_master")}
    orders = core.rows("ord_hdr")
    lines_by_order: dict = {}
    for l in core.rows("ord_line"):
        lines_by_order.setdefault(l[0], []).append(l)
    refund_status = {}
    for r in core.rows("refund_req"):
        refund_status.setdefault(r[1], []).append(r[5])
    skus = [p[0] for p in core.rows("prod_catalog")]

    out.tables["warehouse"] = list(WAREHOUSES)
    out.tables["supplier"] = list(SUPPLIERS)
    out.tables["promo"] = [(i, cd, nm, Decimal(d), dt.date.fromisoformat(a), dt.date.fromisoformat(b)) for i, cd, nm, d, a, b in PROMOS]

    prod_supplier = []
    for sku in skus:
        chosen = rng.sample([s[0] for s in SUPPLIERS], rng.choice([1, 2, 2, 3]))
        for k, sup in enumerate(chosen):
            prod_supplier.append((sku, sup, rng.randint(5, 45), 1 if k == 0 else 0))
    out.tables["prod_supplier"] = prod_supplier

    # ---- shipments (orders that left the warehouse)
    shipments, ship_wh = [], {}
    n = 0
    for oid, cid, day, status, total, cur, channel in orders:
        if status not in ("S", "D", "R"):
            continue
        n += 1
        region = customers[cid][3]
        wh = REGION_WH[region] if rng.random() < 0.9 else rng.choice(WAREHOUSES)[0]
        ship_dt = min(day + dt.timedelta(days=rng.randint(1, 3)), AS_OF)
        if status == "S":
            deliv, st = None, "I"
        else:
            deliv, st = min(ship_dt + dt.timedelta(days=rng.randint(2, 9)), AS_OF), "D"
        shipments.append((f"S-{8000 + n}", oid, wh, rng.choice(["UPS", "DHL", "FDX", "USP"]), ship_dt, deliv, st))
        ship_wh[oid] = wh
    out.tables["shipment"] = shipments

    # ---- payments (an order can have a failed attempt before the settled one)
    payments = []
    for oid, cid, day, status, total, cur, channel in orders:
        method = _weighted(rng, [("CC", 60), ("PP", 20), ("BT", 10), ("GC", 10)])
        t0 = _ts(day, rng, 6, 22)
        refunded = "A" in refund_status.get(oid, []) or (status == "R" and rng.random() < 0.8)
        attempts = []
        if status == "C":
            attempts.append(("F" if rng.random() < 0.5 else "R", t0))
        else:
            if rng.random() < 0.12:
                attempts.append(("F", t0 - dt.timedelta(minutes=rng.randint(1, 30))))
            attempts.append(("R" if refunded else "S", t0))
        for st, when in attempts:
            payments.append((oid, method, total, cur, when, st))
    payments.sort(key=lambda p: (p[4], p[0]))
    out.tables["payment"] = [(f"P-{3000 + i}", oid, m, amt, cur, when, st) for i, (oid, m, amt, cur, when, st) in enumerate(payments, start=1)]

    # ---- promotions applied
    ord_promo = []
    for oid, cid, day, status, total, cur, channel in orders:
        live = [p for p in PROMOS if dt.date.fromisoformat(p[4]) <= day <= dt.date.fromisoformat(p[5])]
        if live and rng.random() < 0.32:
            first = rng.choice(live)
            ord_promo.append((oid, first[0]))
            if rng.random() < 0.15:
                second = rng.choice(live)
                if second[0] != first[0]:
                    ord_promo.append((oid, second[0]))
    out.tables["ord_promo"] = ord_promo

    # ---- inventory movements and current stock
    moves = []
    for oid, cid, day, status, total, cur, channel in orders:
        if status == "C":
            continue
        wh = ship_wh.get(oid) or REGION_WH[customers[cid][3]]
        for _o, _ln, sku, qty, _unit, _disc in lines_by_order[oid]:
            moves.append((sku, wh, _ts(day + dt.timedelta(days=1), rng, 9, 17), "OUT", -qty, oid))
    months = [dt.date(2025, 10 + i, 1) if 10 + i <= 12 else dt.date(2026, 10 + i - 12, 1) for i in range(13)]
    for sku in skus:
        for wh, _nm, _rg in WAREHOUSES:
            for m in months:
                if rng.random() < 0.5:
                    day = m + dt.timedelta(days=rng.randint(0, 27))
                    if day <= AS_OF:
                        moves.append((sku, wh, _ts(day, rng, 7, 12), "IN", rng.randint(40, 200), None))
    for _ in range(60):
        sku, wh = rng.choice(skus), rng.choice(WAREHOUSES)[0]
        moves.append((sku, wh, _ts(_date(rng), rng, 7, 18), "ADJ", rng.choice([-5, -4, -3, -2, -1, 1, 2, 3]), None))
    moves.sort(key=lambda m: (m[2], m[0], m[1], m[3]))
    out.tables["inv_move"] = [(i, *m) for i, m in enumerate(moves, start=1)]
    inventory = []
    for sku in skus:
        for wh, _nm, _rg in WAREHOUSES:
            running, low = 0, 0
            for m in moves:
                if m[0] == sku and m[1] == wh:
                    running += m[4]
                    low = min(low, running)
            opening = -low + rng.randint(30, 120)
            on_hand = opening + running
            # about one row in five is at or below its reorder point, so 'what needs restocking' has an answer
            reorder = on_hand + rng.randint(0, 40) if rng.random() < 0.2 else max(5, on_hand - rng.randint(5, 80))
            inventory.append((sku, wh, on_hand, reorder))
    out.tables["inventory"] = inventory

    # ---- segment history
    first_orders: dict = {}
    by_cust: dict = {}
    for oid, cid, day, status, total, cur, channel in orders:
        if status != "C":
            by_cust.setdefault(cid, []).append(day)
    hist = []
    for cid, c in customers.items():
        signup = c[4]
        for m in months[1:]:                      # 2025-11 .. 2026-10
            if m + dt.timedelta(days=31) < signup:
                continue
            recent = [d for d in by_cust.get(cid, []) if m - dt.timedelta(days=90) <= d < m + dt.timedelta(days=31)]
            ever_before = any(d < m for d in by_cust.get(cid, []))
            if signup >= m - dt.timedelta(days=31):
                seg = "NEW"
            elif c[2] in ("P", "G") and len(recent) >= 2:
                seg = "VIP"
            elif ever_before and not recent:
                seg = "RISK"
            else:
                seg = "REG"
            hist.append((cid, m, seg))
    out.tables["cust_segment_hist"] = hist

    # ---- clickstream: one session per order, plus many abandoned sessions
    events = []
    sess_n = 0

    def new_session() -> str:
        nonlocal sess_n
        sess_n += 1
        return f"sess{sess_n:06d}"

    for oid, cid, day, status, total, cur, channel in orders:
        sid, ch = new_session(), ("APP" if channel == "APP" else "WEB")
        t = _ts(day, rng, 8, 21)
        wanted = [l[2] for l in lines_by_order[oid]]
        for sku in wanted + rng.sample(skus, rng.randint(0, 3)):
            events.append((sid, cid, t, "VIEW", sku, None, ch))
            t += dt.timedelta(seconds=rng.randint(10, 240))
        for sku in wanted:
            events.append((sid, cid, t, "CART", sku, None, ch))
            t += dt.timedelta(seconds=rng.randint(10, 120))
        events.append((sid, cid, t, "CHECKOUT", None, None, ch))
        t += dt.timedelta(seconds=rng.randint(30, 300))
        events.append((sid, cid, t, "PURCHASE", None, oid, ch))
    all_cust = list(customers)
    span = (AS_OF - dt.date(2025, 11, 1)).days
    for _ in range(7000):
        sid = new_session()
        cid = rng.choice(all_cust) if rng.random() < 0.62 else None
        ch = "APP" if rng.random() < 0.35 else "WEB"
        t = _ts(dt.date(2025, 11, 1) + dt.timedelta(days=rng.randint(0, span)), rng, 7, 23)
        viewed = []
        for _v in range(rng.randint(2, 8)):
            sku = rng.choice(skus)
            viewed.append(sku)
            events.append((sid, cid, t, "VIEW", sku, None, ch))
            t += dt.timedelta(seconds=rng.randint(8, 200))
        if rng.random() < 0.35:
            carted = rng.sample(viewed, min(len(viewed), rng.randint(1, 2)))
            for sku in carted:
                events.append((sid, cid, t, "CART", sku, None, ch))
                t += dt.timedelta(seconds=rng.randint(10, 120))
            if rng.random() < 0.4:
                events.append((sid, cid, t, "CHECKOUT", None, None, ch))
    events = [e for e in events if e[2] <= AS_OF_TS]
    events.sort(key=lambda e: (e[2], e[0], e[3]))
    out.tables["web_event"] = [(i, e[0], e[1], e[2], e[3], e[4], e[5], e[6]) for i, e in enumerate(events, start=1)]
    return out


def _date(rng: random.Random) -> dt.date:
    return dt.date(2025, 11, 1) + dt.timedelta(days=rng.randint(0, (AS_OF - dt.date(2025, 11, 1)).days))


def insert_ext(conn, data: ExtData) -> dict:
    counts = {}
    with conn.cursor() as cur:
        for table in EXT_TABLE_ORDER:
            cols = EXT_COLUMNS[table]
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
            rows = data.rows(table)
            for i in range(0, len(rows), 2000):
                cur.executemany(sql, rows[i:i + 2000])
            counts[table] = len(rows)
    return counts
