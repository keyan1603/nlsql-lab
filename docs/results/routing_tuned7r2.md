# Routing: which model answers

Measured on the saved answers of the local model run `tuned7r2` and the hosted gemini-3.5-flash-lite (`gemini-flashlite`), same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).

## core + stress (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned7r2) | 110 of 181 | 60.8% (53.5% to 67.6%) | 0% | $0.04 | 0.000 (12 up, 62 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | 100% | $1.36 |  |
| Rules, 1+ family | 134 of 181 | 74.0% (67.2% to 79.9%) | 31% | $0.51 | 0.000 (6 up, 32 down) |
| Rules, 2+ families | 112 of 181 | 61.9% (54.6% to 68.6%) | 3% | $0.09 | 0.000 (11 up, 59 down) |
| Local, escalate on error or empty | 124 of 181 | 68.5% (61.4% to 74.8%) | 10% | $0.21 | 0.000 (12 up, 48 down) |
| Local, escalate on error, empty or decline | 133 of 181 | 73.5% (66.6% to 79.4%) | 19% | $0.33 | 0.000 (11 up, 38 down) |
| Rules 1+, plus escalate on error, empty or decline | 144 of 181 | 79.6% (73.1% to 84.8%) | 43% | $0.66 | 0.002 (5 up, 21 down) |
| Rules 2+, plus escalate on error, empty or decline | 135 of 181 | 74.6% (67.8% to 80.4%) | 22% | $0.37 | 0.000 (10 up, 35 down) |
| Local, escalate on error, empty, decline or invented value | 138 of 181 | 76.2% (69.5% to 81.9%) | 24% | $0.40 | 0.001 (10 up, 32 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 148 of 181 | 81.8% (75.5% to 86.7%) | 46% | $0.71 | 0.017 (5 up, 17 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 172 of 181 | 95.0% | | | |

## decline set (36 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned7r2) | 36 of 36 | 100.0% (90.4% to 100.0%) | 0% | $0.02 | 0.500 (2 up, 0 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | 100% | $1.34 |  |
| Rules, 1+ family | 36 of 36 | 100.0% (90.4% to 100.0%) | 6% | $0.09 | 0.500 (2 up, 0 down) |
| Rules, 2+ families | 36 of 36 | 100.0% (90.4% to 100.0%) | 0% | $0.02 | 0.500 (2 up, 0 down) |
| Local, escalate on error or empty | 36 of 36 | 100.0% (90.4% to 100.0%) | 0% | $0.02 | 0.500 (2 up, 0 down) |
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
| 1+ families | 57 of 181 | 34 (60%) | 34 of 71 (48%) | 37 |
| 2+ families | 5 of 181 | 3 (60%) | 3 of 71 (4%) | 68 |

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

Hosted right, local wrong, and the rules kept it local (32):

- J04 (join): Show the ticket id and the customer name for every ticket that is still open.
- J05 (join): Which employees are assigned to open tickets of critical severity, which is severity level 1? Show their names.
- D03 (date_time): As of 2026-10-31 18:00:00, how many tickets have been open for more than 7 days, meaning more than 168 hours?
- D04 (date_time): What is the average time to close a ticket, in hours, across the tickets that have been closed? Round to one decimal place.
- D06 (date_time): How many orders were placed on a Saturday or a Sunday?
- N01 (nulls_state): How many tickets are currently open?
- H01 (hierarchy): Who is the direct manager of employee E-012? Show the manager's name.
- H03 (hierarchy): How many employees report to E-001, directly or through other managers?
- HJ02 (multi_join): For each product category, how many units were taken out of stock at the Rotterdam Hub warehouse? Show the category code and the units as a positive number.
- HJ04 (multi_join): Which employees approved refunds on orders placed by customers in the EU region? Show the employee name and how many refunds they approved there.
- HJ05 (multi_join): For delivered shipments only, what is the average number of days between the ship date and the delivery date for each warehouse? Show the warehouse name and the average rounded to one decimal.
- HW05 (window): For every product category, list the two products with the most units ordered. Show the category code, the product name, the units and the position (1 or 2), ordered by category code and position; break ties between products by product name.
