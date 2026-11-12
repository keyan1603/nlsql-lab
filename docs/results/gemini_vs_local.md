# Hosted baseline against the local model

Local: XiYanSQL 7B at Q4_K_M (partial GPU offload on a 4 GB laptop GPU), plain prompt, greedy. Hosted: gemini-3.5-flash-lite, plain prompt, temperature 0. Same questions, same database, same grader. p is the exact two-sided sign test on the answerable questions only one of them got right.

| Question set | Local correct | Hosted correct | Local only | Hosted only | p | Local SQL errors | Hosted SQL errors | Declined correctly (local / hosted) | Invented answers (local / hosted) |
|---|---|---|---|---|---|---|---|---|---|
| core (55) | incomplete (0/55 hosted answers) | | | | | | | | |
| stress, first half (72) | incomplete (0/72 hosted answers) | | | | | | | | |
| stress, second half (54) | incomplete (0/54 hosted answers) | | | | | | | | |
| decline set (36) | incomplete (0/36 hosted answers) | | | | | | | | |
