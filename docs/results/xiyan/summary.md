# XiYan 7B: final configuration against the baselines

Single runs, greedy decoding. Intervals are Wilson 95%. Declines: a question that should be declined counts when the reply is the right kind of decline (`-- UNANSWERABLE` or `-- CLARIFY`). Wrongly refused: an answerable question that got a decline. Latency is mean seconds per question (LM Studio on a 4 GB GPU for the local rows; the 3B row was timed on a different server and is not comparable).

## core (49 answerable, 6 to decline)

| System | Answerable correct | 95% interval | Declined correctly | Wrongly refused | Wrongly answered | vs XiYan plain (gains, losses, p) | Mean s |
|---|---|---|---|---|---|---|---|
| XiYan 7B Q4_K_M, plain prompt | 42 of 49 (85.7%) | 73.3% to 92.9% | 1 of 6 | 0 | 4 | reference | 7.8 |
| XiYan 7B, final (tuned prompt + 4 decline examples + retry 2) | 43 of 49 (87.8%) | 75.8% to 94.3% | 1 of 6 | 0 | 5 | 2, 1, 1.00 | 8.1 |
| Tuned Qwen2.5-Coder-3B (run 6 + retry 2) | 38 of 49 (77.6%) | 64.1% to 87.0% | 6 of 6 | 0 | 0 | 8, 7, 1.00 | 11.5 |
| gemini-3.5-flash-lite (hosted, plain prompt) | 45 of 49 (91.8%) | 80.8% to 96.8% | 5 of 6 | 0 | 1 | 10, 3, 0.09 | 4.5 |

## hard (72 answerable, 0 to decline)

| System | Answerable correct | 95% interval | Declined correctly | Wrongly refused | Wrongly answered | vs XiYan plain (gains, losses, p) | Mean s |
|---|---|---|---|---|---|---|---|
| XiYan 7B Q4_K_M, plain prompt | 41 of 72 (56.9%) | 45.4% to 67.7% | 0 of 0 | 0 | 0 | reference | 17.5 |
| XiYan 7B, final (tuned prompt + 4 decline examples + retry 2) | 46 of 72 (63.9%) | 52.4% to 74.0% | 0 of 0 | 0 | 0 | 10, 5, 0.30 | 15.2 |
| Tuned Qwen2.5-Coder-3B (run 6 + retry 2) | 29 of 72 (40.3%) | 29.7% to 51.8% | 0 of 0 | 2 | 0 | 4, 16, 0.01 | 34.4 |
| gemini-3.5-flash-lite (hosted, plain prompt) | 64 of 72 (88.9%) | 79.6% to 94.3% | 0 of 0 | 0 | 0 | 25, 2, 0.00 | 5.1 |

## hard2 (54 answerable, 0 to decline)

| System | Answerable correct | 95% interval | Declined correctly | Wrongly refused | Wrongly answered | vs XiYan plain (gains, losses, p) | Mean s |
|---|---|---|---|---|---|---|---|
| XiYan 7B Q4_K_M, plain prompt | 30 of 54 (55.6%) | 42.4% to 68.0% | 0 of 0 | 0 | 0 | reference | 16.3 |
| XiYan 7B, final (tuned prompt + 4 decline examples + retry 2) | 35 of 54 (64.8%) | 51.5% to 76.2% | 0 of 0 | 0 | 0 | 6, 1, 0.12 | 14.9 |
| Tuned Qwen2.5-Coder-3B (run 6 + retry 2) | 31 of 54 (57.4%) | 44.2% to 69.7% | 0 of 0 | 3 | 0 | 7, 6, 1.00 | 34.1 |
| gemini-3.5-flash-lite (hosted, plain prompt) | 46 of 54 (85.2%) | 73.4% to 92.3% | 0 of 0 | 0 | 0 | 19, 3, 0.00 | 6.1 |

## decline (12 answerable, 24 to decline)

| System | Answerable correct | 95% interval | Declined correctly | Wrongly refused | Wrongly answered | vs XiYan plain (gains, losses, p) | Mean s |
|---|---|---|---|---|---|---|---|
| XiYan 7B Q4_K_M, plain prompt | 12 of 12 (100.0%) | 75.7% to 100.0% | 7 of 24 | 0 | 15 | reference | 4.8 |
| XiYan 7B, final (tuned prompt + 4 decline examples + retry 2) | 11 of 12 (91.7%) | 64.6% to 98.5% | 4 of 24 | 0 | 20 | 1, 5, 0.22 | 9.1 |
| Tuned Qwen2.5-Coder-3B (run 6 + retry 2) | 12 of 12 (100.0%) | 75.7% to 100.0% | 23 of 24 | 0 | 0 | 17, 1, 0.00 | 10.1 |
| gemini-3.5-flash-lite (hosted, plain prompt) | 11 of 12 (91.7%) | 64.6% to 98.5% | 23 of 24 | 0 | 1 | 16, 1, 0.00 | 6.1 |

