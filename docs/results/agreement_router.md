# Agreement between two local models as a routing signal

3B `tuned6r2` and 7B `xiyan7b-final`; both SQL queries were run on the read-only database and their result sets compared with the grader's comparison (order-insensitive, exact). Hosted reference `gemini-flashlite`. Pool: core, hard, hard2 (181 questions). Single runs, saved answers.

| 7B answer when the two models... | Questions | 7B correct | Share correct |
|---|---|---|---|
| agree | 91 | 84 | 92% |
| disagree | 58 | 30 | 52% |
| (one failed to produce SQL that runs, or one declined) | 32 | 11 | |

| Strategy (all start with the 3B decline gate) | Sent to hosted | Correct | Accuracy (95% interval) | Cost per 1,000 | vs all hosted, sign test p |
|---|---|---|---|---|---|
| 7B with error, empty and invented-value escalation | 17 of 181 (9%) | 138 of 181 | 76.2% (69.5% to 81.9%) | $0.24 | 0.001 (10 up, 32 down) |
| ... plus escalate when the 3B and 7B disagree | 70 of 181 (39%) | 154 of 181 | 85.1% (79.2% to 89.5%) | $0.67 | 0.263 (7 up, 13 down) |
| ... plus rules 1+ (router first) | 67 of 181 (37%) | 147 of 181 | 81.2% (74.9% to 86.2%) | $0.65 | 0.007 (4 up, 17 down) |
| ... plus rules 1+ and disagreement | 93 of 181 (51%) | 155 of 181 | 85.6% (79.8% to 90.0%) | $0.84 | 0.267 (4 up, 9 down) |

