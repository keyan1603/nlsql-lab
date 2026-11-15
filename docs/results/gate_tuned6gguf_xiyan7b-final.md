# Decline gate in front of a local SQL model

Gate: `tuned6gguf`. SQL model: `xiyan7b-final`. Hosted reference: `gemini-flashlite`. Computed from saved single-run answers; a strategy only chooses which saved answer is used. The core set includes 6 should-decline questions, so gate refusals there count as correct.

## core + stress, answerable (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 109 of 181 | 60.2% (52.9% to 67.1%) | $0.01 | 0.000 (11 up, 62 down) |
| 7B alone (xiyan7b-final) | 125 of 181 | 69.1% (62.0% to 75.3%) | $0.03 | 0.000 (10 up, 45 down) |
| 3B decline gate + 7B SQL | 127 of 181 | 70.2% (63.1% to 76.4%) | $0.04 | 0.000 (11 up, 44 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 136 of 181 | 75.1% (68.4% to 80.9%) | $0.17 | 0.000 (10 up, 34 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 147 of 181 | 81.2% (74.9% to 86.2%) | $0.60 | 0.007 (4 up, 17 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 146 of 181 | 80.7% (74.3% to 85.8%) | $0.59 | 0.004 (4 up, 18 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 136 of 181 | 75.1% (68.4% to 80.9%) | $0.21 | 0.000 (9 up, 33 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | $1.36 |  |

## decline set (36 questions: 12 controls, 24 should decline)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 36 of 36 | 100.0% (90.4% to 100.0%) | $0.00 | 0.500 (2 up, 0 down) |
| 7B alone (xiyan7b-final) | 15 of 36 | 41.7% (27.1% to 57.8%) | $0.02 | 0.000 (1 up, 20 down) |
| 3B decline gate + 7B SQL | 35 of 36 | 97.2% (85.8% to 99.5%) | $0.01 | 1.000 (2 up, 1 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | $0.01 | 1.000 (2 up, 1 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 35 of 36 | 97.2% (85.8% to 99.5%) | $0.08 | 1.000 (2 up, 1 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 35 of 36 | 97.2% (85.8% to 99.5%) | $0.05 | 1.000 (2 up, 1 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 35 of 36 | 97.2% (85.8% to 99.5%) | $0.01 | 1.000 (2 up, 1 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | $1.34 |  |

## held-out set (52 questions)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 32 of 52 | 61.5% (48.0% to 73.5%) | $0.02 | 0.007 (2 up, 13 down) |
| 7B alone (xiyan7b-final) | 27 of 52 | 51.9% (38.7% to 64.9%) | $0.05 | 0.001 (3 up, 19 down) |
| 3B decline gate + 7B SQL | 38 of 52 | 73.1% (59.7% to 83.2%) | $0.05 | 0.227 (3 up, 8 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.20 | 1.000 (3 up, 4 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.23 | 1.000 (3 up, 4 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.23 | 1.000 (3 up, 4 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 42 of 52 | 80.8% (68.1% to 89.2%) | $0.20 | 1.000 (3 up, 4 down) |
| All hosted (gemini-3.5-flash-lite) | 43 of 52 | 82.7% (70.3% to 90.6%) | $1.49 |  |

## held-out, routine (12)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 10 of 12 | 83.3% (55.2% to 95.3%) | $0.01 | 1.000 (1 up, 1 down) |
| 7B alone (xiyan7b-final) | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.02 | 0.500 (2 up, 0 down) |
| 3B decline gate + 7B SQL | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 0 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 0 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 0 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 0 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 11 of 12 | 91.7% (64.6% to 98.5%) | $0.03 | 1.000 (1 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 10 of 12 | 83.3% (55.2% to 95.3%) | $1.39 |  |

## held-out, complex (24)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 7 of 24 | 29.2% (14.9% to 49.2%) | $0.03 | 0.000 (0 up, 12 down) |
| 7B alone (xiyan7b-final) | 12 of 24 | 50.0% (31.4% to 68.6%) | $0.07 | 0.039 (1 up, 8 down) |
| 3B decline gate + 7B SQL | 12 of 24 | 50.0% (31.4% to 68.6%) | $0.09 | 0.039 (1 up, 8 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 16 of 24 | 66.7% (46.7% to 82.0%) | $0.41 | 0.375 (1 up, 4 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 16 of 24 | 66.7% (46.7% to 82.0%) | $0.47 | 0.375 (1 up, 4 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 16 of 24 | 66.7% (46.7% to 82.0%) | $0.47 | 0.375 (1 up, 4 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 16 of 24 | 66.7% (46.7% to 82.0%) | $0.41 | 0.375 (1 up, 4 down) |
| All hosted (gemini-3.5-flash-lite) | 19 of 24 | 79.2% (59.5% to 90.8%) | $1.62 |  |

## held-out, should decline (12)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.01 | 1.000 (1 up, 0 down) |
| 7B alone (xiyan7b-final) | 0 of 12 | 0.0% (0.0% to 24.3%) | $0.03 | 0.001 (0 up, 11 down) |
| 3B decline gate + 7B SQL | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.01 | 1.000 (1 up, 0 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.01 | 1.000 (1 up, 0 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.01 | 1.000 (1 up, 0 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.01 | 1.000 (1 up, 0 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 12 of 12 | 100.0% (75.7% to 100.0%) | $0.01 | 1.000 (1 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 11 of 12 | 91.7% (64.6% to 98.5%) | $1.33 |  |

## held-out, answerable controls (4)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6gguf) | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.01 | 1.000 (0 up, 0 down) |
| 7B alone (xiyan7b-final) | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.02 | 1.000 (0 up, 0 down) |
| 3B decline gate + 7B SQL | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.03 | 1.000 (0 up, 0 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.03 | 1.000 (0 up, 0 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.03 | 1.000 (0 up, 0 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.03 | 1.000 (0 up, 0 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 3 of 4 | 75.0% (30.1% to 95.4%) | $0.03 | 1.000 (0 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 3 of 4 | 75.0% (30.1% to 95.4%) | $1.48 |  |

## What the gate costs

- Answerable core and stress questions the 7B got right but the gate refused: 3 (HE02, HS08, HD05).
- Decline-set controls the 7B got right but the gate refused: 0.

