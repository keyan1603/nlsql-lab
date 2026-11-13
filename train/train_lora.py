"""QLoRA fine-tuning of a small coder model on the lab's training pairs, sized for a 4 GB laptop GPU.

    train\\venv\\...python train/train_lora.py --epochs 3 --out train/out/run1

The base model is loaded in 4-bit (NF4), LoRA adapters are trained on every linear layer in bf16, and the loss is computed on the
assistant's reply only (the question and the rules are context, not something to imitate). Memory is kept in budget with gradient
checkpointing and small micro-batches. Writes the adapter after every epoch plus a log with train and validation loss.
Plain PyTorch on purpose: nothing hides what the training loop does.
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).resolve().parent.parent


def load_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def encode(tok, messages: list[dict], max_len: int):
    """Token ids and labels: -100 on everything except the assistant reply."""
    prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
    full = prompt + messages[-1]["content"] + "<|im_end|>\n"
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    f_ids = tok(full, add_special_tokens=False)["input_ids"]
    if len(f_ids) > max_len:
        return None
    labels = [-100] * len(p_ids) + f_ids[len(p_ids):]
    return f_ids, labels


def batches(examples, micro, rng, shuffle=True, budget=700):
    idx = list(range(len(examples)))
    if shuffle:
        rng.shuffle(idx)
        # bucket by length inside windows of 64 so padding stays small, then shuffle the buckets
        chunks = [sorted(idx[i:i + 64], key=lambda j: len(examples[j][0])) for i in range(0, len(idx), 64)]
        groups = []
        for c in chunks:                              # fill a micro-batch until it holds `micro` examples or the padded size reaches the token budget
            cur = []
            for j in c:
                if cur and (len(cur) >= micro or len(examples[j][0]) * (len(cur) + 1) > budget):
                    groups.append(cur)
                    cur = []
                cur.append(j)
            if cur:
                groups.append(cur)
        rng.shuffle(groups)
    else:
        groups = [idx[i:i + micro] for i in range(0, len(idx), micro)]
    for g in groups:
        width = max(len(examples[j][0]) for j in g)
        ids = torch.full((len(g), width), 0, dtype=torch.long)
        lab = torch.full((len(g), width), -100, dtype=torch.long)
        att = torch.zeros((len(g), width), dtype=torch.long)
        for r, j in enumerate(g):
            a, b = examples[j]
            ids[r, :len(a)], lab[r, :len(b)], att[r, :len(a)] = torch.tensor(a), torch.tensor(b), 1
        yield ids, lab, att


def reply_loss(model, ids, lab, att):
    """Cross-entropy on the reply tokens only. The 152k-word output layer is applied to those positions alone, not to the whole prompt,
    which is what keeps a 1,000-token example inside 4 GB."""
    inner = model.base_model.model                       # PeftModel -> LoraModel -> the causal LM
    hidden = inner.model(input_ids=ids, attention_mask=att).last_hidden_state[:, :-1]
    target = lab[:, 1:]
    keep = target != -100
    logits = inner.lm_head(hidden[keep])
    return torch.nn.functional.cross_entropy(logits.float(), target[keep]), int(keep.sum())


@torch.no_grad()
def evaluate(model, examples, micro, device):
    model.eval()
    tot, n = 0.0, 0
    for ids, lab, att in batches(examples, micro, None, shuffle=False):
        loss, k = reply_loss(model, ids.to(device), lab.to(device), att.to(device))
        tot += loss.item() * k
        n += k
    model.train()
    return tot / max(n, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(ROOT / "train" / "base"))
    ap.add_argument("--train", default=str(ROOT / "train" / "data" / "train.jsonl"))
    ap.add_argument("--val", default=str(ROOT / "train" / "data" / "val.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "train" / "out" / "run1"))
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--micro", type=int, default=2)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=32)
    ap.add_argument("--tok-budget", type=int, default=1700, help="most padded tokens in one micro-batch; the 4 GB card fails above about 500")
    ap.add_argument("--max-len", type=int, default=1100)
    ap.add_argument("--limit", type=int, default=0, help="train on the first N examples only (smoke test)")
    ap.add_argument("--init", default="", help="adapter directory to continue from")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    torch.manual_seed(a.seed)
    device = "cuda"
    tok = AutoTokenizer.from_pretrained(a.base)
    enc = lambda rows: [e for e in (encode(tok, r["messages"], a.max_len) for r in rows) if e]
    train_rows, val_rows = load_rows(Path(a.train)), load_rows(Path(a.val))
    if a.limit:
        train_rows, val_rows = train_rows[:a.limit], val_rows[:max(a.limit // 8, 8)]
    train, val = enc(train_rows), enc(val_rows)
    print(f"examples: train {len(train)}/{len(train_rows)} val {len(val)}/{len(val_rows)} (rest longer than {a.max_len} tokens); "
          f"mean length {sum(len(x[0]) for x in train) / len(train):.0f} tokens", flush=True)

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.base, quantization_config=bnb, torch_dtype=torch.bfloat16, device_map={"": 0})
    # not prepare_model_for_kbit_training: it casts the 151k-word embedding matrix to fp32 (about 1 GB), which a 4 GB card cannot spare
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    if a.init:
        model = PeftModel.from_pretrained(model, a.init, is_trainable=True)          # continue training an earlier adapter
    else:
        model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0, betas=(0.9, 0.99))
    steps_per_epoch = max(sum(1 for _ in batches(train, a.micro, random.Random(0), budget=a.tok_budget)) // a.accum, 1)    # micro-batches are token-budgeted, so count them
    total = steps_per_epoch * a.epochs
    warm = max(int(0.04 * total), 3)
    lr_at = lambda s: a.lr * (s + 1) / warm if s < warm else a.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * (s - warm) / max(total - warm, 1))))

    log = []
    step, t0 = 0, time.time()
    model.train()
    for epoch in range(a.epochs):
        micro_i, run_loss, run_n = 0, 0.0, 0
        opt.zero_grad(set_to_none=True)
        for ids, lab, att in batches(train, a.micro, rng, budget=a.tok_budget):
            loss, _ = reply_loss(model, ids.to(device), lab.to(device), att.to(device))
            (loss / a.accum).backward()
            run_loss, run_n, micro_i = run_loss + loss.item(), run_n + 1, micro_i + 1
            if micro_i % a.accum == 0:
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                for g in opt.param_groups:
                    g["lr"] = lr_at(step)
                opt.step()
                opt.zero_grad(set_to_none=True)
                torch.cuda.empty_cache()                    # variable-length batches fragment the cache; on a 4 GB card the overflow spills to system memory and training slows several-fold
                step += 1
                if step % 5 == 0:
                    rec = {"step": step, "epoch": epoch + 1, "loss": round(run_loss / run_n, 4), "lr": round(lr_at(step), 7), "elapsed_s": round(time.time() - t0),
                           "gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)}
                    log.append(rec)
                    print(rec, flush=True)
                    run_loss, run_n = 0.0, 0
        v = evaluate(model, val, a.micro, device)
        rec = {"epoch": epoch + 1, "val_loss": round(v, 4), "elapsed_s": round(time.time() - t0)}
        log.append(rec)
        print(rec, flush=True)
        model.save_pretrained(out / f"epoch{epoch + 1}")
        (out / "log.json").write_text(json.dumps({"args": vars(a), "log": log}, indent=1), encoding="utf-8")
    print("done", round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main()
