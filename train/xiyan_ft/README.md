# XiYanSQL-QwenCoder-7B QLoRA package (NOT RUN)

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

Run `python train/xiyan_ft/pack.py` (from the lab repo) to build `xiyan_ft_package.zip` (about 0.7 MB zipped, not committed):

- `train_qlora_7b.py`: training script. bf16 where the GPU supports it, fp16 plus GradScaler on a T4 or P100. Saves an adapter after each epoch and every 20 steps, and can `--resume`.
- `data/train.jsonl` (2,583 pairs, 2.21 M tokens, 0.15 M reply tokens), `data/val.jsonl` (195), `data/cont2_train.jsonl` (743 pairs, 0.62 M tokens), `data/cont2_val.jsonl` (237). Chat format, built with `nlsql.prompts.tuned_system` (compact rules plus the five most likely tables, about 430 tokens). Token counts use the Qwen2.5 tokenizer, which XiYan shares.
- `pack.py` refuses to build the zip if any training pair overlaps a test question.

The data uses our compact "tuned" prompt, not XiYan's M-Schema. See the main report for which prompt scored better without training; if M-Schema had won, the data would need regenerating with `--prompt mschema`-style system messages, which this package does not do.

## Test hygiene

- Training pairs were filtered with `nlsql.traindata.LeakFilter` against the core, hard, hard2 and decline questions (question wording overlap of 60% or more, exact question, or the same gold query is dropped). `pack.py` re-checks this and reported 0 overlapping pairs when run.
- The terse-question pairs (cont data) avoid every (table, column, value) cell that any test gold query filters on (`scripts/make_terse_data.py test_cells`, 80 cells).
- The dev and dev2 sets are held out of training by the same rules and are the only sets to use for choosing an epoch.
- Hosted-model (teacher) labels are synthetic, generated on the synthetic schema, with no real personal data.

## Exact steps (Kaggle, free)

1. New notebook, accelerator "GPU T4 x2" (use one GPU; the script uses cuda:0 only) or P100. Turn Internet on. Add the zip as a dataset or upload and unzip it.
2. `pip install -q -U transformers peft bitsandbytes accelerate` (the repo's training venv used transformers 5.22, peft 0.21, bitsandbytes 0.50, torch 2.6; other versions are untested).
3. Pass 1: `python train_qlora_7b.py --train data/train.jsonl --val data/val.jsonl --out out/run1 --epochs 1`
4. Pass 2 (the repo's 3B recipe did a second, short pass on the terse data): `python train_qlora_7b.py --init out/run1/epoch1 --train data/cont2_train.jsonl --val data/cont2_val.jsonl --out out/run2 --epochs 1 --lr 1e-4`
5. If the session dies, add `--resume out/run1/ckpt_stepN` to the same command (Adam state restarts).
6. Download `out/run2/epoch1` (the LoRA adapter, about 0.3 GB at rank 32).

Expected runtime (estimate, not measured): 7B on a T4 at roughly 400 to 800 tokens per second means about 1 to 2 hours for pass 1 and 20 to 30 minutes for pass 2, plus 10 to 20 minutes to download 15 GB of weights. Free limits as I understand them (check current terms): Kaggle about 30 GPU hours a week, 12 hours per session; Colab free T4 is shorter and not guaranteed. Out-of-memory: lower `--tok-budget` (4800) or `--micro`.

## Checks on return

1. `venv-train python train/merge_and_convert.py --base <XiYan 7B HF folder> --adapter out/run2/epoch1 --name xiyan7b-ft --outtype q8_0`, then quantise to Q4_K_M with llama.cpp and load in LM Studio. The adapter was trained on 4-bit weights, so score the merged file rather than assume it works.
2. Score with `scripts/run_eval.py --prompt tuned --max-tokens 1024` on dev, dev2 (choose here), then hard, hard2, decline and core once.
3. Compare with the untuned XiYan configuration in `docs/results/xiyan/` and with the tuned 3B. Single runs differ by up to about 3 questions.

## What would have to be true for this to be worth running

- The prompt-only XiYan configuration still cannot decline (4 of 24 on the decline set, against 23 of 24 for the tuned 3B and the hosted model), and a guard or router cannot cover that cheaply. Fine-tuning is the one lever here that has produced reliable declining (the tuned 3B reached 23 of 24).
- Do not expect fine-tuning to close the hard-set gap. The tuned 3B scored 29 of 72 on hard against 41 for plain XiYan 7B and 64 for the hosted model, so on this data fine-tuning taught conventions and declining, not multi-step reasoning. Hoped-for result for a 7B tune: hold XiYan hard-set accuracy (41 to 46 of 72 depending on prompt) while gaining the declines.
- Someone is willing to spend a free-GPU session and 2 to 3 hours of scoring on this machine.
