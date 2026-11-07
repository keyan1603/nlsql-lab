"""The seed is deterministic, internally consistent, and contains the facts the questions rely on."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

import pytest

from nlsql.seed import AS_OF, AS_OF_TS, COLUMNS, TABLE_ORDER, build_seed


@pytest.fixture(scope="module")
def seed():
    return build_seed()


def test_the_seed_is_deterministic():
    a, b = build_seed(), build_seed()
    assert all(a.rows(t) == b.rows(t) for t in TABLE_ORDER)


def test_a_different_random_seed_gives_different_data():
    assert build_seed(1).rows("ord_hdr") != build_seed().rows("ord_hdr")


def test_every_table_is_present_with_the_declared_columns(seed):
    assert set(seed.tables) == set(TABLE_ORDER)
    for table in TABLE_ORDER:
        assert seed.rows(table), table
        assert all(len(r) == len(COLUMNS[table]) for r in seed.rows(table)), table


def test_sizes_are_what_the_questions_were_written_against(seed):
    assert len(seed.rows("cust_master")) == 60 and len(seed.rows("ord_hdr")) == 260 and len(seed.rows("support_tkt")) == 140
    assert len(seed.rows("emp")) == 24 and len(seed.rows("prod_catalog")) == 30


def test_references_resolve(seed):
    custs = {r[0] for r in seed.rows("cust_master")}
    skus = {r[0] for r in seed.rows("prod_catalog")}
    orders = {r[0] for r in seed.rows("ord_hdr")}
    emps = {r[0] for r in seed.rows("emp")}
    tickets = {r[0] for r in seed.rows("support_tkt")}
    assert all(o[1] in custs for o in seed.rows("ord_hdr"))
    assert all(l[0] in orders and l[2] in skus for l in seed.rows("ord_line"))
    assert all(r[1] in orders for r in seed.rows("refund_req"))
    assert all(r[6] is None or r[6] in emps for r in seed.rows("refund_req"))
    assert all(t[1] in custs and (t[6] is None or t[6] in emps) for t in seed.rows("support_tkt"))
    assert all(e[1] in tickets for e in seed.rows("tkt_event"))
    assert all(e[3] is None or e[3] in emps for e in seed.rows("emp"))


def test_every_order_total_is_the_sum_of_its_lines(seed):
    totals = {}
    for oid, _line, _sku, qty, unit, disc in seed.rows("ord_line"):
        totals[oid] = totals.get(oid, Decimal("0")) + (qty * unit * (Decimal("1") - disc / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert all(o[4] == totals[o[0]] for o in seed.rows("ord_hdr"))


def test_codes_used_in_the_data_are_all_defined(seed):
    defined = {(t, v) for t, v, _ in seed.rows("code_lookup")}
    checks = [("ORD_STATUS", [o[3] for o in seed.rows("ord_hdr")]), ("TIER", [c[2] for c in seed.rows("cust_master")]),
              ("REGION", [c[3] for c in seed.rows("cust_master")]), ("CHANNEL", [o[6] for o in seed.rows("ord_hdr")]),
              ("REFUND_STATUS", [r[5] for r in seed.rows("refund_req")]), ("REFUND_REASON", [r[4] for r in seed.rows("refund_req")]),
              ("TKT_CATEG", [t[5] for t in seed.rows("support_tkt")]), ("DEPT", [e[2] for e in seed.rows("emp")])]
    for code_type, values in checks:
        assert all((code_type, v) in defined for v in values), code_type


def test_planted_facts_exist(seed):
    cust = {c[0]: c for c in seed.rows("cust_master")}
    assert cust["C-1002"][1] == "Priya Nair" and cust["C-1002"][5] == 1
    order = {o[0]: o for o in seed.rows("ord_hdr")}
    assert order["O-5002"][1] == "C-1002" and order["O-5002"][3] == "D"
    assert sum(1 for l in seed.rows("ord_line") if l[0] == "O-5002") == 3
    assert any(p[1] == "Aurora Kettle" for p in seed.rows("prod_catalog"))
    assert any(r[1] == "O-5002" and r[4] == "DUP" and r[5] == "P" for r in seed.rows("refund_req"))
    assert {e[0] for e in seed.rows("emp")} >= {"E-001", "E-002", "E-007", "E-012"}
    assert any(t[0] == "T-70010" for t in seed.rows("support_tkt"))
    assert any(r[0] == "R-9003" for r in seed.rows("refund_req"))
    assert sum(1 for o in seed.rows("ord_hdr") if o[1] == "C-1005") >= 2


def test_the_data_the_trap_questions_need(seed):
    ordered = {l[2] for l in seed.rows("ord_line")}
    never = [p[1] for p in seed.rows("prod_catalog") if p[0] not in ordered]
    assert sorted(never) == ["Pebble Storage Baskets", "Willow Pen Set"]
    assert len({c[0] for c in seed.rows("cust_master")} - {o[1] for o in seed.rows("ord_hdr")}) == 6
    assert sum(1 for t in seed.rows("support_tkt") if t[6] is None) >= 3
    assert sum(1 for t in seed.rows("support_tkt") if t[3] is None) >= 15
    assert {o[5] for o in seed.rows("ord_hdr")} >= {"USD", "EUR"}
    assert sum(1 for p in seed.rows("prod_catalog") if p[4] == 1) == 5
    assert sum(1 for o in seed.rows("ord_hdr") if o[3] == "C") >= 5            # cancelled orders exist
    assert any(l[5] > 0 for l in seed.rows("ord_line")) and any(l[5] == 0 for l in seed.rows("ord_line"))


def test_refund_rows_are_internally_consistent(seed):
    for rid, _oid, req, amt, _reason, status, approver, decided in seed.rows("refund_req"):
        assert amt > 0
        if status == "P":
            assert approver is None and decided is None, rid
        else:
            assert approver is not None and decided is not None and decided >= req, rid


def test_nothing_is_dated_after_the_as_of_date(seed):
    assert all(o[2] <= AS_OF for o in seed.rows("ord_hdr"))
    assert all(r[2] <= AS_OF and (r[7] is None or r[7] <= AS_OF) for r in seed.rows("refund_req"))
    assert all(t[2] <= AS_OF_TS and (t[3] is None or (t[2] < t[3] <= AS_OF_TS)) for t in seed.rows("support_tkt"))
    assert all(e[2] <= AS_OF_TS for e in seed.rows("tkt_event"))


def test_order_ids_are_chronological(seed):
    dates = [o[2] for o in seed.rows("ord_hdr")]
    assert dates == sorted(dates)


def test_ticket_events_are_in_order_and_close_matches(seed):
    by_ticket = {}
    for _id, tid, ts, kind, _actor in seed.rows("tkt_event"):
        by_ticket.setdefault(tid, []).append((ts, kind))
    closed = {t[0]: t[3] for t in seed.rows("support_tkt")}
    for tid, evs in by_ticket.items():
        assert evs[0][1] == "OPEN"
        assert [e[0] for e in evs] == sorted(e[0] for e in evs)
        assert (evs[-1][1] == "CLOSE") == (closed[tid] is not None)


def test_the_management_tree_has_the_shape_the_hierarchy_questions_expect(seed):
    emps = {e[0]: e[3] for e in seed.rows("emp")}
    assert emps["E-001"] is None and emps["E-012"] == "E-007"
    assert sum(1 for m in emps.values() if m == "E-002") == 3
    assert sum(1 for k in emps if k != "E-001") == 23


def test_policy_rows_do_not_overlap(seed):
    rows = [r for r in seed.rows("policy_rule") if r[1] == "refund_approval_threshold"]
    rows.sort(key=lambda r: r[3])
    assert rows[0][4] + dt.timedelta(days=1) == rows[1][3] and rows[1][4] is None
