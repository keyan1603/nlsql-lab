# Quantization sweep: XiYanSQL-QwenCoder-7B-2504

Eleven quantizations of one model (Apache-2.0, `mradermacher/XiYanSQL-QwenCoder-7B-2504-GGUF`), the same 55 questions, the same prompt, greedy decoding, the same LM Studio settings for every level (55 percent of the layers on the GPU, 8192-token context, llama.cpp CUDA 12 runtime). Machine: Intel i5-1240P, 15.7 GB RAM, NVIDIA RTX 2050 with 4 GB. Raw data: `quant_sweep.json`, `models/xiyan7b-*.jsonl` and `.summary.json`.

| Level | File | Correct (of 49) | Declined (of 6) | SQL errors | Mean s/question | p95 s | GPU peak MiB | Process peak MiB | Same pass/fail as Q8_0 (of 55) | Questions that flipped |
|---|---|---|---|---|---|---|---|---|---|---|
| Q2_K | 3.02 GB | 40 (81.6%) | 0 | 0 | 4.8 | 12.4 | 2,159 | 3,283 | 52 | G04, H01, U01 |
| Q3_K_S | 3.49 GB | 42 (85.7%) | 0 | 0 | 8.6 | 14.2 | 2,377 | 3,720 | 50 | A06, J01, G04, P03, U01 |
| Q3_K_M | 3.81 GB | 42 (85.7%) | 1 | 0 | 8.6 | 13.1 | 2,559 | 4,039 | 53 | G04, P03 |
| Q3_K_L | 4.09 GB | 41 (83.7%) | 0 | 0 | 6.8 | 13.5 | 2,685 | 4,307 | 53 | G04, U01 |
| IQ4_XS | 4.25 GB | 41 (83.7%) | 0 | 0 | 6.3 | 12.8 | 2,751 | 4,460 | 53 | N03, U01 |
| Q4_K_S | 4.46 GB | 41 (83.7%) | 1 | 0 | 8.4 | 14.0 | 2,853 | 4,650 | 54 | N03 |
| **Q4_K_M** | 4.68 GB | 42 (85.7%) | 1 | 0 | 7.8 | 13.2 | 2,989 | 4,866 | 55 | none |
| Q5_K_S | 5.32 GB | 42 (85.7%) | 1 | 0 | 7.0 | 14.2 | 3,225 | 5,471 | 55 | none |
| Q5_K_M | 5.45 GB | 42 (85.7%) | 1 | 0 | 8.7 | 17.6 | 3,295 | 5,604 | 55 | none |
| Q6_K | 6.25 GB | 42 (85.7%) | 1 | 0 | 10.3 | 18.6 | 3,677 | 6,369 | 55 | none |
| Q8_0 (reference) | 8.10 GB | 42 (85.7%) | 1 | 0 | 13.0 | 23.7 | 3,899 | 6,752 | 55 | none |

## What it shows

- **Size cost almost nothing from 8-bit down to 4-bit.** Q4_K_M is 42 percent smaller than Q8_0 and every one of the 55 questions has the same pass or fail outcome. Q5 and Q6 are the same. Nothing is gained above 4-bit on this task.
- **Below 4-bit, accuracy moves by a question or two.** Q3_K_M is 53 percent smaller and flips 2 questions (the same 42 correct in total); Q2_K is 63 percent smaller, loses 2 of 49 answerable questions and flips 3 of 55 in all.
- **Memory and time scale with size, because of the partial GPU offload.** Q8_0 uses 3.9 GiB of the 4 GiB GPU and 6.6 GiB of process memory and takes 13.0 s a question; Q4_K_M uses 3.0 GiB and 4.8 GiB and takes 7.8 s; Q2_K uses 2.1 GiB and 3.2 GiB and takes 4.8 s. A smaller file puts more layers on the GPU and moves less data through memory, which is where the time goes.
- **What the 2-bit level breaks.** In Q2_K the model wrote `AVG(line_no)` over all lines instead of averaging a per-order count (G04), returned the manager's id instead of the manager's name (H01), and answered the unanswerable satisfaction-score question with `sev_lvl AS customer_satisfaction_score` where the 8-bit model refused (U01). They are the kind of mistakes a smaller model makes, not formatting damage.

## Read this before quoting the table

- **The differences are one to three questions out of 55.** Two runs of the same Q4_K_M file with the same settings produced different text on 4 of 55 questions (D03, P01, U01, U03) with identical pass and fail outcomes on all 55, and a third run was identical to the second. The 7B model, with part of it on the CPU, is not perfectly repeatable, so a one-question difference between two levels is not a finding.
- **The levels are not independent samples of one thing.** Q3_K_S flips 5 questions against Q8_0 (it gains J01 and P03, and loses A06, G04 and U01) and Q3_K_M flips 2 (gains P03, loses G04), yet both score 42 correct; the total hides the churn. The column of flipped questions is the honest comparison.
- **Timings are noisy.** Several levels ran while large downloads were using the network and some CPU, and the order of speeds among the 3- and 4-bit levels (Q3_K_S 8.6 s but IQ4_XS 6.3 s) does not follow file size. The trend from 8-bit to 2-bit is real; the ordering inside the middle is not.
- **The GPU figures include whatever the desktop was using** (roughly 0.5 to 0.7 GiB on this machine), so the real model share is smaller than the table shows.
- **One model, one task, one machine, 55 questions I wrote.** A different model, a harder schema or another kind of question can be more sensitive to compression than this one.
