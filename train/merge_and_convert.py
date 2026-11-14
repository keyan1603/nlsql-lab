"""Merge a LoRA adapter into the base weights (on the CPU, in bf16) and convert the result to GGUF with llama.cpp's converter.

    venv-train python train/merge_and_convert.py --adapter train/out/run2/epoch1 --name nlsql-tuned-run2 --outtype q8_0

The merged model is saved under train/out/<name>/ and the GGUF next to it. Merging a 4-bit-trained adapter into the unquantised base is the
standard QLoRA deployment step; the adapter was trained against slightly rounded weights, so the merged model is checked by scoring it, not assumed.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(ROOT / "train" / "base"))
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--outtype", default="q8_0", choices=["f16", "bf16", "q8_0"])
    a = ap.parse_args()
    out = ROOT / "train" / "out" / a.name
    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16, device_map={"": "cpu"})
    model = PeftModel.from_pretrained(model, a.adapter).merge_and_unload()
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    gguf = out / f"{a.name}-{a.outtype}.gguf"
    env = dict(os.environ)                       # the converter then uses the gguf-py folder of the same llama.cpp tag (the pip release is older)
    subprocess.run([sys.executable, str(ROOT / "train" / "tools" / "convert_hf_to_gguf.py"), str(out), "--outfile", str(gguf), "--outtype", a.outtype], check=True, env=env)
    print("wrote", gguf, round(gguf.stat().st_size / 1e9, 2), "GB")


if __name__ == "__main__":
    main()
