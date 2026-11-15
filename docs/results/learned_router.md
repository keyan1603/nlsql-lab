# Learned router versus deterministic rules

Classifier: TF-IDF (word 1 to 2 grams) plus logistic regression, trained only on the 4010 teacher-written training questions (label: generated for a window, time-bucket, defined-term, multi-step, set-logic or correlated technique, 1311 of them). Training-pool 5-fold cross-validation: precision 0.70, recall 0.77, F1 0.73. No test question, test result or local failure was used to train it or choose its settings. Strategy: router, then 3B decline gate (`tuned6r2`), then 7B (`xiyan7b-final`) with escalation on error, empty or invented value; hosted reference `gemini-flashlite`. Pool: core, hard, hard2 (181 questions). Single runs from saved answers.

| Router | Sent to hosted by router | Catches the 7B's wrong answers (recall) | Of those sent, 7B was wrong (precision) | Correct | Accuracy (95% interval) | Cost per 1,000 | vs all hosted, sign test p |
|---|---|---|---|---|---|---|---|
| No router (gate and 7B only) | 0 of 181 (0%) | 0 of 56 (0%) | 0 of 0 (0%) | 138 of 181 | 76.2% (69.5% to 81.9%) | $0.24 | 0.001 (10 up, 32 down) |
| Deterministic rules, 1+ families | 57 of 181 (31%) | 23 of 56 (41%) | 23 of 57 (40%) | 148 of 181 | 81.8% (75.5% to 86.7%) | $0.64 | 0.012 (4 up, 16 down) |
| Learned classifier, p >= 0.3 | 95 of 181 (52%) | 37 of 56 (66%) | 37 of 95 (39%) | 153 of 181 | 84.5% (78.6% to 89.1%) | $0.87 | 0.118 (4 up, 11 down) |
| Learned classifier, p >= 0.4 | 83 of 181 (46%) | 32 of 56 (57%) | 32 of 83 (39%) | 151 of 181 | 83.4% (77.3% to 88.1%) | $0.81 | 0.049 (4 up, 13 down) |
| Learned classifier, p >= 0.5 | 67 of 181 (37%) | 26 of 56 (46%) | 26 of 67 (39%) | 148 of 181 | 81.8% (75.5% to 86.7%) | $0.68 | 0.017 (5 up, 17 down) |
| Learned classifier, p >= 0.6 | 56 of 181 (31%) | 21 of 56 (38%) | 21 of 56 (38%) | 146 of 181 | 80.7% (74.3% to 85.8%) | $0.63 | 0.007 (5 up, 19 down) |
| Learned classifier, p >= 0.7 | 40 of 181 (22%) | 15 of 56 (27%) | 15 of 40 (38%) | 141 of 181 | 77.9% (71.3% to 83.3%) | $0.51 | 0.001 (5 up, 24 down) |
| Rules OR classifier p >= 0.5 | 85 of 181 (47%) | 34 of 56 (61%) | 34 of 85 (40%) | 150 of 181 | 82.9% (76.7% to 87.7%) | $0.79 | 0.021 (3 up, 13 down) |
| Rules AND classifier p >= 0.5 | 39 of 181 (22%) | 15 of 56 (27%) | 15 of 39 (38%) | 146 of 181 | 80.7% (74.3% to 85.8%) | $0.53 | 0.009 (6 up, 20 down) |
| All hosted | 181 of 181 (100%) | 56 of 56 (100%) | 56 of 181 (31%) | 160 of 181 | 88.4% (82.9% to 92.3%) | $1.36 | 1.000 (0 up, 0 down) |
| Reference: random router sending 31% (expected value) | 57 of 181 | 18 of 56 (31%) | 31% base rate | 144.9 of 181 | 80.1% | $0.59 | |

The classifier threshold was not tuned on any test result: 0.5 is the default and the other rows show the trade-off. Agreement between rules and classifier on the pool: 135 of 181 questions get the same decision.

