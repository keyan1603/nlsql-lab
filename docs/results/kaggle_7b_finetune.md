# Fine-tuned XiYan 7B (Kaggle T4 QLoRA) against the pre-registered win bar

Two-stage QLoRA on a free Kaggle T4 (80.7M trainable parameters, 9.4 GB peak; pass 1 5,315 s, val_loss 0.2564; pass 2 two epochs, val_loss 0.1125 then 0.1115). Epoch 2 was merged and scored once, as a Q8_0 GGUF (the prompt-only baseline is Q4_K_M, which slightly favours the fine-tune), with the same settings as the baseline: tuned prompt, 4 decline examples, retry 2. The epoch was not chosen on the dev sets; only epoch 2 was merged.

| Pre-registered condition | Required | Result | Met |
|---|---|---|---|
| hard | more than 46 of 72 | 44 | no |
| hard2 | more than 35 of 54 | 35 | no (not strictly more) |
| core | 43 of 49 or more | 43 | yes |
| decline set | at least 4 of 24 declined | 22 of 24 (and 11 of 12 controls answered) | yes |

All three must hold, so the fine-tune is **not a win on answering**: no measurable gain on the hard sets. It is a large change in behaviour on declining.

| Set | Prompt-only 7B | Fine-tuned 7B (epoch 2) |
|---|---|---|
| core (49 answerable) | 43 | 43 |
| hard (72) | 46 | 44 |
| hard2 (54) | 35 | 35 |
| decline set, declined of 24 | 4 | 22 |
| held-out, answerable of 40 | 27 | 25 |
| held-out, declined of 12 | 0 | 11 |
| mean seconds per question (hard) | about 20 | 39 (8 GB file mostly on the CPU) |

Single runs; the held-out 2-question difference and the hard 2-question difference are noise.
