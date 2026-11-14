# Routing: which model answers

Measured on the saved answers of the local model run `xiyan7b-final` and the hosted gemini-3.5-flash-lite (`gemini-flashlite`), same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).

## core + stress (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (xiyan7b-final) | 125 of 181 | 69.1% (62.0% to 75.3%) | 0% | $0.03 | 0.000 (10 up, 45 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | 100% | $1.36 |  |
| Rules, 1+ family | 138 of 181 | 76.2% (69.5% to 81.9%) | 31% | $0.50 | 0.000 (3 up, 25 down) |
| Rules, 2+ families | 125 of 181 | 69.1% (62.0% to 75.3%) | 3% | $0.07 | 0.000 (9 up, 44 down) |
| Local, escalate on error or empty | 136 of 181 | 75.1% (68.4% to 80.9%) | 8% | $0.15 | 0.000 (10 up, 34 down) |
| Local, escalate on error, empty or decline | 136 of 181 | 75.1% (68.4% to 80.9%) | 8% | $0.15 | 0.000 (10 up, 34 down) |
| Rules 1+, plus escalate on error, empty or decline | 147 of 181 | 81.2% (74.9% to 86.2%) | 39% | $0.61 | 0.004 (3 up, 16 down) |
| Rules 2+, plus escalate on error, empty or decline | 136 of 181 | 75.1% (68.4% to 80.9%) | 11% | $0.20 | 0.000 (9 up, 33 down) |
| Local, escalate on error, empty, decline or invented value | 139 of 181 | 76.8% (70.1% to 82.3%) | 12% | $0.20 | 0.001 (9 up, 30 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 149 of 181 | 82.3% (76.1% to 87.2%) | 40% | $0.63 | 0.013 (3 up, 14 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 170 of 181 | 93.9% | | | |

## decline set (36 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (xiyan7b-final) | 15 of 36 | 41.7% (27.1% to 57.8%) | 0% | $0.02 | 0.000 (1 up, 20 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | 100% | $1.34 |  |
| Rules, 1+ family | 16 of 36 | 44.4% (29.5% to 60.4%) | 6% | $0.09 | 0.000 (1 up, 19 down) |
| Rules, 2+ families | 15 of 36 | 41.7% (27.1% to 57.8%) | 0% | $0.02 | 0.000 (1 up, 20 down) |
| Local, escalate on error or empty | 15 of 36 | 41.7% (27.1% to 57.8%) | 0% | $0.02 | 0.000 (1 up, 20 down) |
| Local, escalate on error, empty or decline | 15 of 36 | 41.7% (27.1% to 57.8%) | 11% | $0.17 | 0.000 (1 up, 20 down) |
| Rules 1+, plus escalate on error, empty or decline | 16 of 36 | 44.4% (29.5% to 60.4%) | 17% | $0.24 | 0.000 (1 up, 19 down) |
| Rules 2+, plus escalate on error, empty or decline | 15 of 36 | 41.7% (27.1% to 57.8%) | 11% | $0.17 | 0.000 (1 up, 20 down) |
| Local, escalate on error, empty, decline or invented value | 20 of 36 | 55.6% (39.6% to 70.5%) | 25% | $0.35 | 0.001 (1 up, 15 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 21 of 36 | 58.3% (42.2% to 72.9%) | 31% | $0.42 | 0.001 (1 up, 14 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 35 of 36 | 97.2% | | | |

## How well the rules find the questions the local model gets wrong

Among the core and stress questions the local model failed, and the questions where the hosted model was right and the local one wrong.

| Threshold | Routed to hosted | Of those, local was wrong | Local-wrong questions caught | Local-wrong questions missed |
|---|---|---|---|---|
| 1+ families | 57 of 181 | 23 (40%) | 23 of 56 (41%) | 33 |
| 2+ families | 5 of 181 | 1 (20%) | 1 of 56 (2%) | 55 |

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

Hosted right, local wrong, and the rules kept it local (25):

- J05 (join): Which employees are assigned to open tickets of critical severity, which is severity level 1? Show their names.
- D04 (date_time): What is the average time to close a ticket, in hours, across the tickets that have been closed? Round to one decimal place.
- F04 (fanout_trap): What is the total quantity ordered in each product category? Show the category code and the quantity.
- H03 (hierarchy): How many employees report to E-001, directly or through other managers?
- P03 (policy_dates): How many refund requests made in 2026 were for an amount above the approval threshold that was in force on the day they were requested? Compare the amounts as stored and ignore currency.
- U04 (unanswerable): How much profit did we make last month?
- M01 (ambiguous): Show me our best customers.
- M02 (ambiguous): What is our revenue?
- HJ02 (multi_join): For each product category, how many units were taken out of stock at the Rotterdam Hub warehouse? Show the category code and the units as a positive number.
- HJ05 (multi_join): For delivered shipments only, what is the average number of days between the ship date and the delivery date for each warehouse? Show the warehouse name and the average rounded to one decimal.
- HC08 (cte_multistep): How many distinct customers moved from the REG segment in one month straight to the RISK segment in the very next month, according to the segment history?
- HE03 (correlated): Which tickets that are still open were opened by a customer who placed no order in the 30 days before the ticket was opened? Show the ticket ids.
