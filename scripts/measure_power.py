"""Measure the GPU's power draw while the local model answers questions.

    python scripts/measure_power.py --model improve-q4km [--n 10]

Polls nvidia-smi once a second: ten idle samples first, then during generation for the first N stress questions (plain prompt, as in
the baseline). Reports mean and peak GPU watts, seconds per question and GPU energy per question. It sees the GPU only: the CPU
(which does part of the work under partial offload), memory and the rest of the machine are not measured here. Writes
docs/results/power_measurement.json.
"""

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlsql.config import ROOT                      # noqa: E402
from nlsql.pipeline import Options, solve          # noqa: E402
from nlsql.questions import load_questions         # noqa: E402


def gpu_watts() -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
    return float(out.strip().splitlines()[0])


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop = [], threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.samples.append((time.monotonic(), gpu_watts()))
            self.stop.wait(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()
    idle = []
    for _ in range(10):
        idle.append(gpu_watts())
        time.sleep(1)
    questions = load_questions(ROOT / "data" / "questions_hard.json")[: args.n]
    opts = Options(extended=True)
    s = Sampler()
    s.start()
    t0 = time.monotonic()
    for q in questions:
        solve(args.model, q.question, opts)
    wall = time.monotonic() - t0
    s.stop.set()
    s.join()
    watts = [w for t, w in s.samples if t >= t0]
    res = {"gpu": subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip(),
           "model": args.model, "questions": len(questions), "idle_w_mean": round(statistics.mean(idle), 1),
           "load_w_mean": round(statistics.mean(watts), 1), "load_w_peak": round(max(watts), 1), "samples": len(watts),
           "seconds_per_question": round(wall / len(questions), 2),
           "gpu_wh_per_question": round(statistics.mean(watts) * (wall / len(questions)) / 3600, 4)}
    (ROOT / "docs" / "results" / "power_measurement.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
