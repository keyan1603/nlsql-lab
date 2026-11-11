"""Run the same 55 questions on every quantization of one model and tabulate size, memory, speed and accuracy.

    python scripts/quant_sweep.py --model-prefix xiyansql-qwencoder-7b-2504 --family xiyan7b [--quants Q8_0,Q6_K,...]

For each quantization found in LM Studio: load it with identical settings (GPU share and context), run scripts/run_eval.py, sample the
memory the model actually uses while it answers, unload it, and append a row to runs/<family>-sweep.json. Quantizations that already
have a summary file are skipped, so an interrupted sweep resumes.
"""

import argparse
import csv
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
LMS = str(Path.home() / ".lmstudio" / "bin" / "lms.exe")
PY = str(ROOT / "venv" / "Scripts" / "python.exe")


def lms(*args, timeout=900) -> str:
    # lms draws progress spinners in non-ASCII characters; decode as UTF-8 and never fail on a stray byte
    p = subprocess.run([LMS, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return ((p.stdout or "") + (p.stderr or "")).replace("\r", "\n")


def model_entries(prefix: str) -> dict:
    """quantization name -> LM Studio model key, for every downloaded file of the model."""
    out = json.loads(lms("ls", "--json"))
    entries = {}
    for m in out:
        key = m.get("modelKey") or m.get("path") or ""
        if m.get("type") == "llm" and prefix in key.lower():
            quant = (m.get("quantization") or {}).get("name") or key.rsplit("@", 1)[-1]
            entries[quant.upper()] = key
    return entries


def sample_memory(stop: threading.Event, box: dict) -> None:
    """Peak GPU memory in use and peak working set of the inference process while the model answers."""
    while not stop.is_set():
        try:
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip()
            box["gpu_mib"] = max(box.get("gpu_mib", 0), int(gpu.splitlines()[0]))
            rows = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10).stdout
            for row in csv.reader(io.StringIO(rows)):
                if len(row) >= 5 and row[0].lower().startswith("llama-server"):
                    kb = int(row[4].replace(",", "").replace(" K", "").replace(".", "").strip() or 0)
                    box["rss_mib"] = max(box.get("rss_mib", 0), kb // 1024)
        except Exception:
            pass
        stop.wait(5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-prefix", required=True)
    ap.add_argument("--family", required=True)
    ap.add_argument("--quants", help="comma separated; default every quantization found")
    ap.add_argument("--gpu", default="0.55")
    ap.add_argument("--context", default="8192")
    ap.add_argument("--max-tokens", default="1024")
    ap.add_argument("--tag", default="", help="suffix for a repeat run, for example -rep1, so the first run's saved answers are kept")
    ap.add_argument("--set", choices=["core", "hard", "hard2", "decline"], default="core", help="which question set to run")
    args = ap.parse_args()

    entries = model_entries(args.model_prefix)
    wanted = [q.strip().upper() for q in args.quants.split(",")] if args.quants else sorted(entries)
    port_url = None
    status = lms("server", "status")
    for token in status.split():
        if token.rstrip(".").isdigit():
            port_url = f"http://127.0.0.1:{token.rstrip('.')}/v1"
    env = {"LMSTUDIO_BASE_URL": port_url or "http://127.0.0.1:1234/v1"}
    import os
    env = {**os.environ, **env}
    suffix = ("" if args.set == "core" else f"-{args.set}") + args.tag
    table_path = RUNS / f"{args.family}{suffix}-sweep.json"
    table = json.loads(table_path.read_text()) if table_path.exists() else {}

    for quant in wanted:
        if quant not in entries:
            print(f"{quant}: not downloaded, skipping")
            continue
        label = f"{args.family}-{quant.lower().replace('_', '')}{suffix}"
        summary_file = RUNS / f"{label}.summary.json"
        if summary_file.exists():
            print(f"{quant}: already evaluated ({label}), skipping")
        else:
            ident = f"sweep-{label}"
            lms("unload", "--all")
            estimate = lms("load", entries[quant], "--estimate-only", "--gpu", args.gpu, "-c", args.context)
            loaded = lms("load", entries[quant], "--gpu", args.gpu, "-c", args.context, "--identifier", ident, "-y")
            if "loaded successfully" not in loaded.lower():
                print(f"{quant}: load failed\n{loaded[-300:]}")
                continue
            box: dict = {}
            stop = threading.Event()
            t = threading.Thread(target=sample_memory, args=(stop, box), daemon=True)
            t.start()
            t0 = time.time()
            subprocess.run([PY, "-u", str(ROOT / "scripts" / "run_eval.py"), "--model", ident, "--label", label, "--max-tokens", args.max_tokens, "--set", args.set], env=env)
            stop.set()
            t.join(timeout=10)
            lms("unload", ident)
            if not summary_file.exists():
                print(f"{quant}: run did not finish")
                continue
            s = json.loads(summary_file.read_text())
            s["estimate_text"] = " ".join(line.strip() for line in estimate.splitlines() if "Memory" in line)
            s.update({"gpu_peak_mib": box.get("gpu_mib"), "server_rss_peak_mib": box.get("rss_mib"), "sweep_wall_s": round(time.time() - t0, 1)})
            summary_file.write_text(json.dumps(s, indent=2))
        s = json.loads(summary_file.read_text())
        table[quant] = {"label": label, "file_gb": None, "accuracy": s["execution_accuracy"], "correct": s["correct"], "declined": s["declined_correctly"],
                        "sql_errors": s["sql_errors"], "latency_mean_s": s["latency_mean_s"], "tok_s": s["tokens_out_per_s"],
                        "gpu_peak_mib": s.get("gpu_peak_mib"), "rss_peak_mib": s.get("server_rss_peak_mib")}
        table_path.write_text(json.dumps(table, indent=2))
    print(json.dumps(table, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
