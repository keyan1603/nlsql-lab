# Agreement between two local models as a routing signal

3B `tuned6gguf` and 7B `xiyan7b-final`; both SQL queries were run on the read-only database and their result sets compared with the grader's comparison (order-insensitive, exact). Hosted reference `gemini-flashlite`. Pool: heldout (52 questions). Single runs, saved answers.

| 7B answer when the two models... | Questions | 7B correct | Share correct |
|---|---|---|---|
| agree | 22 | 20 | 91% |
| disagree | 11 | 6 | 55% |
| (one failed to produce SQL that runs, or one declined) | 19 | 1 | |

| Strategy (all start with the 3B decline gate) | Sent to hosted | Correct | Accuracy (95% interval) | Cost per 1,000 | vs all hosted, sign test p |
|---|---|---|---|---|---|
| 7B with error, empty and invented-value escalation | 5 of 52 (10%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.20 | 1.000 (3 up, 4 down) |
| ... plus escalate when the 3B and 7B disagree | 16 of 52 (31%) | 44 of 52 | 84.6% (72.5% to 92.0%) | $0.56 | 1.000 (2 up, 1 down) |
| ... plus rules 1+ (router first) | 6 of 52 (12%) | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.23 | 1.000 (3 up, 4 down) |
| ... plus rules 1+ and disagreement | 17 of 52 (33%) | 44 of 52 | 84.6% (72.5% to 92.0%) | $0.59 | 1.000 (2 up, 1 down) |

