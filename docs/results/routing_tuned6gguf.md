# Routing: which model answers

Measured on the saved answers of the local model run `tuned6gguf` and the hosted gemini-3.5-flash-lite (`gemini-flashlite`), same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).

## core + stress (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 109 of 181 | 60.2% (52.9% to 67.1%) | 0% | $0.01 | 0.000 (11 up, 62 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | 100% | $1.36 |  |
| Rules, 1+ family | 129 of 181 | 71.3% (64.3% to 77.4%) | 31% | $0.49 | 0.000 (6 up, 37 down) |
| Rules, 2+ families | 112 of 181 | 61.9% (54.6% to 68.6%) | 3% | $0.05 | 0.000 (11 up, 59 down) |
| Local, escalate on error or empty | 125 of 181 | 69.1% (62.0% to 75.3%) | 10% | $0.18 | 0.000 (11 up, 46 down) |
| Local, escalate on error, empty or decline | 132 of 181 | 72.9% (66.0% to 78.9%) | 18% | $0.27 | 0.000 (10 up, 38 down) |
| Rules 1+, plus escalate on error, empty or decline | 142 of 181 | 78.5% (71.9% to 83.8%) | 43% | $0.64 | 0.001 (5 up, 23 down) |
| Rules 2+, plus escalate on error, empty or decline | 133 of 181 | 73.5% (66.6% to 79.4%) | 20% | $0.30 | 0.000 (10 up, 37 down) |
| Local, escalate on error, empty, decline or invented value | 137 of 181 | 75.7% (68.9% to 81.4%) | 25% | $0.37 | 0.000 (8 up, 31 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 149 of 181 | 82.3% (76.1% to 87.2%) | 48% | $0.71 | 0.027 (5 up, 16 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 171 of 181 | 94.5% | | | |

## decline set (36 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 36 of 36 | 100.0% (90.4% to 100.0%) | 0% | $0.00 | 0.500 (2 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | 100% | $1.34 |  |
| Rules, 1+ family | 36 of 36 | 100.0% (90.4% to 100.0%) | 6% | $0.08 | 0.500 (2 up, 0 down) |
| Rules, 2+ families | 36 of 36 | 100.0% (90.4% to 100.0%) | 0% | $0.00 | 0.500 (2 up, 0 down) |
| Local, escalate on error or empty | 36 of 36 | 100.0% (90.4% to 100.0%) | 0% | $0.00 | 0.500 (2 up, 0 down) |
| Local, escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.88 | 1.000 (1 up, 0 down) |
| Rules 1+, plus escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 69% | $0.92 | 1.000 (1 up, 0 down) |
| Rules 2+, plus escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.88 | 1.000 (1 up, 0 down) |
| Local, escalate on error, empty, decline or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.88 | 1.000 (1 up, 0 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | 69% | $0.92 | 1.000 (1 up, 0 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 36 of 36 | 100.0% | | | |

## held-out set (52 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 32 of 52 | 61.5% (48.0% to 73.5%) | 0% | $0.02 | 0.007 (2 up, 13 down) |
| All hosted (gemini-3.5-flash-lite) | 43 of 52 | 82.7% (70.3% to 90.6%) | 100% | $1.49 |  |
| Rules, 1+ family | 32 of 52 | 61.5% (48.0% to 73.5%) | 2% | $0.05 | 0.007 (2 up, 13 down) |
| Rules, 2+ families | 32 of 52 | 61.5% (48.0% to 73.5%) | 0% | $0.02 | 0.007 (2 up, 13 down) |
| Local, escalate on error or empty | 35 of 52 | 67.3% (53.8% to 78.5%) | 6% | $0.11 | 0.039 (2 up, 10 down) |
| Local, escalate on error, empty or decline | 35 of 52 | 67.3% (53.8% to 78.5%) | 35% | $0.51 | 0.021 (1 up, 9 down) |
| Rules 1+, plus escalate on error, empty or decline | 35 of 52 | 67.3% (53.8% to 78.5%) | 37% | $0.54 | 0.021 (1 up, 9 down) |
| Rules 2+, plus escalate on error, empty or decline | 35 of 52 | 67.3% (53.8% to 78.5%) | 35% | $0.51 | 0.021 (1 up, 9 down) |
| Local, escalate on error, empty, decline or invented value | 38 of 52 | 73.1% (59.7% to 83.2%) | 42% | $0.63 | 0.125 (1 up, 6 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 38 of 52 | 73.1% (59.7% to 83.2%) | 44% | $0.65 | 0.125 (1 up, 6 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 45 of 52 | 86.5% | | | |

## held-out, routine (12)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 10 of 12 | 83.3% (55.2% to 95.3%) | 0% | $0.01 | 1.000 (1 up, 1 down) |
| All hosted (gemini-3.5-flash-lite) | 10 of 12 | 83.3% (55.2% to 95.3%) | 100% | $1.39 |  |
| Rules, 1+ family | 10 of 12 | 83.3% (55.2% to 95.3%) | 0% | $0.01 | 1.000 (1 up, 1 down) |
| Rules, 2+ families | 10 of 12 | 83.3% (55.2% to 95.3%) | 0% | $0.01 | 1.000 (1 up, 1 down) |
| Local, escalate on error or empty | 10 of 12 | 83.3% (55.2% to 95.3%) | 0% | $0.01 | 1.000 (1 up, 1 down) |
| Local, escalate on error, empty or decline | 10 of 12 | 83.3% (55.2% to 95.3%) | 8% | $0.13 | 1.000 (1 up, 1 down) |
| Rules 1+, plus escalate on error, empty or decline | 10 of 12 | 83.3% (55.2% to 95.3%) | 8% | $0.13 | 1.000 (1 up, 1 down) |
| Rules 2+, plus escalate on error, empty or decline | 10 of 12 | 83.3% (55.2% to 95.3%) | 8% | $0.13 | 1.000 (1 up, 1 down) |
| Local, escalate on error, empty, decline or invented value | 10 of 12 | 83.3% (55.2% to 95.3%) | 8% | $0.13 | 1.000 (1 up, 1 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 10 of 12 | 83.3% (55.2% to 95.3%) | 8% | $0.13 | 1.000 (1 up, 1 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 11 of 12 | 91.7% | | | |

## held-out, complex (24)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 7 of 24 | 29.2% (14.9% to 49.2%) | 0% | $0.03 | 0.000 (0 up, 12 down) |
| All hosted (gemini-3.5-flash-lite) | 19 of 24 | 79.2% (59.5% to 90.8%) | 100% | $1.62 |  |
| Rules, 1+ family | 7 of 24 | 29.2% (14.9% to 49.2%) | 4% | $0.09 | 0.000 (0 up, 12 down) |
| Rules, 2+ families | 7 of 24 | 29.2% (14.9% to 49.2%) | 0% | $0.03 | 0.000 (0 up, 12 down) |
| Local, escalate on error or empty | 10 of 24 | 41.7% (24.5% to 61.2%) | 12% | $0.23 | 0.004 (0 up, 9 down) |
| Local, escalate on error, empty or decline | 11 of 24 | 45.8% (27.9% to 64.9%) | 21% | $0.37 | 0.008 (0 up, 8 down) |
| Rules 1+, plus escalate on error, empty or decline | 11 of 24 | 45.8% (27.9% to 64.9%) | 25% | $0.43 | 0.008 (0 up, 8 down) |
| Rules 2+, plus escalate on error, empty or decline | 11 of 24 | 45.8% (27.9% to 64.9%) | 21% | $0.37 | 0.008 (0 up, 8 down) |
| Local, escalate on error, empty, decline or invented value | 14 of 24 | 58.3% (38.8% to 75.5%) | 38% | $0.62 | 0.062 (0 up, 5 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 14 of 24 | 58.3% (38.8% to 75.5%) | 42% | $0.68 | 0.062 (0 up, 5 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 19 of 24 | 79.2% | | | |

## held-out, should decline (12)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 12 of 12 | 100.0% (75.7% to 100.0%) | 0% | $0.01 | 1.000 (1 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 11 of 12 | 91.7% (64.6% to 98.5%) | 100% | $1.33 |  |
| Rules, 1+ family | 12 of 12 | 100.0% (75.7% to 100.0%) | 0% | $0.01 | 1.000 (1 up, 0 down) |
| Rules, 2+ families | 12 of 12 | 100.0% (75.7% to 100.0%) | 0% | $0.01 | 1.000 (1 up, 0 down) |
| Local, escalate on error or empty | 12 of 12 | 100.0% (75.7% to 100.0%) | 0% | $0.01 | 1.000 (1 up, 0 down) |
| Local, escalate on error, empty or decline | 11 of 12 | 91.7% (64.6% to 98.5%) | 100% | $1.34 | 1.000 (0 up, 0 down) |
| Rules 1+, plus escalate on error, empty or decline | 11 of 12 | 91.7% (64.6% to 98.5%) | 100% | $1.34 | 1.000 (0 up, 0 down) |
| Rules 2+, plus escalate on error, empty or decline | 11 of 12 | 91.7% (64.6% to 98.5%) | 100% | $1.34 | 1.000 (0 up, 0 down) |
| Local, escalate on error, empty, decline or invented value | 11 of 12 | 91.7% (64.6% to 98.5%) | 100% | $1.34 | 1.000 (0 up, 0 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 11 of 12 | 91.7% (64.6% to 98.5%) | 100% | $1.34 | 1.000 (0 up, 0 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 12 of 12 | 100.0% | | | |

## held-out, answerable controls (4)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned6gguf) | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 3 of 4 | 75.0% (30.1% to 95.4%) | 100% | $1.48 |  |
| Rules, 1+ family | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Rules, 2+ families | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Local, escalate on error or empty | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Local, escalate on error, empty or decline | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Rules 1+, plus escalate on error, empty or decline | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Rules 2+, plus escalate on error, empty or decline | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Local, escalate on error, empty, decline or invented value | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 3 of 4 | 75.0% (30.1% to 95.4%) | 0% | $0.01 | 1.000 (0 up, 0 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 3 of 4 | 75.0% | | | |

## How well the rules find the questions the local model gets wrong

Among the core and stress questions the local model failed, and the questions where the hosted model was right and the local one wrong.

| Threshold | Routed to hosted | Of those, local was wrong | Local-wrong questions caught | Local-wrong questions missed |
|---|---|---|---|---|
| 1+ families | 57 of 181 | 30 (53%) | 30 of 72 (42%) | 42 |
| 2+ families | 5 of 181 | 4 (80%) | 4 of 72 (6%) | 68 |

## The rules on the training questions

Share of training questions the 1+ rule would send to the hosted model, by the technique each was generated for. This check uses no test result.

| Technique | Questions | Routed to hosted |
|---|---|---|
| time_bucket | 150 | 91% |
| evidence | 190 | 58% |
| window | 187 | 52% |
| correlated | 182 | 24% |
| set_ops | 154 | 18% |
| pivot | 185 | 18% |
| cte_multistep | 197 | 13% |
| hierarchy | 161 | 10% |
| decline_unanswerable | 200 | 6% |
| decline_ambiguous | 129 | 5% |
| date_time | 150 | 4% |
| lookup_filter | 90 | 3% |
| fanout | 170 | 2% |
| aggregate | 120 | 2% |
| state_codes | 140 | 1% |
| multi_join | 178 | 1% |

## Misses and false alarms

Hosted right, local wrong, and the rules kept it local (37):

- L02 (lookup): Which region is customer C-1010 in?
- L03 (lookup): What is the total amount of order O-5002, and in which currency?
- J05 (join): Which employees are assigned to open tickets of critical severity, which is severity level 1? Show their names.
- G04 (group_by): What is the average number of lines per order?
- D03 (date_time): As of 2026-10-31 18:00:00, how many tickets have been open for more than 7 days, meaning more than 168 hours?
- D04 (date_time): What is the average time to close a ticket, in hours, across the tickets that have been closed? Round to one decimal place.
- D06 (date_time): How many orders were placed on a Saturday or a Sunday?
- N01 (nulls_state): How many tickets are currently open?
- H01 (hierarchy): Who is the direct manager of employee E-012? Show the manager's name.
- H03 (hierarchy): How many employees report to E-001, directly or through other managers?
- P03 (policy_dates): How many refund requests made in 2026 were for an amount above the approval threshold that was in force on the day they were requested? Compare the amounts as stored and ignore currency.
- HJ02 (multi_join): For each product category, how many units were taken out of stock at the Rotterdam Hub warehouse? Show the category code and the units as a positive number.

## Held-out set: how well the rules find the local failures

| Threshold | Routed to hosted | Local wrong among them (precision) | Local-wrong questions caught (recall) |
|---|---|---|---|
| 1+ families | 1 of 52 | 0 of 1 | 0 of 20 |
| 2+ families | 0 of 52 | 0 of 0 | 0 of 20 |
