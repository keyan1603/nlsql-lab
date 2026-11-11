# Improvement round on the stress set, XiYanSQL 7B at Q4_K_M

Each technique alone, against the plain prompt, on the same questions. Intervals are Wilson 95 percent. Gains and losses are questions the configuration got right that the baseline missed, and the reverse; p is the exact two-sided sign test on those. A configuration that has not finished all its questions is marked incomplete and left out of the comparison.

| Configuration | Correct | Accuracy | 95% interval | SQL errors | Model calls | Mean s/question | Gains | Losses | p |
|---|---|---|---|---|---|---|---|---|---|
| Plain prompt (baseline) | 71/126 | 56.3% | 48 to 65% | 17 | 126 | 17.0 | ref | ref | ref |
| M-Schema layout with example values | 67/126 | 53.2% | 44 to 62% | 24 | 126 | 17.7 | 2 | 6 | 0.289 |
| Show only 5 likely tables | 76/126 | 60.3% | 52 to 68% | 12 | 126 | 13.0 | 10 | 5 | 0.302 |
| 3 worked examples | 64/126 | 50.8% | 42 to 59% | 22 | 126 | 15.8 | 8 | 15 | 0.210 |
| Retry on database error (up to 2) | 74/126 | 58.7% | 50 to 67% | 7 | 153 | 18.4 | 4 | 1 | 0.375 |
| Retry on error or empty result (up to 2) | 74/126 | 58.7% | 50 to 67% | 7 | 159 | 19.1 | 4 | 1 | 0.375 |
| Stack: 5 tables + retry on error | 77/126 | 61.1% | 52 to 69% | 8 | 149 | 15.1 | 11 | 5 | 0.210 |
| Stack + vote over 5 candidates | 78/126 | 61.9% | 53 to 70% | 2 | 737 | 70.4 | 11 | 4 | 0.118 |
