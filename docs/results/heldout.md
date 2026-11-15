# Held-out test of the frozen routing design

The routing rules (`nlsql/router.py`) and the invented-value check (`nlsql/invented.py`) were written after the author had seen the test categories, so the published routing numbers are optimistic. This page scores the frozen design on questions that none of the rules were designed against.

## What was frozen

- Last commit that changed `nlsql/router.py` or `nlsql/invented.py`: `8aadc9ed2440fbaf66f64bfb35f539ad02b04bb0` (`git log -1 --format=%H -- nlsql/router.py nlsql/invented.py`).
- Git tag `router-frozen` on HEAD `a00df58a4ed4a3b580163d1c83aaaa3a434c2bc0`, created before any question was written. `nlsql/guard.py` was frozen too. None of the three files was edited.
- The agreement router and the learned router (`scripts/agreement_router.py`, `scripts/learned_router.py`) were committed before scoring, in `3c028fd3cf764997bcaadf677260d0519b876e0e`, and are treated as frozen.

## Method

- `data/questions_heldout.json`: 52 questions on the 22-table schema, same format as `questions_hard.json`. 12 routine, 24 complex (window 4, time bucketing 4, definition in the question 4, multi-step CTE 3, set logic 3, correlated 3, wide schema 3), 6 unanswerable, 6 ambiguous and 4 answerable controls that look like the declines. 40 have a gold query; all 40 run on the real database, return rows, are single safe SELECTs and are stable (`scripts/check_gold.py --set heldout`).
- The questions were written from `sql/schema.sql` and `sql/schema_ext.sql` as a business user would phrase them, with the rule patterns not re-read while writing and no attempt to match or dodge them. Where a question could have two readings the question states the tie-break or the date.
- Leak checks (`scripts/heldout_checks.py`, `docs/results/heldout_checks.json`): `LeakFilter` against core, hard, hard2, decline, dev and dev2 found 0 overlaps. Against the 8,373 training pairs in `train/data/*.jsonl` it first found 12 near-copies (three held-out questions resembled training questions such as "Which customer placed order O-5147?"); those three were reworded and the re-run found 0.
- Shared filter cells: 37 of the 40 gold queries filter on at least one (table, column, value) cell, and 32 of them share at least one cell with some training query (for example `ord_hdr.currency_cd = 'USD'`, `cust_master.is_actv = 1`, `support_tkt.closed_ts IS NOT NULL`). The schema has few distinct codes, so this overlap is hard to avoid; the queries were not dropped. Their cells are listed in the checks file. The training data therefore may have taught the tuned 3B some of the value decoding, which flatters the 3B on the routine questions.
- Runs (single, greedy): hosted `gemini-3.5-flash-lite`, plain prompt, `--max-tokens 4096`, label `gemini-flashlite-heldout`; tuned 3B Q8_0 GGUF in LM Studio, `--prompt tuned --max-tokens 512 --retry 2`, label `tuned6gguf-heldout`; XiYan 7B Q4_K_M, `--prompt tuned --decline-shots 4 --retry 2 --max-tokens 1024`, label `xiyan7b-final-heldout`. Strategies are computed from the saved answers by `scripts/route_eval.py --local-run tuned6gguf`, `scripts/gate_eval.py --gate tuned6gguf --sql xiyan7b-final` and `scripts/heldout_report.py`. The held-out set is a separate pool and is never merged into the 181 (`SETS["heldout"]` exists but the 181 loaders skip it). Regenerating `routing.md` and `gate.md` reproduces every existing number.
- Which 3B: the published pool numbers use `tuned6r2` (the same weights served from Hugging Face). The held-out run used the Q8_0 GGUF (`tuned6gguf`). To keep the server from being mistaken for the questions, the original pool is also recomputed with the GGUF (`routing_tuned6gguf.md`, `gate_tuned6gguf_xiyan7b-final.md`); the two differ by 0 to 5 questions of 181.

## Results

Accuracy with Wilson 95% intervals. Cost per 1,000 questions as in the existing scripts (hosted Standard prices; local electricity from measured latency, which on the 4 GB card makes the 7B slower than in the published pool).

| Strategy | Held-out set (52) | Original 181, published | Original 181, same GGUF | Change vs published (points) | Cost per 1,000, held-out | Cost per 1,000, original |
|---|---|---|---|---|---|---|
| All hosted (gemini-3.5-flash-lite) | 43 of 52 (82.7%; 70.3% to 90.6%) | 160 of 181 (88.4%; 82.9% to 92.3%) | 160 of 181 | -5.7 | $1.49 | $1.36 |
| 3B alone | 32 of 52 (61.5%; 48.0% to 73.5%) | 104 of 181 (57.5%; 50.2% to 64.4%) | 109 of 181 (60.2%) | +4.1 | $0.02 | $0.06 |
| 7B alone | 27 of 52 (51.9%; 38.7% to 64.9%) | 125 of 181 (69.1%; 62.0% to 75.3%) | 125 of 181 | -17.1 | $0.05 | $0.03 |
| 3B decline gate + 7B | 38 of 52 (73.1%; 59.7% to 83.2%) | 127 of 181 (70.2%; 63.1% to 76.4%) | 127 of 181 | +2.9 | $0.05 | $0.09 |
| Gate + 7B, escalate on error, empty or invented value | 42 of 52 (80.8%; 68.1% to 89.2%) | 138 of 181 (76.2%; 69.5% to 81.9%) | 136 of 181 (75.1%) | +4.5 | $0.20 | $0.24 |
| Rules 1+ first, then gate, then 7B with escalation | 42 of 52 (80.8%; 68.1% to 89.2%) | 148 of 181 (81.8%; 75.5% to 86.7%) | 147 of 181 (81.2%) | -1.0 | $0.23 | $0.64 |
| Gate first, then rules 1+, then 7B with escalation | 42 of 52 (80.8%; 68.1% to 89.2%) | 147 of 181 (81.2%; 74.9% to 86.2%) | 146 of 181 (80.7%) | -0.4 | $0.23 | $0.65 |
| 3B-only router: rules 1+, escalate on error, empty, decline or invented value | 38 of 52 (73.1%; 59.7% to 83.2%) | 151 of 181 (83.4%; 77.3% to 88.1%) | 149 of 181 (82.3%) | -10.3 | $0.65 | $0.76 |

Note that the original 181 pool holds 6 should-decline questions (3%) while the held-out set holds 12 of 52 (23%), so the pools are not the same mix. By part of the held-out set (correct of n):

| Strategy | Routine (12) | Complex (24) | Should decline (12) | Answerable controls (4) |
|---|---|---|---|---|
| All hosted | 10 | 19 | 11 | 3 |
| 3B alone | 10 | 7 | 12 | 3 |
| 7B alone | 12 | 12 | 0 | 3 |
| Gate + 7B | 11 | 12 | 12 | 3 |
| Gate + 7B, escalate | 11 | 16 | 12 | 3 |
| Rules 1+ first, gate, 7B, escalate | 11 | 16 | 12 | 3 |
| 3B-only router | 10 | 14 | 11 | 3 |

### Rule recall and precision

| Pool | Threshold | Routed to hosted | Local wrong | Local-wrong caught (recall) | Routed that were local-wrong (precision) |
|---|---|---|---|---|---|
| original 181 (tuned6r2) | 1+ | 57 of 181 | 77 | 35 (45%) | 35 of 57 (61%) |
| original 181 (tuned6r2) | 2+ | 5 of 181 | 77 | 3 (4%) | 3 of 5 (60%) |
| held-out, 3B GGUF | 1+ | 1 of 52 | 20 | 0 (0%) | 0 of 1 |
| held-out, 3B GGUF | 2+ | 0 of 52 | 20 | 0 (0%) | none routed |

## Did the original numbers hold up?

- **The rules did not.** On the original pool the 1+ rules sent 31% of questions to the hosted model and caught 45% of the 3B's failures. On the held-out set they sent one question out of 52 and caught none of the 20 3B failures. The rules key on particular words (running, rank, previous, per month, percentage, both, and so on). Phrased differently, the same kinds of question ("growing total", "month-by-month", "right before it", "as well", "yet did not buy", "than the average product in their own category") did not match. Of the 24 complex questions, one matched (HO20, "higher than the average product in their own category", which the 3B answered correctly, so it was a false alarm). This is the clearest result here, and it is what the caveat in the README predicted.
- **Strategies that depend on the rules shrank.** "Rules 1+ first" and "gate first, then rules" score 80.8%, exactly the score of gate + 7B with escalation and no rules, because the rules are inert. The 3B-only router lost 10.3 points (83.4% to 73.1%) because the rules were carrying it; without them only the runtime signals (SQL error, empty result, decline, invented value) send questions up, and wrong-but-running queries slip through.
- **Strategies that depend on runtime signals held up or grew.** Gate + 7B + escalation went from 76.2% to 80.8% (+4.5 points), the plain gate from 70.2% to 73.1%. I think most of this is composition, not a better design: 12 of the 52 held-out questions should be declined and the 3B gate gets 12 of 12, while the 7B alone gets 0 of 12 (it invented a query for every one), which is the large swing in "7B alone" (-17.1). On the 24 complex questions the escalating setup got 16 (67%) against 19 (79%) for the hosted model, close to the gap seen before. The intervals are wide (about +/-12 points), so none of these shifts is significant on its own.
- **The hosted model fell 5.7 points** (88.4% to 82.7%), inside its interval. Two of its 9 misses are partly artifacts: it wrapped a correct decline for HU03 in a SQL code fence, which the existing extractor scores as an invented answer (counted as wrong here; 44 of 52 if read leniently), and it joined `code_lookup` with the wrong code type for HK02 and RT08. The rest (HO01, HO02, HO08, HO13, HO15, RT12) are real wrong results.
- **The cost story is unchanged in shape.** Gate + 7B + escalation costs $0.20 per 1,000 against $1.49 hosted, at 80.8% against 82.7% (difference not significant here: 3 up, 4 down against all hosted). That is the cheapest setup near the hosted score, and on this set it does not need the rules.
- **Small differences are noise.** n is 52; one question is 1.9 points.

## Agreement router and learned router, held-out

Strategy order as in the scripts: 3B decline gate, router, 7B with error, empty and invented-value escalation. Gate is `tuned6gguf`. Outputs: `heldout_agreement_router.md/json`, `heldout_learned_router.md/json`, run with `--sets heldout` (the committed `agreement_router.md` and `learned_router.md` were not touched).

Agreement signal (does the 7B tend to be right when the 3B and 7B result sets agree?):

| | Original pool (3 sets, 181) | Held-out (52) |
|---|---|---|
| Models agree: 7B correct | 84 of 91 (92%) | 20 of 22 (91%) |
| Models disagree: 7B correct | 30 of 58 (52%) | 6 of 11 (55%) |
| One failed, or one declined | 11 of 32 correct | 1 of 19 correct |

The agreement signal still separates right from wrong: 91% against 55%, the same as the original 92% against 52%. Escalating on disagreement lifted the gate + 7B + escalation setup from 80.8% to 84.6% (44 of 52) by sending 31% of questions (16 of 52) to the hosted model, at $0.56 per 1,000 against $0.20. That is a gain of 2 questions on n = 52; the original pool showed 76.2% to 85.1%. The signal holds; the size of the accuracy gain is not measurable here. Rules 1+ added nothing on top (80.8%), and with disagreement it is the same 44 of 52.

Learned router (TF-IDF plus logistic regression trained on `train/data/candidates.jsonl` only; cross-validation precision 0.70, recall 0.77):

| Router | Sent to hosted | Catches the 7B's wrong answers | Correct | Cost per 1,000 |
|---|---|---|---|---|
| No router | 0 of 52 | 0 of 25 | 42 of 52 (80.8%) | $0.20 |
| Rules 1+ | 1 of 52 (2%) | 0 of 25 | 42 of 52 (80.8%) | $0.23 |
| Classifier, p >= 0.3 | 17 of 52 (33%) | 7 of 25 (28%) | 44 of 52 (84.6%) | $0.60 |
| Classifier, p >= 0.5 | 9 of 52 (17%) | 4 of 25 (16%) | 42 of 52 (80.8%) | $0.37 |
| Classifier, p >= 0.7 | 5 of 52 (10%) | 3 of 25 (12%) | 43 of 52 (82.7%) | $0.32 |
| Random router matched to the rules' 2% | 1 of 52 | 2% expected | 42.0 of 52 | $0.23 |

Is the random reference still as good as the rules? Yes, on this set the rules (0 of 25 wrong answers caught) are no better than a random router sending the same 2% (about 0.5 expected), where on the original pool they beat it (41% recall against 31%). The classifier also sits at about the base rate on this set: at p >= 0.3 it sends 33% and catches 28% of the 7B's wrong answers, where a random 33% would catch about 33%. On the original pool it was above chance (66% caught while sending 52%). Its accuracy gain at p >= 0.3 (+2 questions) is the same size as sending a random third of questions. Note that 12 of the 25 "wrong 7B answers" are should-decline questions the 7B answered, which the gate already handles, so recall over text-only signals is hard to read here.

## Caveats

- Single runs of each model; the hosted model is not bit-repeatable, so a re-run could move its score by a question or two.
- n = 52 (40 answerable). Intervals are 17 to 25 points wide. Nothing here proves a design is better than another; the rules failing to fire is the robust finding.
- I wrote the questions after the rules existed and after reading the README, so my phrasing may still be unconsciously influenced by what I knew about them; the questions were not iterated against model output, and no question was changed after a model had answered it (only before, for leak checks and an empty gold result).
- One author, one schema, synthetic data. The 3B shares filter cells with its training data (see above).
- The 3B on the held-out set is the Q8_0 GGUF, the pool numbers are the Hugging Face server; the recomputed GGUF column shows the effect of that difference is 0 to 5 questions of 181.
- Local seconds on this run came from a 4 GB GPU with the 7B partly offloaded (mean 20 s per question), slower than in the published pool, so local cost figures are not comparable to the published ones to the cent.
- The existing extractor scores a fenced decline as an invented answer; I did not change it, because that would also change earlier results.
