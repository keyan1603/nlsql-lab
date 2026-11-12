# Hosted baseline against the local model

Local: XiYanSQL 7B at Q4_K_M (partial GPU offload on a 4 GB laptop GPU), plain prompt, greedy. Hosted: gemini-3.5-flash-lite, plain prompt, temperature 0. Same questions, same database, same grader. p is the exact two-sided sign test on the answerable questions only one of them got right.

| Question set | Local correct | Hosted correct | Local only | Hosted only | p | Local SQL errors | Hosted SQL errors | Declined correctly (local / hosted) | Invented answers (local / hosted) |
|---|---|---|---|---|---|---|---|---|---|
| core (55) | 42/49 (85.7%, 73 to 92%) | 45/49 (91.8%, 80 to 96%) | 3 | 6 | 0.508 | 0 | 1 | 1/6 / 5/6 | 4 / 1 |
| stress, first half (72) | 41/72 (56.9%, 45 to 67%) | 64/72 (88.9%, 79 to 94%) | 2 | 25 | 0.000 | 10 | 4 | n/a | n/a |
| stress, second half (54) | 30/54 (55.6%, 42 to 67%) | 46/54 (85.2%, 73 to 92%) | 3 | 19 | 0.001 | 7 | 5 | n/a | n/a |
| decline set (36) | 12/12 (100.0%, 75 to 100%) | 11/12 (91.7%, 64 to 98%) | 1 | 0 | 1.000 | 0 | 0 | 7/24 / 23/24 | 15 / 1 |

Pooled over the sets that finished: local 125/187 (66.8%), hosted 166/187 (88.8%). Mean seconds per question, local: 12.7. Hosted tokens: 816,188 in, 20,139 out over 217 questions (3,761 and 93 per question).

Hosted latency, measured on a 30-question sample after the client timer was fixed to exclude rate-limit waits (the full run's timer included them): mean 4.6 s, median 4.3 s, 95th percentile 8.9 s. The same 30 questions had the same outcome (right or wrong) in both hosted runs, although the SQL text differed in 18 of them: the hosted model is not bit-for-bit repeatable at temperature 0.
