# Does the model's own token probability say which answers to escalate?

Model run `xiyan7bft-e2`, one attempt per question, no repair. Pre-registered plan in the script header: the threshold is fixed on the pool (core, hard, hard2) and applied unchanged to the held-out set.

## Pool: 181 questions (174 answerable with SQL)

| Signal | AUC for 'this answer is wrong' |
|---|---|
| mean | 0.828 |
| min | 0.734 |
| p10 | 0.769 |
| below1 | 0.695 |

Local first attempt correct: 124 of 181. Wrong answers the ordinary checks catch: 20 of 55.

## Held-out: 52 questions (40 answerable with SQL)

| Signal | AUC for 'this answer is wrong' |
|---|---|
| mean | 0.843 |
| min | 0.864 |
| p10 | 0.651 |
| below1 | 0.753 |

Local first attempt correct: 36 of 52. Wrong answers the ordinary checks catch: 6 of 15.

## Escalating on the checks plus low confidence

Thresholds on the mean log-probability are picked on the pool so that the total share sent to the hosted model hits the target, then applied unchanged to the held-out set. 'Random' is the expected score of sending the same share at random (after the checks).

| Target share | Threshold | Pool correct | Pool share | Pool random | Held-out correct | Held-out share | Held-out random |
|---|---|---|---|---|---|---|---|
| checks only | none | 143 of 181 (79.0%) | 13.3% | n/a | 41 of 52 | 13.5% | n/a |
| 20% | -0.108 | 149 of 181 (82.3%) | 19.9% | 79.7% | 43 of 52 (82.7%) | 17.3% | 79.0% |
| 30% | -0.080 | 156 of 181 (86.2%) | 29.8% | 80.8% | 46 of 52 (88.5%) | 26.9% | 79.4% |
| 40% | -0.062 | 160 of 181 (88.4%) | 40.3% | 81.9% | 45 of 52 (86.5%) | 40.4% | 80.0% |
| 50% | -0.056 | 162 of 181 (89.5%) | 50.3% | 83.0% | 45 of 52 (86.5%) | 42.3% | 80.1% |

For reference, the saved-answer simulation of escalating when the 3B and 7B disagree scored 154 of 181 (85.1%) with 70 of 181 (38.7%) sent up on the pool, and 44 of 52 (84.6%) with 16 sent up on the held-out set.

