# Routing: which model answers

Measured on the saved answers of the local model run `tuned8r2` and the hosted gemini-3.5-flash-lite (`gemini-flashlite`), same questions, same grader. A strategy only picks which saved answer is used. Hosted answers are single runs (not bit-repeatable).

## core + stress (181 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned8r2) | 101 of 181 | 55.8% (48.5% to 62.8%) | 0% | $0.04 | 0.000 (10 up, 69 down) |
| All hosted (gemini-3.5-flash-lite) | 160 of 181 | 88.4% (82.9% to 92.3%) | 100% | $1.36 |  |
| Rules, 1+ family | 126 of 181 | 69.6% (62.6% to 75.8%) | 31% | $0.51 | 0.000 (6 up, 40 down) |
| Rules, 2+ families | 104 of 181 | 57.5% (50.2% to 64.4%) | 3% | $0.09 | 0.000 (10 up, 66 down) |
| Local, escalate on error or empty | 117 of 181 | 64.6% (57.4% to 71.2%) | 11% | $0.23 | 0.000 (10 up, 53 down) |
| Local, escalate on error, empty or decline | 129 of 181 | 71.3% (64.3% to 77.4%) | 22% | $0.37 | 0.000 (9 up, 40 down) |
| Rules 1+, plus escalate on error, empty or decline | 142 of 181 | 78.5% (71.9% to 83.8%) | 45% | $0.68 | 0.001 (5 up, 23 down) |
| Rules 2+, plus escalate on error, empty or decline | 131 of 181 | 72.4% (65.4% to 78.4%) | 24% | $0.40 | 0.000 (9 up, 38 down) |
| Local, escalate on error, empty, decline or invented value | 130 of 181 | 71.8% (64.9% to 77.9%) | 23% | $0.38 | 0.000 (9 up, 39 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 143 of 181 | 79.0% (72.5% to 84.3%) | 46% | $0.69 | 0.002 (5 up, 22 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 170 of 181 | 93.9% | | | |

## decline set (36 questions)

| Strategy | Correct | Accuracy (95% interval) | Sent to hosted | Cost per 1,000 questions | vs all hosted, paired sign test p |
|---|---|---|---|---|---|
| All local (tuned8r2) | 34 of 36 | 94.4% (81.9% to 98.5%) | 0% | $0.02 | 1.000 (2 up, 2 down) |
| All hosted (gemini-3.5-flash-lite) | 34 of 36 | 94.4% (81.9% to 98.5%) | 100% | $1.34 |  |
| Rules, 1+ family | 34 of 36 | 94.4% (81.9% to 98.5%) | 6% | $0.09 | 1.000 (2 up, 2 down) |
| Rules, 2+ families | 34 of 36 | 94.4% (81.9% to 98.5%) | 0% | $0.02 | 1.000 (2 up, 2 down) |
| Local, escalate on error or empty | 34 of 36 | 94.4% (81.9% to 98.5%) | 0% | $0.02 | 1.000 (2 up, 2 down) |
| Local, escalate on error, empty or decline | 34 of 36 | 94.4% (81.9% to 98.5%) | 67% | $0.90 | 1.000 (1 up, 1 down) |
| Rules 1+, plus escalate on error, empty or decline | 34 of 36 | 94.4% (81.9% to 98.5%) | 69% | $0.93 | 1.000 (1 up, 1 down) |
| Rules 2+, plus escalate on error, empty or decline | 34 of 36 | 94.4% (81.9% to 98.5%) | 67% | $0.90 | 1.000 (1 up, 1 down) |
| Local, escalate on error, empty, decline or invented value | 34 of 36 | 94.4% (81.9% to 98.5%) | 67% | $0.90 | 1.000 (1 up, 1 down) |
| Rules 1+, plus escalate on error, empty, decline or invented value | 34 of 36 | 94.4% (81.9% to 98.5%) | 69% | $0.93 | 1.000 (1 up, 1 down) |
| Oracle: whichever model was right (upper bound, not achievable) | 36 of 36 | 100.0% | | | |

## How well the rules find the questions the local model gets wrong

Among the core and stress questions the local model failed, and the questions where the hosted model was right and the local one wrong.

| Threshold | Routed to hosted | Of those, local was wrong | Local-wrong questions caught | Local-wrong questions missed |
|---|---|---|---|---|
| 1+ families | 57 of 181 | 35 (61%) | 35 of 80 (44%) | 45 |
| 2+ families | 5 of 181 | 4 (80%) | 4 of 80 (5%) | 76 |

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

Hosted right, local wrong, and the rules kept it local (40):

- L02 (lookup): Which region is customer C-1010 in?
- A08 (filter_aggregate): How many employees work in the Support department?
- J05 (join): Which employees are assigned to open tickets of critical severity, which is severity level 1? Show their names.
- D04 (date_time): What is the average time to close a ticket, in hours, across the tickets that have been closed? Round to one decimal place.
- D06 (date_time): How many orders were placed on a Saturday or a Sunday?
- H03 (hierarchy): How many employees report to E-001, directly or through other managers?
- HJ01 (multi_join): Which carrier delivered the most orders to Platinum-tier customers? Show the carrier code and the number of delivered orders.
- HJ02 (multi_join): For each product category, how many units were taken out of stock at the Rotterdam Hub warehouse? Show the category code and the units as a positive number.
- HJ03 (multi_join): List the names of customers who used the promotion code WELCOME10 on an order that later had an approved refund request. Show each customer once.
- HJ04 (multi_join): Which employees approved refunds on orders placed by customers in the EU region? Show the employee name and how many refunds they approved there.
- HJ05 (multi_join): For delivered shipments only, what is the average number of days between the ship date and the delivery date for each warehouse? Show the warehouse name and the average rounded to one decimal.
- HJ08 (multi_join): Which suppliers are the primary supplier of at least one product that has never been ordered? Show the supplier names.
