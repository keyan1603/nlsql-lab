"""The cost model: what a question costs on the local model and on the hosted one.

    python scripts/cost_model.py

MEASURED (read from this lab's own runs): tokens per question on the hosted model, seconds per question on the local one, and the
GPU's power draw during local generation (scripts/measure_power.py).
PUBLISHED (cited): the hosted model's per-token prices.
ASSUMED (clearly marked, with a range, because this lab cannot measure them): the power the CPU and the rest of the laptop draw
during generation, the price of electricity, and the monthly cost of a dedicated machine. Change them in ASSUMPTIONS and re-run.
Writes docs/results/cost_model.md.
"""

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

# Published: https://ai.google.dev/gemini-api/docs/pricing (redirects to https://aistudio.google.com/docs/pricing), read 2026-11-12.
# The page shows no last-updated date. Output price includes thinking tokens. The free tier is free of charge and states that its
# content is used to improve Google's products.
PRICE = {"Standard": (0.30, 2.50), "Batch": (0.15, 1.25), "Priority": (0.54, 4.50)}      # USD per 1M tokens: (input, output)

ASSUMPTIONS = {
    "cpu_and_system_w": (40, (20, 60)),               # watts drawn by the CPU and the rest of the laptop while generating (not measured)
    "usd_per_kwh": (0.15, (0.08, 0.30)),              # electricity price (depends on where the machine runs)
    "dedicated_machine_usd_per_month": (200, (50, 800)),   # a machine or instance kept for this workload, 24 hours a day
}


def load(name: str) -> list[dict]:
    p = RUNS / f"{name}.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def usd(tin: float, tout: float, tier: str) -> float:
    pin, pout = PRICE[tier]
    return tin * pin / 1e6 + tout * pout / 1e6


def main() -> int:
    plain = [r for n in ("gemini-flashlite", "gemini-flashlite-hard", "gemini-flashlite-hard2", "gemini-flashlite-decline") for r in load(n)]
    stack = [r for n in ("gemini-p5r2-hard", "gemini-p5r2-hard2") for r in load(n)]
    local = [r for n in ("xiyan7b-q4km", "xiyan7b-q4km-hard", "xiyan7b-q4km-hard2", "imp-base-decline") for r in load(n)]
    power = json.loads((ROOT / "docs" / "results" / "power_measurement.json").read_text(encoding="utf-8"))
    n = len(plain)
    tin, tout = sum(r["tokens_in"] for r in plain) / n, sum(r["tokens_out"] for r in plain) / n
    secs = statistics.mean(r["latency_s"] for r in local)
    cpu_w, (cpu_lo, cpu_hi) = ASSUMPTIONS["cpu_and_system_w"]
    kwh_price, (kwh_lo, kwh_hi) = ASSUMPTIONS["usd_per_kwh"]
    machine, (m_lo, m_hi) = ASSUMPTIONS["dedicated_machine_usd_per_month"]

    def local_cost(cpu: float, price: float, s: float = secs) -> float:
        return (power["load_w_mean"] + cpu) * s / 3600 / 1000 * price

    base_local = local_cost(cpu_w, kwh_price)
    hosted = {t: usd(tin, tout, t) for t in PRICE}
    L = ["# Cost model", "",
         "Measured values come from this lab's runs; published prices are cited; **assumptions are marked and have a range**, because a laptop's CPU draw, a local electricity price and a server's monthly cost are not things this lab can measure. "
         "The point is the shape of the comparison, not three-decimal accuracy.", "",
         "## Inputs", "",
         "| Input | Value | Status |", "|---|---|---|",
         f"| Hosted tokens per question (plain prompt, {n} questions) | {tin:,.0f} in, {tout:,.0f} out | measured |",
         f"| Hosted price, Standard tier | ${PRICE['Standard'][0]:.2f} in, ${PRICE['Standard'][1]:.2f} out per 1M tokens | published ([pricing page](https://ai.google.dev/gemini-api/docs/pricing), read 2026-11-12, no last-updated date shown) |",
         f"| Hosted price, Batch tier | ${PRICE['Batch'][0]:.2f} in, ${PRICE['Batch'][1]:.2f} out per 1M tokens | published, same page (asynchronous) |",
         "| Hosted free tier | free of charge; the page says its content is used to improve Google's products | published, same page |",
         f"| Local seconds per question | {secs:.1f} (4 GB RTX 2050, partial offload, {len(local)} questions) | measured |",
         f"| Local GPU power during generation | {power['load_w_mean']} W mean, {power['load_w_peak']} W peak ({power['idle_w_mean']} W idle), {power['samples']} samples over {power['questions']} questions | measured with nvidia-smi |",
         f"| CPU and rest of the laptop while generating | {cpu_w} W (range {cpu_lo} to {cpu_hi}) | **assumed** |",
         f"| Electricity | ${kwh_price:.2f} per kWh (range ${kwh_lo:.2f} to ${kwh_hi:.2f}) | **assumed** |",
         f"| A dedicated machine kept for the workload | ${machine} per month (range ${m_lo} to ${m_hi}) | **assumed** |", "",
         "## Cost per 1,000 questions", "",
         "| Option | USD per 1,000 questions | Notes |", "|---|---|---|",
         f"| Hosted, free tier | 0 | rate-limited, and content is used to improve the provider's products: not for private data |",
         f"| Hosted, Standard | {hosted['Standard'] * 1000:.2f} | {tin * PRICE['Standard'][0] / 1e6 * 1000:.2f} input + {tout * PRICE['Standard'][1] / 1e6 * 1000:.2f} output |",
         f"| Hosted, Batch | {hosted['Batch'] * 1000:.2f} | half price, asynchronous |",
         f"| Local, electricity only | {base_local * 1000:.3f} | at the assumed {power['load_w_mean'] + cpu_w:.0f} W total and ${kwh_price:.2f}/kWh; range {local_cost(cpu_lo, kwh_lo) * 1000:.3f} to {local_cost(cpu_hi, kwh_hi) * 1000:.3f} |", "",
         f"Electricity is a small fraction of the hosted token bill (about {hosted['Standard'] / base_local:.0f} times less per question at the central assumptions), but electricity is not the whole local cost: the machine itself has to exist and be kept running.", "",
         f"For scale: the 217-question hosted baseline in this lab would have cost ${usd(tin * n, tout * n, 'Standard'):.2f} on the Standard tier ({tin * n:,.0f} input and {tout * n:,.0f} output tokens)."]

    if stack:
        s_in, s_out = sum(r["tokens_in"] for r in stack) / len(stack), sum(r["tokens_out"] for r in stack) / len(stack)
        calls = sum((r.get("pipeline") or {}).get("calls", 1) for r in stack) / len(stack)
        hp = [r for n_ in ("gemini-flashlite-hard", "gemini-flashlite-hard2") for r in load(n_)]
        p_in, p_out = sum(r["tokens_in"] for r in hp) / len(hp), sum(r["tokens_out"] for r in hp) / len(hp)
        L += ["", "## The prune-and-retry stack on the hosted model (stress questions)", "",
              f"| Hosted, stress set ({len(stack)} questions) | Tokens in / out per question | Calls per question | USD per 1,000 (Standard) |", "|---|---|---|---|",
              f"| Plain prompt | {p_in:,.0f} / {p_out:,.0f} | 1.00 | {usd(p_in, p_out, 'Standard') * 1000:.2f} |",
              f"| 5 tables + retry on error | {s_in:,.0f} / {s_out:,.0f} | {calls:.2f} | {usd(s_in, s_out, 'Standard') * 1000:.2f} |"]

    # cost per correct answer on the stress set
    def acc(names):
        rs = [r for n_ in names for r in load(n_)]
        return sum(r["outcome"] == "correct" for r in rs) / len(rs) if rs else None
    la, ha = acc(("xiyan7b-q4km-hard", "xiyan7b-q4km-hard2")), acc(("gemini-flashlite-hard", "gemini-flashlite-hard2"))
    if la and ha:
        L += ["", "## Per correct answer (stress set, where the models differ most)", "",
              "| Option | Accuracy | USD per 1,000 correct answers |", "|---|---|---|",
              f"| Local, electricity only | {la * 100:.1f}% | {base_local * 1000 / la:.3f} |",
              f"| Hosted, Standard | {ha * 100:.1f}% | {hosted['Standard'] * 1000 / ha:.2f} |", "",
              "This spreads the price of every question, right or wrong, over the right ones. It treats a wrong answer as costing nothing beyond its own price. In an enterprise a wrong answer usually costs more (a wrong number in a report, a retry, a person checking it), so read accuracy next to the price rather than folded into it."]

    # break-even against a dedicated machine
    L += ["", "## When does running your own machine pay for itself?", "",
          "A dedicated machine costs the same whether it answers one question or many. It beats the hosted Standard price once the monthly volume exceeds machine cost divided by the saving per question:", "",
          "| Dedicated machine per month (assumed) | Break-even questions per month vs Standard | vs Batch |", "|---|---|---|"]
    for m in (m_lo, machine, m_hi):
        L.append(f"| ${m} | {m / (hosted['Standard'] - base_local):,.0f} | {m / (hosted['Batch'] - base_local):,.0f} |")
    cap = 3600 / secs * 24 * 30
    L += ["", f"For scale, the laptop used here answers one question every {secs:.1f} s, so about {cap:,.0f} a month if it ran flat out around the clock. Below the break-even volume the hosted model is cheaper; above it the local machine is, **provided its answers are good enough**: on the stress set the local model got {la * 100:.0f}% against {ha * 100:.0f}%. "
          "A larger local model on proper hardware changes both the price and the accuracy, and is not measured here." if la and ha else ""]
    text = "\n".join(L) + "\n"
    (ROOT / "docs" / "results" / "cost_model.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
