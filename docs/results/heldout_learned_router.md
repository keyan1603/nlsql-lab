# Learned router versus deterministic rules

Classifier: TF-IDF (word 1 to 2 grams) plus logistic regression, trained only on the 4010 teacher-written training questions (label: generated for a window, time-bucket, defined-term, multi-step, set-logic or correlated technique, 1311 of them). Training-pool 5-fold cross-validation: precision 0.70, recall 0.77, F1 0.73. No test question, test result or local failure was used to train it or choose its settings. Strategy: router, then 3B decline gate (`tuned6gguf`), then 7B (`xiyan7b-final`) with escalation on error, empty or invented value; hosted reference `gemini-flashlite`. Pool: heldout (52 questions). Single runs from saved answers.

| Router | Sent to hosted by router | Catches the 7B's wrong answers (recall) | Of those sent, 7B was wrong (precision) | Correct | Accuracy (95% interval) | Cost per 1,000 | vs all hosted, sign test p |
|---|---|---|---|---|---|---|---|
| No router (gate and 7B only) | 0 of 52 (0%) | 0 of 25 (0%) | 0 of 0 (0%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.20 | 1.000 (3 up, 4 down) |
| Deterministic rules, 1+ families | 1 of 52 (2%) | 0 of 25 (0%) | 0 of 1 (0%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.23 | 1.000 (3 up, 4 down) |
| Learned classifier, p >= 0.3 | 17 of 52 (33%) | 7 of 25 (28%) | 7 of 17 (41%) | 44 of 52 | 84.6% (72.5% to 92.0%) | $0.60 | 1.000 (2 up, 1 down) |
| Learned classifier, p >= 0.4 | 14 of 52 (27%) | 6 of 25 (24%) | 6 of 14 (43%) | 43 of 52 | 82.7% (70.3% to 90.6%) | $0.52 | 1.000 (2 up, 2 down) |
| Learned classifier, p >= 0.5 | 9 of 52 (17%) | 4 of 25 (16%) | 4 of 9 (44%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.37 | 1.000 (2 up, 3 down) |
| Learned classifier, p >= 0.6 | 6 of 52 (12%) | 3 of 25 (12%) | 3 of 6 (50%) | 43 of 52 | 82.7% (70.3% to 90.6%) | $0.35 | 1.000 (3 up, 3 down) |
| Learned classifier, p >= 0.7 | 5 of 52 (10%) | 3 of 25 (12%) | 3 of 5 (60%) | 43 of 52 | 82.7% (70.3% to 90.6%) | $0.32 | 1.000 (3 up, 3 down) |
| Rules OR classifier p >= 0.5 | 10 of 52 (19%) | 4 of 25 (16%) | 4 of 10 (40%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.40 | 1.000 (2 up, 3 down) |
| Rules AND classifier p >= 0.5 | 0 of 52 (0%) | 0 of 25 (0%) | 0 of 0 (0%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.20 | 1.000 (3 up, 4 down) |
| All hosted | 52 of 52 (100%) | 25 of 25 (100%) | 25 of 52 (48%) | 43 of 52 | 82.7% (70.3% to 90.6%) | $1.49 | 1.000 (0 up, 0 down) |
| Reference: random router sending 2% (expected value) | 1 of 52 | 0 of 25 (2%) | 2% base rate | 42.0 of 52 | 80.8% | $0.23 | |

The classifier threshold was not tuned on any test result: 0.5 is the default and the other rows show the trade-off. Agreement between rules and classifier on the pool: 42 of 52 questions get the same decision.

