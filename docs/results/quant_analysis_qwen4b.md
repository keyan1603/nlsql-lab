# Quantization against difficulty: Qwen3-4B-Instruct general model, 6 levels

Accuracy is the share of answerable questions whose query returned the right result. Intervals are Wilson 95 percent. Gains and losses are questions a level got right that Q8_0 got wrong, and the reverse; p is the exact two-sided sign test on those discordant questions (McNemar's exact test). A small p says the flips went one way more than chance would.

## Hard set, first half (72 questions, 22 tables)

| Level | File GB | Correct | Accuracy | 95% interval | SQL errors | Gains vs Q8_0 | Losses vs Q8_0 | Net | p (sign test) |
|---|---|---|---|---|---|---|---|---|---|
| Q8_0 | 4.28 | 39/72 | 54.2% | 43 to 65% | 13 | 0 | 0 | +0 | 1.000 |
| Q6_K | 3.31 | 36/72 | 50.0% | 39 to 61% | 12 | 2 | 5 | -3 | 0.453 |
| Q4_K_M | 2.50 | 37/72 | 51.4% | 40 to 63% | 12 | 4 | 6 | -2 | 0.754 |
| Q3_K_M | 2.08 | 24/72 | 33.3% | 24 to 45% | 30 | 5 | 20 | -15 | 0.004 |
| Q3_K_S | 1.89 | 27/72 | 37.5% | 27 to 49% | 20 | 10 | 22 | -12 | 0.050 |
| Q2_K | 1.67 | 1/72 | 1.4% | 0 to 7% | 15 | 0 | 38 | -38 | 0.000 |

## Hard set, second half (54 questions, 22 tables)

| Level | File GB | Correct | Accuracy | 95% interval | SQL errors | Gains vs Q8_0 | Losses vs Q8_0 | Net | p (sign test) |
|---|---|---|---|---|---|---|---|---|---|
| Q8_0 | 4.28 | 30/54 | 55.6% | 42 to 68% | 12 | 0 | 0 | +0 | 1.000 |
| Q6_K | 3.31 | 29/54 | 53.7% | 41 to 66% | 13 | 3 | 4 | -1 | 1.000 |
| Q4_K_M | 2.50 | 28/54 | 51.9% | 39 to 65% | 12 | 6 | 8 | -2 | 0.791 |
| Q3_K_M | 2.08 | 13/54 | 24.1% | 15 to 37% | 19 | 1 | 18 | -17 | 0.000 |
| Q3_K_S | 1.89 | 26/54 | 48.1% | 35 to 61% | 15 | 7 | 11 | -4 | 0.481 |
| Q2_K | 1.67 | 0/54 | 0.0% | 0 to 7% | 8 | 0 | 30 | -30 | 0.000 |

## Hard set, both halves together (126 questions)

| Level | File GB | Correct | Accuracy | 95% interval | SQL errors | Gains vs Q8_0 | Losses vs Q8_0 | Net | p (sign test) |
|---|---|---|---|---|---|---|---|---|---|
| Q8_0 | 4.28 | 69/126 | 54.8% | 46 to 63% | 25 | 0 | 0 | +0 | 1.000 |
| Q6_K | 3.31 | 65/126 | 51.6% | 43 to 60% | 25 | 5 | 9 | -4 | 0.424 |
| Q4_K_M | 2.50 | 65/126 | 51.6% | 43 to 60% | 24 | 10 | 14 | -4 | 0.541 |
| Q3_K_M | 2.08 | 37/126 | 29.4% | 22 to 38% | 49 | 6 | 38 | -32 | 0.000 |
| Q3_K_S | 1.89 | 53/126 | 42.1% | 34 to 51% | 35 | 17 | 33 | -16 | 0.033 |
| Q2_K | 1.67 | 1/126 | 0.8% | 0 to 4% | 23 | 0 | 68 | -68 | 0.000 |

## Per category, hard set (correct / questions)

| Category | Q8_0 | Q6_K | Q4_K_M | Q3_K_M | Q3_K_S | Q2_K |
|---|---|---|---|---|---|---|
| correlated | 4/8 | 5/8 | 5/8 | 3/8 | 4/8 | 0/8 |
| cte_multistep | 3/8 | 2/8 | 2/8 | 2/8 | 0/8 | 0/8 |
| evidence | 2/8 | 1/8 | 2/8 | 2/8 | 2/8 | 0/8 |
| multi_join | 4/8 | 4/8 | 5/8 | 3/8 | 3/8 | 1/8 |
| pivot | 5/8 | 5/8 | 5/8 | 4/8 | 4/8 | 0/8 |
| set_ops | 5/8 | 4/8 | 5/8 | 2/8 | 1/8 | 0/8 |
| time_bucket | 5/8 | 4/8 | 2/8 | 2/8 | 4/8 | 0/8 |
| wide_schema | 8/8 | 8/8 | 7/8 | 5/8 | 6/8 | 0/8 |
| window | 3/8 | 3/8 | 4/8 | 1/8 | 3/8 | 0/8 |

## Per category, hardall set (correct / questions)

| Category | Q8_0 | Q6_K | Q4_K_M | Q3_K_M | Q3_K_S | Q2_K |
|---|---|---|---|---|---|---|
| correlated | 9/14 | 9/14 | 7/14 | 6/14 | 8/14 | 0/14 |
| cte_multistep | 5/14 | 3/14 | 2/14 | 2/14 | 0/14 | 0/14 |
| evidence | 6/14 | 4/14 | 8/14 | 3/14 | 5/14 | 0/14 |
| multi_join | 7/14 | 7/14 | 8/14 | 3/14 | 6/14 | 1/14 |
| pivot | 9/14 | 8/14 | 8/14 | 6/14 | 6/14 | 0/14 |
| set_ops | 9/14 | 8/14 | 10/14 | 3/14 | 4/14 | 0/14 |
| time_bucket | 6/14 | 6/14 | 4/14 | 3/14 | 7/14 | 0/14 |
| wide_schema | 14/14 | 14/14 | 13/14 | 10/14 | 11/14 | 0/14 |
| window | 4/14 | 6/14 | 5/14 | 1/14 | 6/14 | 0/14 |
