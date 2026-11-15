# Decline gate in front of a local SQL model

Gate: `tuned6r2`. SQL model: `xiyan7b-final`. Hosted reference: `gemini-flashlite`. Computed from saved single-run answers; a strategy only chooses which saved answer is used. The core set includes 6 should-decline questions, so gate refusals there count as correct.

## core + stress, answerable (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6r2) | 104 of 181 | 57.5% (50.2% to 64.4%) | $0.06 | 0.000 (10 up, 66 down) |
| 7B alone (xiyan7b-final) | 125 of 181 | 69.1% (62.0% to 75.3%) | $0.03 | 0.000 (10 up, 45 down) |
| 3B decline gate + 7B SQL | 127 of 181 | 70.2% (63.1% to 76.4%) | $0.09 | 0.000 (11 up, 44 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 138 of 181 | 76.2% (69.5% to 81.9%) | $0.24 | 0.001 (10 up, 32 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 148 of 181 | 81.8% (75.5% to 86.7%) | $0.64 | 0.012 (4 up, 16 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 147 of 181 | 81.2% (74.9% to 86.2%) | $0.65 | 0.007 (4 up, 17 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 138 of 181 | 76.2% (69.5% to 81.9%) | $0.28 | 0.001 (9 up, 31 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | $1.36 |  |

## decline set (36 questions: 12 controls, 24 should decline)

| Strategy | Correct | Accuracy (95% interval) | Local cost per 1,000 incl. any hosted | vs all hosted, sign test p |
|---|---|---|---|---|
| 3B alone (tuned6r2) | 35 of 36 | 97.2% (85.8% to 99.5%) | $0.02 | 1.000 (2 up, 1 down) |
| 7B alone (xiyan7b-final) | 15 of 36 | 41.7% (27.1% to 57.8%) | $0.02 | 0.000 (1 up, 20 down) |
| 3B decline gate + 7B SQL | 34 of 36 | 94.4% (81.9% to 98.5%) | $0.03 | 1.000 (2 up, 2 down) |
| 3B decline gate + 7B SQL, escalate on error, empty or invented value | 34 of 36 | 94.4% (81.9% to 98.5%) | $0.03 | 1.000 (2 up, 2 down) |
| Rules 1+ first, then 3B gate, then 7B with escalation | 34 of 36 | 94.4% (81.9% to 98.5%) | $0.10 | 1.000 (2 up, 2 down) |
| 3B gate first, then rules 1+, then 7B with escalation | 34 of 36 | 94.4% (81.9% to 98.5%) | $0.06 | 1.000 (2 up, 2 down) |
| 3B gate first, then rules 2+, then 7B with escalation | 34 of 36 | 94.4% (81.9% to 98.5%) | $0.03 | 1.000 (2 up, 2 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | $1.34 |  |

## What the gate costs

- Answerable core and stress questions the 7B got right but the gate refused: 3 (HE02, HS08, HT10).
- Decline-set controls the 7B got right but the gate refused: 0.

