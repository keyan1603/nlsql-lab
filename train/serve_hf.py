"""A tiny OpenAI-compatible server around the fine-tuned model (base weights in 4-bit plus a LoRA adapter), for scoring a run before it is
converted to GGUF. Same request shape as LM Studio, so scripts/run_eval.py needs only LMSTUDIO_BASE_URL pointed here.

    venv-train python train/serve_hf.py --adapter train/out/run0/epoch2 --port 1235

Greedy decoding. Latencies measured through this server are NOT comparable with LM Studio's (different runtime); the GGUF run is the one timed.
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(ROOT / "train" / "base"))
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--port", type=int, default=1235)
    a = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(a.base)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.base, quantization_config=bnb, dtype=torch.bfloat16, device_map={"": 0})
    model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()
    name = "tuned-" + Path(a.adapter).parent.name + "-" + Path(a.adapter).name

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"data": [{"id": name}]})

        @torch.no_grad()
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            ids = tok.apply_chat_template(req["messages"], add_generation_prompt=True, return_tensors="pt", return_dict=True).to(0)
            n_in = ids["input_ids"].shape[1]
            out = model.generate(**ids, max_new_tokens=int(req.get("max_tokens", 512)), do_sample=False, pad_token_id=tok.eos_token_id)
            gen = out[0, n_in:]
            text = tok.decode(gen, skip_special_tokens=True)
            done = bool(gen.numel() and gen[-1].item() in (tok.eos_token_id, tok.convert_tokens_to_ids("<|im_end|>")))
            self._send({"choices": [{"message": {"content": text}, "finish_reason": "stop" if done else "length"}],
                        "usage": {"prompt_tokens": n_in, "completion_tokens": int(gen.numel())}})

    print("serving", name, "on", a.port, flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
