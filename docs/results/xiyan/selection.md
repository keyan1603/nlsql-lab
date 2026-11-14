# XiYan selection runs (dev, dev2, hard only)

Choosing rule, fixed before round 2: highest total of answerable-correct (dev 18, dev2 14, hard 72) plus declines-correct (dev 12). Differences of 3 questions or fewer are not distinguishable. hard2 and the decline set were not used.

| Configuration | dev answerable (of 18) | dev declines (of 12) | dev2 (of 14) | hard (of 72) | Total answerable (of 104) | Total with declines |
|---|---|---|---|---|---|---|
| XiYan plain prompt | 16 | 8 | 13 | 41 | 70 | 78 |
| mschema prompt | 16 | 5 | 12 | not run | n/a | n/a |
| tuned prompt | 17 | 6 | 14 | 36 | 67 | 73 |
| tuned + dialect rules | 17 | 8 | 14 | 39 | 70 | 78 |
| tuned + 4 decline examples (d4) | 17 | 5 | 12 | 45 | 74 | 79 |
| tuned + dialect + d4 | 17 | 5 | 13 | 43 | 73 | 78 |
| tuned + dialect + d6 | 17 | 6 | 10 | 38 | 65 | 71 |
| tuned + dialect + d6 + 2 answer examples | 17 | 9 | 12 | 40 | 69 | 78 |
| tuned + d4 + retry 2 (FINAL) | 17 | 5 | 13 | 46 | 76 | 81 |
| tuned + d4 + decline guard (rejected) | 14 | 9 | 10 | 38 | 62 | 71 |

Guard: with the decline guard the dev declines rose from 5 to 9 of 12 but 12 answerable questions were lost (74 down to 62) across the three sets (over-declining), so it was rejected.
