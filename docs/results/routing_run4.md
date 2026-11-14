# Routing: which model answers

Measured on the saved answers of the local tuned 3B model (`tuned4r2`: up to two repair attempts) and the hosted gemini-3.5-flash-lite (`gemini-flashlite`), same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).

## core + stress (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned 3B + retry) | 96 of 181 | 53.0% (45.8% to 60.2%) | 0% | $0.05 | 0.000 (11 up, 75 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | 100% | $1.36 |  |
| Rules, 1+ family | 122 of 181 | 67.4% (60.3% to 73.8%) | 31% | $0.51 | 0.000 (6 up, 44 down) |
| Rules, 2+ families | 98 of 181 | 54.1% (46.9% to 61.2%) | 3% | $0.09 | 0.000 (11 up, 73 down) |
| Local, escalate on error or empty | 115 of 181 | 63.5% (56.3% to 70.2%) | 12% | $0.25 | 0.000 (11 up, 56 down) |
| Local, escalate on error, empty or decline | 127 of 181 | 70.2% (63.1% to 76.4%) | 23% | $0.35 | 0.000 (10 up, 43 down) |
| Rules 1+, plus escalate on error, empty or decline | 140 of 181 | 77.3% (70.7% to 82.8%) | 45% | $0.68 | 0.000 (5 up, 25 down) |
| Rules 2+, plus escalate on error, empty or decline | 128 of 181 | 70.7% (63.7% to 76.9%) | 25% | $0.39 | 0.000 (10 up, 42 down) |
| Local, escalate on error, empty, decline or invented value | 126 of 181 | 69.6% (62.6% to 75.8%) | 25% | $0.38 | 0.000 (8 up, 42 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 141 of 181 | 77.9% (71.3% to 83.3%) | 46% | $0.69 | 0.001 (5 up, 24 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 171 of 181 | 94.5% | | | |

## decline set (36 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned 3B + retry) | 35 of 36 | 97.2% (85.8% to 99.5%) | 0% | $0.02 | 1.000 (2 up, 1 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | 100% | $1.34 |  |
| Rules, 1+ family | 35 of 36 | 97.2% (85.8% to 99.5%) | 6% | $0.09 | 1.000 (2 up, 1 down) |
| Rules, 2+ families | 35 of 36 | 97.2% (85.8% to 99.5%) | 0% | $0.02 | 1.000 (2 up, 1 down) |
| Local, escalate on error or empty | 35 of 36 | 97.2% (85.8% to 99.5%) | 0% | $0.02 | 1.000 (2 up, 1 down) |
| Local, escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.90 | 1.000 (1 up, 0 down) |
| Rules 1+, plus escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 69% | $0.93 | 1.000 (1 up, 0 down) |
| Rules 2+, plus escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.90 | 1.000 (1 up, 0 down) |
| Local, escalate on error, empty, decline or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.90 | 1.000 (1 up, 0 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | 69% | $0.93 | 1.000 (1 up, 0 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 36 of 36 | 100.0% | | | |

## How well the rules find the questions the local model gets wrong

Among the core and stress questions the local model failed, and the questions where the hosted model was right and the local one wrong.

| Threshold | Routed to hosted | Of those, local was wrong | Local-wrong questions caught | Local-wrong questions missed |
|---|---|---|---|---|
| 1+ families | 57 of 181 | 36 (63%) | 36 of 85 (42%) | 49 |
| 2+ families | 5 of 181 | 3 (60%) | 3 of 85 (4%) | 82 |

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

Hosted right, local wrong, and the rules kept it local (44):

- A03 (filter_aggregate): How many orders were cancelled?
- A06 (filter_aggregate): How many orders were placed through the mobile app?
- A07 (filter_aggregate): How many refund requests are still pending?
- J05 (join): Which employees are assigned to open tickets of critical severity, which is severity level 1? Show their names.
- J06 (join): What is the name of the customer behind refund request R-9003?
- G04 (group_by): What is the average number of lines per order?
- D04 (date_time): What is the average time to close a ticket, in hours, across the tickets that have been closed? Round to one decimal place.
- D06 (date_time): How many orders were placed on a Saturday or a Sunday?
- N01 (nulls_state): How many tickets are currently open?
- F03 (fanout_trap): How many orders have at least one line with a discount above zero percent?
- H03 (hierarchy): How many employees report to E-001, directly or through other managers?
- P03 (policy_dates): How many refund requests made in 2026 were for an amount above the approval threshold that was in force on the day they were requested? Compare the amounts as stored and ignore currency.
