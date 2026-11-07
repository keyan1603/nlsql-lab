# nlsql-lab

How far can a small model that runs on a laptop get at turning business questions into correct SQL on a real MySQL database, with no frontier model and no per-token cost? This repo is the harness for answering that honestly: a realistic schema, a labelled question set with gold queries, a grader that judges the answer a query returns (not the SQL text), and the safety limits that make generated SQL safe to run.

Everything here is free and open source or free of charge: MySQL Community Server, the Python libraries below, and local models served through LM Studio. There is no paid service.

## What is in it

| Piece | Where | What it does |
|---|---|---|
| The database | `sql/schema.sql`, `nlsql/seed.py` | 11 tables for a support and orders platform, named the way legacy schemas are named: abbreviations, codes instead of words (`ord_status = 'D'`), a lookup table for what the codes mean, soft deletes (`is_actv`), `NULL` meaning "still open", and policy values that change over time. Column comments document the codes. A bare variant with the comments stripped exists on purpose, to measure how much the documentation is worth |
| The data | `nlsql/seed.py` | Deterministic from one fixed seed: 60 customers, 260 orders with 549 lines, 45 refund requests, 140 tickets with 601 events, 24 employees, 30 products. All synthetic (names are combined from lists, emails use `example.com`). A few facts are planted because questions refer to them by id (`C-1002`, `O-5002`, `E-007`) |
| The questions | `data/questions.json` | 55 labelled questions in 11 categories: 49 answerable with a gold query (18 easy, 23 medium, 8 hard), 4 that the schema cannot answer, 2 that are ambiguous. Written for this schema, so there is no benchmark leakage |
| The grader | `nlsql/grader.py` | Runs the gold query and the generated query and compares the result sets. Three match levels: `strict` (same rows and columns), `perm` (same rows, columns reordered, the headline number) and `lenient` (the answer plus extra columns). Unanswerable and ambiguous questions are graded on whether the model said so instead of inventing a query |
| The safety check | `nlsql/safety.py` | A parser-based allow-list: exactly one read-only `SELECT`, no `INTO`, no locking reads, no `SLEEP` or `LOAD_FILE`. Deny by default |
| The database roles | `scripts/make_setup_sql.py`, `nlsql/db.py` | `nlsql_admin` writes to the lab database only and is used by the loader. `nlsql_reader` has `SELECT` and nothing else, at most 4 connections, a read-only session, and a server-side time limit on every query |

### The traps in the question set

Each answerable question is there to test one thing a real schema does to a model: decoding a word into a code (`Platinum` into `P`), `disc_flag` meaning *discontinued* and not *discounted*, `closed_ts IS NULL` meaning open, soft-deleted customers, a join that repeats an order's total once per line, an anti-join (products never ordered), a self-join and a recursive query for the management tree, effective-dated policy rows, date arithmetic from a stated reference date (`2026-10-31`, so answers never change as real time passes), and a deliberate tie at the cut-off of a top-five question that only the question's own tie-break instruction resolves.

## Run it

```bash
python -m venv venv && venv/Scripts/pip install -r requirements.txt
venv/Scripts/python scripts/make_setup_sql.py          # writes .env and setup/setup_mysql.sql (random passwords, never committed)
```

Run `setup/setup_mysql.sql` once as a MySQL administrator. The repo never sees that password. On Windows, the `mysql` client in this MySQL version did not honour `source` passed through `-e`, so feed the file in with a redirect:

```bash
cmd /c '"C:\Program Files\MySQL\MySQL Server 26.10\bin\mysql.exe" -u root -p < C:\path\to\nlsql-lab\setup\setup_mysql.sql'
```

```bash
venv/Scripts/python scripts/load_db.py                 # create the tables, load the seed
venv/Scripts/python scripts/check_gold.py              # run every gold query and check the set is sound
venv/Scripts/python -m pytest -q                       # 100 tests; the 30 that need the database skip themselves without it
```

## What the checks showed

Environment: MySQL Community Server 26.10.0 on Windows, Python 3.13, PyMySQL 1.2.3, sqlglot 30.30.0. Evidence is in `docs/results/`.

- **The set is sound.** All 49 gold queries run, return rows, and return the same rows on a second run. The offline tests also assert every gold query is a safe single `SELECT` that parses as MySQL and touches only real tables.
- **The grader separates right from plausible-wrong.** Eight alternative correct formulations (an `IN` subquery, a `LEFT JOIN` anti-join, a join through the code table, `YEAR()` and `MONTH()` instead of a date range) are accepted. Ten plausible wrong queries, each the exact mistake a trap is built for, are rejected: `= NULL`, the fan-out join, `COUNT(*)` for `COUNT(DISTINCT ...)`, the oldest policy row instead of the one in force, a missing `is_actv` filter, the wrong weekday numbering, the word `Pending` for the code `P`.
- **A tie is deliberate.** Fifth and sixth place in the top-five question have the same count (7 orders), so only following "break ties by customer id" gives the gold answer.
- **The reader cannot write.** `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE` and `TRUNCATE` are all refused by the database. The account holds only `SELECT`, cannot see the `mysql` system schema, and cannot execute stored routines.
- **The server-side time limit works, with a caveat.** A four-way join filtered on an expression is stopped at about 0.4 s with error 3024 for a 300 ms limit. Two things behaved differently from what one might assume. A plain `COUNT(*)` over a four-way cross join returned 90,842,562,801 in under a millisecond, because MySQL's optimizer does not scan it, so it is not a runaway query. And `SELECT SLEEP(3)` under a 300 ms limit returned `1` after 0.31 s without raising an error, because `SLEEP` reports interruption as a result. The safety check refuses `SLEEP` for that reason.

Limits: one machine, one synthetic dataset of a few hundred rows, 55 questions written by one author. The numbers this harness produces will say how a model does on this schema, not on yours.
