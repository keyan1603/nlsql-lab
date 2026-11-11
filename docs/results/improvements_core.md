# Improvement round on the core set, XiYanSQL 7B at Q4_K_M

Each technique alone, against the plain prompt, on the same questions. Intervals are Wilson 95 percent. Gains and losses are questions the configuration got right that the baseline missed, and the reverse; p is the exact two-sided sign test on those. A configuration that has not finished all its questions is marked incomplete and left out of the comparison.

| Configuration | Correct | Accuracy | 95% interval | SQL errors | Model calls | Mean s/question | Gains | Losses | p |
|---|---|---|---|---|---|---|---|---|---|
| Plain prompt (baseline) | 42/49 | 85.7% | 73 to 93% | 0 | 49 | 7.7 | ref | ref | ref |
| Stack: 5 tables + retry on error | 43/49 | 87.8% | 76 to 94% | 0 | 49 | 6.5 | 1 | 0 | 1.000 |
| Stack + vote over 5 candidates | 43/49 | 87.8% | 76 to 94% | 0 | 248 | 28.9 | 1 | 0 | 1.000 |
