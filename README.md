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

## Local models

Models are served by LM Studio (free of charge; its terms allow work use as of its July 2025 announcement, which the repo does not re-verify) and called through its local OpenAI-compatible endpoint. `scripts/fetch_model.py` downloads a named GGUF file from Hugging Face, checks its size and SHA-256 against what Hugging Face publishes, and records the licence tag and hash in `docs/models.json`. `scripts/run_eval.py` asks every question, extracts the SQL, grades it on the real database and saves the raw output of every answer to `runs/`. One prompt is used for all models (`nlsql/prompts.py`, greedy decoding), so a difference in score is a difference in model.

### Four models, one prompt, 55 questions (each at Q4_K_M)

| Model | Correct (of 49 answerable) | Declined correctly (of 6) | SQL errors | Mean s per question | Followed the output format |
|---|---|---|---|---|---|
| XiYanSQL-QwenCoder-7B-2504 (SQL specialist, 7B) | **42 (85.7%)** | 1 | 0 | 8.8 | 2 of 55 (bare statement 53) |
| Arctic-Text2SQL-R1-7B (SQL specialist, 7B) | 40 (81.6%) | 0 | 8 | 73.8 | 55 of 55 |
| Qwen3-4B-Instruct-2507 (general model, 4B) | 38 (77.5%) | 3 | 2 | 2.2 | 54 of 55 |
| Qwen-3-4b-Text_to_SQL (SQL fine-tune of that same 4B model) | 34 (69.4%) | 0 | 3 | 5.9 | 0 of 55 |

What the four runs showed (evidence in `docs/results/models/`):

- **Specialist is not automatically better.** The SQL fine-tune of the 4B model scored 8 points below the general model it was tuned from, declined none of the six questions that should be declined, and was 2.7 times slower, because it writes the schema out again before answering. The 7B specialist, XiYan, was the best model.
- **Output format is a property of the model.** The fine-tune ignored the requested code block on all 55 questions (it answers after a `SQL Query:` label, as in its training format), and XiYan returns a bare statement. `nlsql/extract.py` recovers the statement in every case and records how, so the share of answers that needed recovery is reported.
- **Dialect leaks through the prompt.** Arctic wrote SQLite (`strftime`, `julianday`) against a MySQL prompt, and 7 of its 8 errors are those calls, which MySQL reads as unknown stored routines (`execute command denied` for the reader account). Its dates score was 1 of 6. The 4B fine-tune wrote SQL Server (`DATEADD`, `GETDATE`) and used `year_month` as an alias, which MySQL reserves.
- **Declining is the weak point of every model.** Across the four models only 4 of the 24 questions that should be declined were handled correctly; the rest got an invented query (a `shipping_address` made by renaming the email column, a profit formula, "best customers" as Platinum).
- **The comments in the schema are not worth a reliable number here.** Running the general model with the column comments stripped scored 73.5% against 77.5%, but 13 questions changed outcome in both directions (7 got worse, 6 better).
- **The 4B models repeat exactly; the 7B does not quite.** Two runs of the 4B general model at temperature 0 produced byte-identical text for all 55 answers. Two runs of the 7B XiYan file produced different text on 4 of 55 answers with the same pass or fail on all 55.

### Shrinking a model: eleven quantizations of XiYan 7B

Full table and caveats in `docs/results/quant_sweep.md`; driver in `scripts/quant_sweep.py`.

| Level | File | Correct (of 49) | Declined (of 6) | Mean s per question | GPU peak | Process peak |
|---|---|---|---|---|---|---|
| Q2_K | 3.02 GB | 40 | 0 | 4.8 | 2.1 GiB | 3.2 GiB |
| Q3_K_M | 3.81 GB | 42 | 1 | 8.6 | 2.5 GiB | 3.9 GiB |
| Q4_K_M | 4.68 GB | 42 | 1 | 7.8 | 2.9 GiB | 4.8 GiB |
| Q5_K_M | 5.45 GB | 42 | 1 | 8.7 | 3.2 GiB | 5.5 GiB |
| Q6_K | 6.25 GB | 42 | 1 | 10.3 | 3.6 GiB | 6.2 GiB |
| Q8_0 | 8.10 GB | 42 | 1 | 13.0 | 3.8 GiB | 6.6 GiB |

(Five more levels are in the full table.) From Q8_0 down to Q4_K_M the file is 42 percent smaller and every one of the 55 questions has the same pass or fail outcome. Q3_K_M is 53 percent smaller and flips two questions. Q2_K is 63 percent smaller, loses 2 of the 49 answerable questions and flips 3 of 55. Time and memory fall with file size, because more of the model fits on a 4 GB GPU. Differences of a question or two are inside the run-to-run variation of the 7B model, and several timings were taken while large downloads were running; read the table as a trend.

Limits: one machine, one synthetic dataset of a few hundred rows, 55 questions written by one author, one model for the compression sweep. The numbers say how a model does on this schema, not on yours.

### Does the compression show up? Easy questions hide it, hard ones show it

The core questions above are easy enough that every level looked the same. A stress set was added to give a decline somewhere to appear: 11 more tables (22 in all, with confusable names such as `ship_status` beside `ord_status`), a 41,800-row clickstream table and 126 harder questions in nine categories (many-table joins, window functions, multi-step CTEs, correlated subqueries, set operations, pivots, date bucketing, definitions given in the question, and choosing the right table among look-alikes). The patterns follow what Spider 2.0, BEAVER and BIRD single out as hard. Full tables, per-category scores and the chart are in `docs/results/quant_analysis.md` and `quant_curve.png`; the question files are `data/questions_hard.json` (72) and `data/questions_hard2.json` (54).

| Level | File | Core set (49) | Hard set, 126 questions | Hard set, SQL errors | Hard set vs Q8_0 (gains, losses, p) |
|---|---|---|---|---|---|
| Q8_0 | 8.10 GB | 42 (85.7%) | 68 (54.0%) | 21 | reference |
| Q6_K | 6.25 GB | 42 (85.7%) | 68 (54.0%) | 22 | 1, 1, p 1.00 |
| Q5_K_M | 5.45 GB | 42 (85.7%) | 68 (54.0%) | 18 | 4, 4, p 1.00 |
| Q4_K_M | 4.68 GB | 42 (85.7%) | 71 (56.3%) | 17 | 8, 5, p 0.58 |
| Q3_K_M | 3.81 GB | 42 (85.7%) | 69 (54.8%) | 19 | 9, 8, p 1.00 |
| **Q2_K** | 3.02 GB | 40 (81.6%) | **53 (42.1%)** | **31** | **10, 25, p 0.017** |

(The first 72 hard questions were also run on all eleven levels; the extra 54 on the six shown. The first half alone gave the same picture: Q2_K 28 of 72 against 37 for Q8_0, p 0.093, with every other level between 34 and 42.)

- **From 8-bit down to 3-bit the hard set shows no measurable loss.** Q6_K, Q5_K_M, Q4_K_M and Q3_K_M score within 3 questions of Q8_0, and every comparison has p above 0.5. A model file 53 percent smaller (Q3_K_M) answered the hard questions as well as the 8-bit one.
- **At 2-bit the hard questions show a drop the easy ones hid.** On the core set Q2_K lost 2 of 49 (p 0.5, indistinguishable from noise). On the hard set it lost 12 points, 15 questions net (it missed 25 questions that Q8_0 got right and got 10 right that Q8_0 missed, p 0.017), and its invalid SQL rose from 21 to 31 answers. By category the damage is concentrated in correlated subqueries (3 of 14 against 8 of 14), window functions (2 against 5), questions with a definition in the text (2 against 5) and choosing the right table among look-alikes (11 against 14); pivots and joins held.
- **Read the p value with care.** The 0.017 is for one comparison out of five made against Q8_0; corrected for five comparisons it is about 0.085, so the 2-bit drop is suggestive and consistent across both halves of the stress set, not proven. Only the one 7B model was swept for this table. Repeating the Q8_0 and Q2_K runs on the whole hard set gave the same 126 queries again for both files (`xiyan7b-*-rep1` in `docs/results/models/`), so the gap is not run-to-run noise; an earlier repeat on the core set had changed 4 of 55 answer texts, with the same pass or fail outcomes.

### Do smaller models break sooner? The 4B model does

The research the sweep was built on says smaller models are more fragile under compression. To test that, the same 126 hard questions were run on six levels of a 4B general model (Qwen3-4B-Instruct-2507, from the same publisher and recipe family as the 7B ladder; Q5_K_M did not finish downloading and is not included). Full tables are in `docs/results/quant_analysis_qwen4b.md` and `quant_curve_qwen4b.png`.

| Level | File | Hard set, 126 questions | SQL errors | vs Q8_0 (gains, losses, p) |
|---|---|---|---|---|
| Q8_0 | 4.28 GB | 69 (54.8%) | 25 | reference |
| Q6_K | 3.31 GB | 65 (51.6%) | 25 | 5, 9, p 0.42 |
| Q4_K_M | 2.50 GB | 65 (51.6%) | 24 | 10, 14, p 0.54 |
| Q3_K_M | 2.08 GB | 37 (29.4%) | 49 | 6, 38, p < 0.001 |
| Q3_K_S | 1.89 GB | 53 (42.1%) | 35 | 17, 33, p 0.033 |
| **Q2_K** | 1.67 GB | **1 (0.8%)** | 23 | 0, 68, p < 0.001 |

- **The 4B model holds to 4-bit and then breaks one step earlier than the 7B.** The 7B model kept its score at 3-bit and slipped at 2-bit; the 4B model loses about 25 points at Q3_K_M and nearly everything at Q2_K.
- **The 2-bit 4B model mostly stops answering.** On the first 72 questions it replied with the prompt's decline template (`-- UNANSWERABLE`) 56 times, including on questions the 8-bit file answered correctly. The raw outputs were checked; this is what the model wrote, not an extraction problem.
- **The curve is not smooth.** Q3_K_S (42.1%) scored above Q3_K_M (29.4%) although it is smaller. Different quantization recipes damage different layers, so file size alone does not predict accuracy at low bit widths; test the exact file you intend to deploy.
- Same caveats as before: one dataset, one author, 126 questions, and p values not corrected for the five comparisons per model (the two below 0.001 would survive that; 0.033 would not).

### Can the answers be improved without changing the model?

Phase 3 wrapped five techniques around XiYan 7B at Q4_K_M (the file most people would run: 4.7 GB) and measured each on the same 126 stress questions, against the plain prompt. The code is `nlsql/pipeline.py` and `nlsql/schema_link.py`; every technique is a flag of `scripts/run_eval.py`. None of them sees the gold query or the expected answer. Full table: `docs/results/improvements_hardall.md`.

| Configuration | Correct (of 126) | SQL errors | Model calls | Mean s per question | vs plain (gains, losses, p) |
|---|---|---|---|---|---|
| Plain prompt | 71 (56.3%) | 17 | 126 | 17.0 | reference |
| M-Schema layout with example values | 67 | 24 | 126 | 17.7 | 2, 6, p 0.29 |
| 3 worked examples | 64 | 22 | 126 | 15.8 | 8, 15, p 0.21 |
| Show only the 5 likeliest tables | 76 | 12 | 126 | 13.0 | 10, 5, p 0.30 |
| Retry once or twice on a database error | 74 | 7 | 153 | 18.4 | 4, 1, p 0.38 |
| Retry on error or on an empty result | 74 | 7 | 159 | 19.1 | 4, 1, p 0.38 |
| **Stack: 5 tables + retry on error** | **77 (61.1%)** | 8 | 149 | 15.1 | 11, 5, p 0.21 |
| Stack + vote over 5 sampled candidates | 78 (61.9%) | 2 | 737 | 70.4 | 11, 4, p 0.12 |

On the 49 answerable core questions, which were never used to choose techniques: plain 42 (85.7%), stack 43 (87.8%), stack with voting 43.

- **Nothing here is statistically significant.** The best single technique (showing fewer tables) gains 5 questions out of 126, p 0.30. The stack gains 6 with a smaller p of 0.21, and its direction holds on the core set, but it is a small plausible gain, not a proven one. The stack was chosen because pruning and retry both leaned positive and work through independent mechanisms; that choice was made after seeing the stress-set numbers, which is why the core set is the check.
- **Two popular techniques made things worse.** The M-Schema layout and few-shot examples both lowered the score (-4 and -7) and raised SQL errors. A 7B model compressed to 4 bits seems to be distracted by a longer, busier prompt. The examples were written after the evaluation sets and checked mechanically against them (no question or query overlaps), so this is not a leak in either direction.
- **Retry does what it is built to do, but less than it looks.** It cuts invalid queries from 17 to 7, yet only 3 of those became right answers; the others turned into queries that run and return the wrong thing. Retrying on an empty result added nothing.
- **Showing fewer tables is the cheapest gain.** The lexical selector kept every table the gold query needs for 173 of 175 answerable questions (weights fixed in advance, never tuned), shortened the prompt and made answers faster (13 s against 17 s per question).
- **Voting is not worth it here.** Five candidates per question cost 737 model calls instead of 149 and 70 seconds per question instead of 15, for one extra correct answer.
- **Declining did not improve.** Of the 6 core questions that should be declined or clarified, the plain prompt handled 1 and so did the stack; the pool is too small to test a fix, which is a reason to build a dedicated decline set before drawing conclusions.

Two bugs were found on the way. Model output with an unterminated quote crashed the safety check (it now counts as an ordinary syntax failure, with tests), and a stray `-- comment` after the semicolon had earlier been counted as a second statement.

## Does the model know when not to answer?

The core set has only six questions that should be declined, too few to say anything. `data/questions_decline.json` adds 36 on the 22-table schema: 12 that the data cannot answer (DU), 12 too vague to answer without guessing (DM), and 12 answerable look-alike controls (DA) so that declining everything cannot score well. It was written after the improvement round and was not used to choose any technique. XiYanSQL 7B at Q4_K_M, greedy.

| Configuration | Declined correctly (of 24) | Unanswerable (of 12) | Ambiguous (of 12) | Invented an answer | Controls correct (of 12) | Gains / losses vs plain | p |
|---|---|---|---|---|---|---|---|
| Plain prompt | 7 | 5 | 2 | 15 | 12 | ref | ref |
| 5 tables + retry on error | 7 | 4 | 3 | 16 | 11 | 2 / 2 | 1.0 |
| 3 worked examples (including two decline examples) | 18 | 9 | 9 | 4 | 10 | 11 / 0 | 0.001 |

- Left alone, the model answers almost everything: it invented an answer to 15 of 24 questions it should have declined, for example an average salary by "job title" taken from the department column.
- The worked examples are the one technique with a clear effect here: 11 more questions declined correctly and none lost (exact sign test p 0.001). They are also the only technique that contains decline examples, so this is what teaching the format would predict.
- The price: 2 of the 12 controls broke (both became SQL errors), and on the stress set the same examples lowered SQL accuracy. A model that declines more also over-declines or mis-answers some answerable questions; 12 controls is a small sample, so treat 10 against 12 as a warning, not a measurement.
- The stack chosen in the previous round does nothing for declining (2 gained, 2 lost).
- Caveats: one model, one quantization, 24 should-decline questions, and the labels are my judgement of what is answerable. Per-question outputs are in `docs/results/models/imp-*-decline.jsonl`.
