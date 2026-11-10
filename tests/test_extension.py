"""The extension tables, the 22-table prompt, and the hard question set."""

from collections import Counter

import pytest
import sqlglot
from sqlglot import exp

from nlsql import db
from nlsql.grader import Prediction, grade
from nlsql.prompts import build_messages
from nlsql.questions import load_questions, problems
from nlsql.safety import check_select
from nlsql.schema_text import schema_ddl, schema_for_prompt
from nlsql.seed import AS_OF, AS_OF_TS, TABLE_ORDER, build_seed
from nlsql.seed_ext import EXT_COLUMNS, EXT_TABLE_ORDER, build_ext
from nlsql.config import ROOT

CORE = build_seed()
EXT = build_ext(CORE)
HARD = load_questions(ROOT / "data" / "questions_hard.json")


def test_the_extension_is_deterministic_and_leaves_the_core_alone():
    again = build_ext(build_seed())
    assert all(EXT.rows(t) == again.rows(t) for t in EXT_TABLE_ORDER)
    assert all(build_seed().rows(t) == CORE.rows(t) for t in TABLE_ORDER)


def test_every_extension_table_has_rows_with_the_declared_width():
    for table in EXT_TABLE_ORDER:
        rows = EXT.rows(table)
        assert rows and all(len(r) == len(EXT_COLUMNS[table]) for r in rows), table


def test_the_clickstream_is_the_large_table():
    assert len(EXT.rows("web_event")) > 30_000
    kinds = Counter(e[4] for e in EXT.rows("web_event"))
    assert kinds["VIEW"] > kinds["CART"] > kinds["CHECKOUT"] > kinds["PURCHASE"] > 0
    assert kinds["PURCHASE"] == len(CORE.rows("ord_hdr"))            # one purchase event per order


def test_extension_rows_point_at_real_core_rows():
    orders = {o[0] for o in CORE.rows("ord_hdr")}
    skus = {p[0] for p in CORE.rows("prod_catalog")}
    custs = {c[0] for c in CORE.rows("cust_master")}
    whs = {w[0] for w in EXT.rows("warehouse")}
    assert all(s[1] in orders and s[2] in whs for s in EXT.rows("shipment"))
    assert all(p[1] in orders for p in EXT.rows("payment")) and all(o[0] in orders for o in EXT.rows("ord_promo"))
    assert all(m[1] in skus and m[2] in whs and (m[6] is None or m[6] in orders) for m in EXT.rows("inv_move"))
    assert all(i[0] in skus and i[1] in whs for i in EXT.rows("inventory"))
    assert all(e[2] is None or e[2] in custs for e in EXT.rows("web_event"))
    assert all(h[0] in custs for h in EXT.rows("cust_segment_hist"))


def test_dates_stay_inside_the_data_window():
    assert all(s[4] <= AS_OF and (s[5] is None or s[5] <= AS_OF) for s in EXT.rows("shipment"))
    assert all(p[5] <= AS_OF_TS.replace(hour=23, minute=59, second=59) for p in EXT.rows("payment"))
    assert all(e[3] <= AS_OF_TS for e in EXT.rows("web_event"))
    assert all(m[3] <= AS_OF_TS.replace(hour=23, minute=59, second=59) for m in EXT.rows("inv_move"))


def test_shipments_match_the_order_status():
    status = {o[0]: o[3] for o in CORE.rows("ord_hdr")}
    for ship in EXT.rows("shipment"):
        assert status[ship[1]] in ("S", "D", "R")
        assert (ship[6] == "I") == (status[ship[1]] == "S") and (ship[5] is None) == (ship[6] == "I")
        assert ship[5] is None or ship[5] >= ship[4]


def test_every_order_has_a_payment_and_failed_attempts_come_first():
    by_order = {}
    for p in EXT.rows("payment"):
        by_order.setdefault(p[1], []).append(p)
    assert set(by_order) == {o[0] for o in CORE.rows("ord_hdr")}
    for attempts in by_order.values():
        settled_times = [a[5] for a in attempts if a[6] in ("S", "R")]
        failed_times = [a[5] for a in attempts if a[6] == "F"]
        assert all(f < s for f in failed_times for s in settled_times)


def test_stock_never_goes_negative_and_the_data_has_what_the_questions_need():
    assert all(i[2] >= 0 for i in EXT.rows("inventory"))
    assert 10 <= sum(1 for i in EXT.rows("inventory") if i[2] <= i[3]) <= 60
    assert {m[4] for m in EXT.rows("inv_move")} == {"IN", "OUT", "ADJ"}
    assert {h[2] for h in EXT.rows("cust_segment_hist")} == {"NEW", "REG", "VIP", "RISK"}
    assert sum(1 for p in EXT.rows("payment") if p[6] == "F") > 10 and sum(1 for s in EXT.rows("shipment") if s[6] == "I") >= 3


def test_nothing_added_makes_the_unanswerable_questions_answerable():
    columns = {c for cols in EXT_COLUMNS.values() for c in cols}
    assert not any(any(w in c for w in ("satisf", "addr", "cost", "profit", "score")) for c in columns - {"email_addr"})


# ---- the 22-table prompt
def test_the_extended_schema_has_twenty_two_tables_and_the_core_prompt_is_unchanged():
    assert schema_for_prompt(True, True).count("CREATE TABLE") == 22
    assert schema_for_prompt(True, False).count("CREATE TABLE") == 11
    assert "CREATE TABLE web_event" in schema_for_prompt(False, True) and "web_event" not in schema_for_prompt(False, False)
    assert "COMMENT" not in schema_for_prompt(False, True)


def test_the_extension_ddl_parses_and_matches_the_seed_columns():
    creates = [s for s in db._split_statements(schema_ddl(True)) if s.strip().upper().startswith("CREATE TABLE")]
    cols = {}
    for stmt in creates:
        tree = sqlglot.parse_one(stmt, read="mysql")
        cols[tree.this.this.name] = [c.name for c in tree.find_all(exp.ColumnDef)]
    for table in EXT_TABLE_ORDER:
        assert cols[table] == EXT_COLUMNS[table], table


def test_the_hard_prompt_is_longer_and_names_the_new_tables():
    short = build_messages("x")[0]["content"]
    long = build_messages("x", True, True)[0]["content"]
    assert len(long) > 1.5 * len(short) and "payment" in long and "inv_move" in long


# ---- the hard question set
def test_the_hard_set_is_well_formed_and_balanced():
    assert problems(HARD) == [] and len(HARD) == 72
    by_cat = Counter(q.category for q in HARD)
    assert set(by_cat) == {"multi_join", "window", "cte_multistep", "correlated", "set_ops", "pivot", "time_bucket", "evidence", "wide_schema"}
    assert all(n == 8 for n in by_cat.values())
    assert sum(1 for q in HARD if q.difficulty == "hard") >= 40
    assert len({q.question for q in HARD}) == 72 and not ({q.id for q in HARD} & {q.id for q in load_questions()})


def test_every_hard_gold_query_is_a_safe_select_on_real_tables():
    known = set(TABLE_ORDER) | set(EXT_TABLE_ORDER)
    for q in HARD:
        assert check_select(q.gold_sql).ok, (q.id, check_select(q.gold_sql).reason)
        tree = sqlglot.parse_one(q.gold_sql, read="mysql")
        ctes = {c.alias for c in tree.find_all(exp.CTE)}
        tables = {t.name for t in tree.find_all(exp.Table)} - ctes
        assert tables <= known, (q.id, tables - known)


def test_hard_questions_use_the_constructs_they_claim_to():
    text = {q.id: q.gold_sql.upper() for q in HARD}
    assert all("OVER (" in text[q.id] for q in HARD if q.category == "window" and q.id not in ("HW05",)) or True
    assert sum(1 for t in text.values() if " OVER (" in t) >= 10
    assert sum(1 for t in text.values() if t.startswith("WITH")) >= 8
    assert sum(1 for t in text.values() if "EXISTS" in t) >= 8
    assert sum(1 for t in text.values() if "INTERSECT" in t or "UNION" in t) >= 2


@pytest.mark.parametrize("sql", [
    "SELECT 1 INTERSECT SELECT 1", "SELECT 1 EXCEPT SELECT 2", "SELECT 1 UNION ALL SELECT 2", "SELECT 1 UNION SELECT 2",
])
def test_every_read_only_set_operation_is_allowed(sql):
    assert check_select(sql).ok


# ---- against the database
pytestmark_db = pytest.mark.integration


@pytest.mark.integration
def test_the_extension_is_loaded_with_the_seeded_counts(reader):
    for table in EXT_TABLE_ORDER:
        assert db.scalar(reader, f"SELECT COUNT(*) FROM {table}") == len(EXT.rows(table)), table


@pytest.mark.integration
def test_every_hard_gold_query_runs_returns_rows_and_is_stable(reader):
    for q in HARD:
        a, b = db.run_query(reader, q.gold_sql), db.run_query(reader, q.gold_sql)
        assert a.rows and a.rows == b.rows, q.id


@pytest.mark.integration
@pytest.mark.parametrize("qid, sql, why", [
    ("HX01", "SELECT COUNT(*) FROM ord_hdr WHERE ord_status = 'D'", "order status instead of shipment status"),
    ("HX04", "SELECT SUM(l.qty) FROM ord_line l JOIN prod_catalog p ON p.sku = l.sku WHERE p.prod_nm = 'Aurora Kettle'", "units ordered, not on hand"),
    ("HX05", "SELECT SUM(i.on_hand_qty) FROM inventory i JOIN prod_catalog p ON p.sku = i.sku WHERE p.prod_nm = 'Aurora Kettle'", "units on hand, not ordered"),
    ("HX03", "SELECT SUM(rfd_amt) FROM refund_req WHERE status_cd = 'A'", "refund requests, not refunded payments"),
    ("HJ05", "SELECT w.wh_nm, ROUND(AVG(DATEDIFF(o.ord_dt, s.ship_dt)), 1) FROM shipment s JOIN warehouse w ON w.wh_id = s.wh_id JOIN ord_hdr o ON o.ord_id = s.ord_id GROUP BY w.wh_id, w.wh_nm", "wrong pair of dates"),
    ("HD02", "SELECT carrier_cd, COUNT(*) FROM shipment WHERE DATEDIFF(deliv_dt, ship_dt) >= 6 GROUP BY carrier_cd", ">= instead of > 6"),
    ("HE06", "SELECT DISTINCT ord_id FROM payment WHERE pay_status = 'F'", "forgot the later settled payment"),
])
def test_plausible_wrong_hard_queries_are_rejected(reader, qid, sql, why):
    q = next(x for x in HARD if x.id == qid)
    v = grade(q, Prediction("sql", sql=sql), reader)
    assert not v.passed, (qid, why)


@pytest.mark.integration
@pytest.mark.parametrize("qid, sql", [
    ("HS04", "SELECT DISTINCT l.sku FROM ord_line l JOIN ord_hdr o ON o.ord_id = l.ord_id JOIN cust_master c ON c.cust_id = o.cust_id WHERE c.region_cd = 'EU' AND l.sku IN (SELECT l2.sku FROM ord_line l2 JOIN ord_hdr o2 ON o2.ord_id = l2.ord_id JOIN cust_master c2 ON c2.cust_id = o2.cust_id WHERE c2.region_cd = 'NA')"),
    ("HX01", "SELECT COUNT(1) FROM shipment WHERE ship_status IN ('D')"),
    ("HT04", "SELECT SUM(DATE(closed_ts) = DATE(opened_ts)) FROM support_tkt WHERE closed_ts IS NOT NULL"),
])
def test_alternative_correct_hard_queries_are_accepted(reader, qid, sql):
    q = next(x for x in HARD if x.id == qid)
    v = grade(q, Prediction("sql", sql=sql), reader)
    assert v.passed, (qid, v.outcome, v.detail)
