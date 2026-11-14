# Routing: which model answers

Measured on the saved answers of the local tuned 3B model (`tuned6r2`: up to two repair attempts) and the hosted gemini-3.5-flash-lite (`gemini-flashlite`), same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).

## core + stress (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned 3B + retry) | 104 of 181 | 57.5% (50.2% to 64.4%) | 0% | $0.06 | 0.000 (10 up, 66 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | 100% | $1.36 |  |
| Rules, 1+ family | 129 of 181 | 71.3% (64.3% to 77.4%) | 31% | $0.52 | 0.000 (6 up, 37 down) |
| Rules, 2+ families | 106 of 181 | 58.6% (51.3% to 65.5%) | 3% | $0.11 | 0.000 (10 up, 64 down) |
| Local, escalate on error or empty | 124 of 181 | 68.5% (61.4% to 74.8%) | 13% | $0.27 | 0.000 (10 up, 46 down) |
| Local, escalate on error, empty or decline | 127 of 181 | 70.2% (63.1% to 76.4%) | 19% | $0.34 | 0.000 (9 up, 42 down) |
| Rules 1+, plus escalate on error, empty or decline | 145 of 181 | 80.1% (73.7% to 85.3%) | 45% | $0.71 | 0.004 (5 up, 20 down) |
| Rules 2+, plus escalate on error, empty or decline | 129 of 181 | 71.3% (64.3% to 77.4%) | 22% | $0.38 | 0.000 (9 up, 40 down) |
| Local, escalate on error, empty, decline or invented value | 134 of 181 | 74.0% (67.2% to 79.9%) | 24% | $0.39 | 0.000 (9 up, 35 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 151 of 181 | 83.4% (77.3% to 88.1%) | 49% | $0.76 | 0.064 (5 up, 14 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 170 of 181 | 93.9% | | | |

## decline set (36 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned 3B + retry) | 35 of 36 | 97.2% (85.8% to 99.5%) | 0% | $0.02 | 1.000 (2 up, 1 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | 100% | $1.34 |  |
| Rules, 1+ family | 35 of 36 | 97.2% (85.8% to 99.5%) | 6% | $0.10 | 1.000 (2 up, 1 down) |
| Rules, 2+ families | 35 of 36 | 97.2% (85.8% to 99.5%) | 0% | $0.02 | 1.000 (2 up, 1 down) |
| Local, escalate on error or empty | 35 of 36 | 97.2% (85.8% to 99.5%) | 0% | $0.02 | 1.000 (2 up, 1 down) |
| Local, escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.90 | 1.000 (1 up, 0 down) |
| Rules 1+, plus escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 69% | $0.94 | 1.000 (1 up, 0 down) |
| Rules 2+, plus escalate on error, empty or decline | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.90 | 1.000 (1 up, 0 down) |
| Local, escalate on error, empty, decline or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | 67% | $0.90 | 1.000 (1 up, 0 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 35 of 36 | 97.2% (85.8% to 99.5%) | 69% | $0.94 | 1.000 (1 up, 0 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 36 of 36 | 100.0% | | | |

## How well the rules find the questions the local model gets wrong

Among the core and stress questions the local model failed, and the questions where the hosted model was right and the local one wrong.

| Threshold | Routed to hosted | Of those, local was wrong | Local-wrong questions caught | Local-wrong questions missed |
|---|---|---|---|---|
| 1+ families | 57 of 181 | 35 (61%) | 35 of 77 (45%) | 42 |
| 2+ families | 5 of 181 | 3 (60%) | 3 of 77 (4%) | 74 |

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

- J04 (join): Show the ticket id and the customer name for every ticket that is still open.
- J05 (join): Which employees are assigned to open tickets of critical severity, which is severity level 1? Show their names.
- J06 (join): What is the name of the customer behind refund request R-9003?
- G04 (group_by): What is the average number of lines per order?
- D03 (date_time): As of 2026-10-31 18:00:00, how many tickets have been open for more than 7 days, meaning more than 168 hours?
- D04 (date_time): What is the average time to close a ticket, in hours, across the tickets that have been closed? Round to one decimal place.
- D06 (date_time): How many orders were placed on a Saturday or a Sunday?
- N01 (nulls_state): How many tickets are currently open?
- H01 (hierarchy): Who is the direct manager of employee E-012? Show the manager's name.
- H03 (hierarchy): How many employees report to E-001, directly or through other managers?
- P01 (policy_dates): What is the refund approval threshold in force on 2026-10-31?
- HJ02 (multi_join): For each product category, how many units were taken out of stock at the Rotterdam Hub warehouse? Show the category code and the units as a positive number.
