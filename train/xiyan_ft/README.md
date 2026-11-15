# XiYanSQL-QwenCoder-7B QLoRA package (NOT RUN), aimed at hard-style questions and declines

Status: prepared, not executed on a 7B model. `train_qlora_7b.py` is derived from `train/train_lora.py`, which trained the 3B models in this repo. Smoke test that was run: the script trained the 3B base (`train/base3b`) on 48 examples for one epoch on this machine's RTX 2050 (bf16 path, 214 s, peak 3.57 GB, loss logged, checkpoints and validation written). Not exercised: the fp16 plus GradScaler path used on a T4, `--resume`, and anything at 7B size. Expect to debug once on the free GPU.

## Why this is a package and not a local run

The laptop GPU has 4 GB. Estimate for 4-bit QLoRA of a 7.6B Qwen2.5-Coder model (arithmetic, not measured):

| Part | 3B run (measured peak 3.73 GB) | 7B (estimate) |
|---|---|---|
| Embedding + output matrices (bf16, not quantised by bitsandbytes; 7B has them untied) | 0.6 GB (tied, one copy) | about 2.2 GB (two copies of 152k x 3584) |
| Transformer body in NF4 | about 1.5 GB | about 3.4 GB |
| LoRA r32 weights, gradients, Adam state | small | about 1 GB |
| Activations, CUDA context, fragmentation | about 1.5 GB | at least 1.5 GB |
| Total | 3.73 GB (measured) | about 8 GB |

The weights alone (about 5.6 GB) are larger than the card. Verdict: infeasible on 4 GB, even with a micro-batch of 1. Paging weights to system RAM would make a step take minutes. An 8 to 12 GB card or a free cloud T4 (15 GB) is the realistic route.

## What is in the package

Run `python train/xiyan_ft/pack.py` (from the lab repo) to build `xiyan_ft_package.zip` (about 0.7 MB zipped, not committed). Counts are in `package_report.json`.

- `train_qlora_7b.py`: training script. bf16 where the GPU supports it, fp16 plus GradScaler on a T4 or P100. Saves an adapter after each epoch and every 20 steps, and can `--resume`.
- Data, chat format built with `nlsql.prompts.tuned_system` (compact rules plus the five most likely tables, about 430 tokens). Token counts use the Qwen2.5 tokenizer, which XiYan shares. Strict mode (default, see hygiene) gives:

| File | Pairs | of which declines | Tokens | Use |
|---|---|---|---|---|
| `data/train.jsonl` | 1,733 | 329 | 1.48 M | pass 1: the general pool |
| `data/hard_train.jsonl` | 943 | 169 | 0.79 M | pass 2: hard-question pairs plus replay |
| `data/val.jsonl`, `data/hard_val.jsonl` | 133, 65 | 39, 5 | 0.11 M, 0.06 M | validation loss per pass |
| `data/cont2_train.jsonl`, `data/cont2_val.jsonl` | 598, 175 | 125, 48 | 0.49 M, 0.14 M | optional, the 3B's terse-question pass; 96 of its pairs are already replayed inside `hard_train.jsonl` |

`hard_train.jsonl` by source (strict mode): 636 new teacher-written, database-verified hard pairs; 150 replayed decline and clarify pairs from `train.jsonl`; 96 replayed terse pairs from `cont2_train.jsonl` (answers and declines mixed); 61 replayed easy answerable pairs. The replay is there so pass 2 does not unlearn declining or short questions.

The 636 new pairs by failure family (the families are those in `nlsql/router.py`; the teacher was asked for one technique per request, so the technique count is exact, while the router-regex column shows how many of the questions also carry the surface cues the router looks for):

| Family (technique asked for) | New pairs | Matching the router regex for that family |
|---|---|---|
| window | 134 | 49 |
| time_bucket | 110 | 37 |
| defined_term (a term defined in the question) | 74 | 42 |
| multi_step (WITH-clause, several steps) | 119 | 19 |
| set_logic | 86 | 21 |
| correlated | 113 | 19 |

459 of the 636 match no router regex at all. The regexes were written for the stress questions' phrasing, so a low match rate says the teacher words things differently, not that the pairs are off target. The failures being aimed at (final prompt-only run): hard 26 of 72 wrong (cte_multistep 6 of 8, set_ops 4, window 4, correlated 4, evidence 4, multi_join 3, time_bucket 1) and hard2 19 of 54 wrong (cte_multistep 4 of 6, time_bucket 4, window 3, set_ops 2, evidence 2, pivot 2, correlated 1, multi_join 1). 21 of the 26 and 16 of the 19 were wrong results, not SQL errors, so this is a reasoning gap that 636 pairs may only partly close.

How the new pairs were made (`scripts/make_hard_data.py`, files `train/data/hard_*.jsonl`): the hosted teacher (gemini-3.5-flash-lite, free tier, 58 generation and 52 answer requests) saw only the synthetic schema, never a test or hard-set question or failure text. It wrote candidate pairs for six hard techniques x five business areas x two rounds. After the query had to run and return rows and duplicates of the existing pool were removed, 1,233 candidates remained. A blind second teacher answer had to return the same result (122 disagreed, 6 declined). One pair was dropped as a test look-alike (LeakFilter), and 428 were dropped because the query filters on a (table, column, value) cell that a test gold query filters on (`filter_cells`). 676 remained: 636 to training, 40 to validation. The existing `train.jsonl`, `val.jsonl` and `candidates.jsonl` were not changed.

The data uses our compact "tuned" prompt, not XiYan's M-Schema. M-Schema scored lower on dev and dev2 without training, so it was not used.

## Test hygiene

- Every pair passed `nlsql.traindata.LeakFilter` against the core, hard, hard2 and decline questions (question wording overlap of 60% or more, exact question, or the same gold query). `pack.py` re-checks all files and reported 0 overlapping pairs.
- Held-out cells. The new hard pairs were built with the held-out-cell rule. The older files predate it for answers: 850 of 2,254 answer pairs in `train.jsonl`, 145 of 618 in `cont2_train.jsonl` and 63 replayed ones in the new file filter on a (table, column, value) cell that some test gold query also filters on. A cell overlap is weaker than a question overlap (the model sees a code value, not a test question) but it is not what the rule promises. `pack.py` therefore runs in strict mode by default and drops every such answer pair from the copies inside the zip (counts in `package_report.json`; the files in `train/data` are untouched). `--lenient` keeps them, which matches how the 3B was trained. The strict data is smaller than what the 3B used, so a 7B result is not a like-for-like comparison with the 3B.
- The dev and dev2 sets are held out of training by the same rules and are the only sets to use for choosing an epoch.
- Teacher labels are synthetic, written on the synthetic schema, with no real personal data.

## Exact steps (Kaggle, free)

1. New notebook, accelerator "GPU T4 x2" (use one GPU; the script uses cuda:0 only) or P100. Turn Internet on. Add the zip as a dataset or upload and unzip it.
2. `pip install -q -U transformers peft bitsandbytes accelerate` (the repo's training venv used transformers 5.22, peft 0.21, bitsandbytes 0.50, torch 2.6; other versions are untested).
3. Pass 1: `python train_qlora_7b.py --train data/train.jsonl --val data/val.jsonl --out out/run1 --epochs 1`
4. Pass 2 (hard pairs plus replay): `python train_qlora_7b.py --init out/run1/epoch1 --train data/hard_train.jsonl --val data/hard_val.jsonl --out out/run2 --epochs 2 --lr 1e-4`
5. If the session dies, add `--resume out/run1/ckpt_stepN` to the same command (Adam state restarts).
6. Download `out/run2/epoch1` and `out/run2/epoch2` (LoRA adapters, about 0.3 GB each at rank 32). Pick the epoch on dev and dev2 score, never on hard, hard2 or decline.

Expected runtime (estimate, not measured; the only measured number is 139 tokens per second for the 3B on this machine's 4 GB card): a 7B on a T4 at roughly 400 to 800 tokens per second. Pass 1 is 1.48 M tokens, about 0.5 to 1 hour. Pass 2 is 0.79 M tokens x 2 epochs, about 0.5 to 1 hour. Downloading 15 GB of weights takes 10 to 20 minutes. So about 1.5 to 2.5 hours of a 12-hour Kaggle session. Free limits as I understand them (check current terms): Kaggle about 30 GPU hours a week, 12 hours per session; Colab free T4 is shorter and not guaranteed. Out of memory: lower `--tok-budget` (4800) or `--micro`.

## Checks on return

1. `venv-train python train/merge_and_convert.py --base <XiYan 7B HF folder> --adapter out/run2/epoch1 --name xiyan7b-ft --outtype q8_0`, then quantise to Q4_K_M with llama.cpp and load in LM Studio. The adapter was trained on 4-bit weights, so score the merged file rather than assume it works.
2. Score on dev and dev2 first (choose the epoch there), then once each on hard, hard2, core and decline with the same settings as the prompt-only baseline: `scripts/run_eval.py --prompt tuned --decline-shots 4 --retry 2 --max-tokens 1024` (labels like `xiyan7b-ft-hard`). Also score the tuned prompt without the examples, since a fine-tuned model may not need them.
3. Compare with `docs/results/xiyan/summary.md`. Single runs differ by up to about 3 questions.

## Pre-registered win bar (written before any training)

The 7B fine-tune counts as a win only if, scored with the settings above, it:

1. beats **46 of 72 on hard** and **35 of 54 on hard2** (the final prompt-only configuration). "Beats" means a strictly higher count; a gain of 3 questions or fewer is to be reported as not distinguishable from noise;
2. scores **43 of 49 or more on core** (no regression on the answerable core questions);
3. on the decline set, declines **no fewer than 4 of 24** (also report the 12 controls). A separate 3B decline gate already handles declines in the planned system, so the 7B only has to not get worse here.

All three must hold. If hard and hard2 each improve by 3 questions or fewer, the answer is "no measurable gain" and the fine-tune is not worth deploying. These numbers are fixed here before any training; the epoch is chosen on dev and dev2 only.

## What would have to be true for this to be worth running

- The planned system already has a decline gate, so the fine-tune is justified only by answering better on hard-style questions. The prompt-only 7B reaches 46 of 72 on hard and 35 of 54 on hard2; the hosted model reaches 64 and 46.
- Do not expect a large gain. The tuned 3B scored 29 of 72 on hard against 41 for plain XiYan 7B, so the earlier fine-tune taught conventions and declining, not multi-step reasoning. This package adds 636 hard-question pairs, the first test of whether targeted pairs help. With most hard failures being wrong results rather than errors, a partial gain is the likely outcome.
- Someone is willing to spend a free-GPU session and about 2 hours of scoring on this machine.
