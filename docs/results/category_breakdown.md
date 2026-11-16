# Where the fine-tuned 7B loses: per category, with the training pairs each category had

Computed from saved single-run answers. Pool = core + hard + hard2 (answerable). Held-out is separate. 'Training pairs' counts the pairs (strict train + the hard continuation file) whose technique has the same name as the test category; a category with no matching technique shows 0.

## Pool (core, hard, hard2)

| Category | Questions | Tuned 7B | Prompt 7B | Tuned 3B | Hosted | Training pairs | Tuned 7B misses: wrong result / SQL error |
|---|---|---|---|---|---|---|---|
| multi_join | 14 | 9 | 10 | 10 | 13 | 131 | 5 / 0 |
| window | 14 | 7 | 7 | 4 | 11 | 292 | 6 / 1 |
| cte_multistep | 14 | 5 | 4 | 3 | 12 | 253 | 8 / 1 |
| correlated | 14 | 11 | 9 | 7 | 14 | 251 | 2 / 1 |
| set_ops | 14 | 9 | 8 | 4 | 14 | 164 | 3 / 2 |
| pivot | 14 | 10 | 12 | 10 | 12 | 91 | 3 / 1 |
| time_bucket | 14 | 9 | 9 | 7 | 9 | 204 | 4 / 1 |
| evidence | 14 | 5 | 8 | 2 | 11 | 171 | 9 / 0 |
| wide_schema | 14 | 14 | 14 | 13 | 14 | 0 | 0 / 0 |
| filter_aggregate | 8 | 7 | 8 | 8 | 7 | 0 | 1 / 0 |
| join | 8 | 7 | 7 | 5 | 8 | 0 | 1 / 0 |
| group_by | 8 | 8 | 8 | 7 | 6 | 0 | 0 / 0 |
| date_time | 6 | 4 | 5 | 3 | 6 | 109 | 2 / 0 |
| lookup | 5 | 5 | 5 | 5 | 5 | 0 | 0 / 0 |
| nulls_state | 4 | 4 | 4 | 3 | 4 | 0 | 0 / 0 |
| fanout_trap | 4 | 3 | 2 | 4 | 3 | 0 | 1 / 0 |
| hierarchy | 3 | 3 | 2 | 1 | 3 | 132 | 0 / 0 |
| policy_dates | 3 | 2 | 2 | 2 | 3 | 0 | 1 / 0 |

## Held-out (52)

| Category | Questions | Tuned 7B | Prompt 7B | Tuned 3B | Hosted | Training pairs | Tuned 7B misses: wrong result / SQL error |
|---|---|---|---|---|---|---|---|
| routine | 12 | 12 | 12 | 10 | 10 | 0 | 0 / 0 |
| window | 4 | 1 | 2 | 1 | 2 | 292 | 3 / 0 |
| time_bucket | 4 | 3 | 4 | 2 | 3 | 204 | 1 / 0 |
| evidence | 4 | 2 | 1 | 1 | 4 | 171 | 2 / 0 |
| control | 4 | 2 | 3 | 3 | 3 | 0 | 2 / 0 |
| cte_multistep | 3 | 0 | 0 | 0 | 1 | 253 | 2 / 1 |
| set_ops | 3 | 1 | 1 | 1 | 3 | 164 | 1 / 1 |
| correlated | 3 | 2 | 2 | 1 | 3 | 251 | 1 / 0 |
| wide_schema | 3 | 2 | 2 | 1 | 3 | 0 | 0 / 1 |

