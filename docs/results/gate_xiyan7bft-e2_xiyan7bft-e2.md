# Decline gate in front of a local SQL model

Gate: `xiyan7bft-e2`. SQL model: `xiyan7bft-e2`. Hosted reference: `gemini-flashlite`. Computed from saved single-run answers; a strategy only chooses which saved answer is used. The core set includes 6 should-decline questions, so gate refusals there count as correct.

## core + stress, answerable (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 127 of 181 | 70.2% (63.1% to 76.4%) | $0.08 | 0.000 (12 up, 45 down) |
| 7B alone (xiyan7bft-e2) | 127 of 181 | 70.2% (63.1% to 76.4%) | $0.08 | 0.000 (12 up, 45 down) |
| 3B decline gate + 7B SQL | 127 of 181 | 70.2% (63.1% to 76.4%) | $0.15 | 0.000 (12 up, 45 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 140 of 181 | 77.3% (70.7% to 82.8%) | $0.31 | 0.004 (12 up, 32 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 147 of 181 | 81.2% (74.9% to 86.2%) | $0.68 | 0.011 (5 up, 18 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 147 of 181 | 81.2% (74.9% to 86.2%) | $0.71 | 0.011 (5 up, 18 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 140 of 181 | 77.3% (70.7% to 82.8%) | $0.34 | 0.003 (11 up, 31 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | $1.36 |  |

## decline set (36 questions: 12 controls, 24 should decline)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.04 | 1.000 (2 up, 3 down) |
| 7B alone (xiyan7bft-e2) | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.04 | 1.000 (2 up, 3 down) |
| 3B decline gate + 7B SQL | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.06 | 1.000 (2 up, 3 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.06 | 1.000 (2 up, 3 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.13 | 1.000 (2 up, 3 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.10 | 1.000 (2 up, 3 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 33 of 36 | 91.7% (78.2% to 97.1%) | $0.06 | 1.000 (2 up, 3 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | $1.34 |  |

## held-out set (52 questions)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 36 of 52 | 69.2% (55.7% to 80.1%) | $0.07 | 0.092 (3 up, 10 down) |
| 7B alone (xiyan7bft-e2) | 36 of 52 | 69.2% (55.7% to 80.1%) | $0.07 | 0.092 (3 up, 10 down) |
| 3B decline gate + 7B SQL | 36 of 52 | 69.2% (55.7% to 80.1%) | $0.13 | 0.092 (3 up, 10 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 39 of 52 | 75.0% (61.8% to 84.8%) | $0.28 | 0.344 (3 up, 7 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 39 of 52 | 75.0% (61.8% to 84.8%) | $0.30 | 0.344 (3 up, 7 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 39 of 52 | 75.0% (61.8% to 84.8%) | $0.30 | 0.344 (3 up, 7 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 39 of 52 | 75.0% (61.8% to 84.8%) | $0.28 | 0.344 (3 up, 7 down) |
| All hosted (gemini-3.5-flash-lite) | 43 of 52 | 82.7% (70.3% to 90.6%) | $1.49 |  |

## held-out, routine (12)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.04 | 0.500 (2 up, 0 down) |
| 7B alone (xiyan7bft-e2) | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.04 | 0.500 (2 up, 0 down) |
| 3B decline gate + 7B SQL | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.07 | 0.500 (2 up, 0 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.07 | 0.500 (2 up, 0 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.07 | 0.500 (2 up, 0 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.07 | 0.500 (2 up, 0 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.07 | 0.500 (2 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 10 of 12 | 83.3% (55.2% to 95.3%) | $1.39 |  |

## held-out, complex (24)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 11 of 24 | 45.8% (27.9% to 64.9%) | $0.10 | 0.008 (0 up, 8 down) |
| 7B alone (xiyan7bft-e2) | 11 of 24 | 45.8% (27.9% to 64.9%) | $0.10 | 0.008 (0 up, 8 down) |
| 3B decline gate + 7B SQL | 11 of 24 | 45.8% (27.9% to 64.9%) | $0.21 | 0.008 (0 up, 8 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 14 of 24 | 58.3% (38.8% to 75.5%) | $0.53 | 0.062 (0 up, 5 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 14 of 24 | 58.3% (38.8% to 75.5%) | $0.59 | 0.062 (0 up, 5 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 14 of 24 | 58.3% (38.8% to 75.5%) | $0.59 | 0.062 (0 up, 5 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 14 of 24 | 58.3% (38.8% to 75.5%) | $0.53 | 0.062 (0 up, 5 down) |
| All hosted (gemini-3.5-flash-lite) | 19 of 24 | 79.2% (59.5% to 90.8%) | $1.62 |  |

## held-out, should decline (12)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| 7B alone (xiyan7bft-e2) | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| 3B decline gate + 7B SQL | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 1 down) |
| All hosted (gemini-3.5-flash-lite) | 11 of 12 | 91.7% (64.6% to 98.5%) | $1.33 |  |

## held-out, answerable controls (4)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (xiyan7bft-e2) | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.05 | 1.000 (0 up, 1 down) |
| 7B alone (xiyan7bft-e2) | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.05 | 1.000 (0 up, 1 down) |
| 3B decline gate + 7B SQL | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.11 | 1.000 (0 up, 1 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.11 | 1.000 (0 up, 1 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.11 | 1.000 (0 up, 1 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.11 | 1.000 (0 up, 1 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 2 of 4 | 50.0% (15.0% to 85.0%) | $0.11 | 1.000 (0 up, 1 down) |
| All hosted (gemini-3.5-flash-lite) | 3 of 4 | 75.0% (30.1% to 95.4%) | $1.48 |  |

## What the gate costs

- Answerable core and stress questions the 7B got right but the gate refused: 0 (none).
- Decline-set controls the 7B got right but the gate refused: 0.

