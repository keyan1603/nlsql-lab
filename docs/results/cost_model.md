# Cost model

Measured values come from this lab's runs; published prices are cited; **assumptions are marked and have a range**, because a laptop's CPU draw, a local electricity price and a server's monthly cost are not things this lab can measure. The point is the shape of the comparison, not three-decimal accuracy.

## Inputs

| Input | Value | Status |
|---|---|---|
| Hosted tokens per question (plain prompt, 217 questions) | 3,761 in, 93 out | measured |
| Hosted price, Standard tier | $0.30 in, $2.50 out per 1M tokens | published ([pricing page](https://ai.google.dev/gemini-api/docs/pricing), read 2026-11-12, no last-updated date shown) |
| Hosted price, Batch tier | $0.15 in, $1.25 out per 1M tokens | published, same page (asynchronous) |
| Hosted free tier | free of charge; the page says its content is used to improve Google's products | published, same page |
| Local seconds per question | 12.7 (4 GB RTX 2050, partial offload, 217 questions) | measured |
| Local GPU power during generation | 14.3 W mean, 20.0 W peak (4.7 W idle), 99 samples over 10 questions | measured with nvidia-smi |
| CPU and rest of the laptop while generating | 40 W (range 20 to 60) | **assumed** |
| Electricity | $0.15 per kWh (range $0.08 to $0.30) | **assumed** |
| A dedicated machine kept for the workload | $200 per month (range $50 to $800) | **assumed** |

## Cost per 1,000 questions

| Option | USD per 1,000 questions | Notes |
|---|---|---|
| Hosted, free tier | 0 | rate-limited, and content is used to improve the provider's products: not for private data |
| Hosted, Standard | 1.36 | 1.13 input + 0.23 output |
| Hosted, Batch | 0.68 | half price, asynchronous |
| Local, electricity only | 0.029 | at the assumed 54 W total and $0.15/kWh; range 0.010 to 0.078 |

Electricity is a small fraction of the hosted token bill (about 47 times less per question at the central assumptions), but electricity is not the whole local cost: the machine itself has to exist and be kept running.

For scale: the 217-question hosted baseline in this lab would have cost $0.30 on the Standard tier (816,188 input and 20,139 output tokens).

## The prune-and-retry stack on the hosted model (stress questions)

| Hosted, stress set (126 questions) | Tokens in / out per question | Calls per question | USD per 1,000 (Standard) |
|---|---|---|---|
| Plain prompt | 4,219 / 128 | 1.00 | 1.59 |
| 5 tables + retry on error | 1,830 / 151 | 1.13 | 0.93 |

## Per correct answer (stress set, where the models differ most)

| Option | Accuracy | USD per 1,000 correct answers |
|---|---|---|
| Local, electricity only | 56.3% | 0.051 |
| Hosted, Standard | 87.3% | 1.56 |

This spreads the price of every question, right or wrong, over the right ones. It treats a wrong answer as costing nothing beyond its own price. In an enterprise a wrong answer usually costs more (a wrong number in a report, a retry, a person checking it), so read accuracy next to the price rather than folded into it.

## When does running your own machine pay for itself?

A dedicated machine costs the same whether it answers one question or many. It beats the hosted Standard price once the monthly volume exceeds machine cost divided by the saving per question:

| Dedicated machine per month (assumed) | Break-even questions per month vs Standard | vs Batch |
|---|---|---|
| $50 | 37,545 | 76,740 |
| $200 | 150,179 | 306,959 |
| $800 | 600,715 | 1,227,835 |

For scale, the laptop used here answers one question every 12.7 s, so about 204,762 a month if it ran flat out around the clock. Below the break-even volume the hosted model is cheaper; above it the local machine is, **provided its answers are good enough**: on the stress set the local model got 56% against 87%. A larger local model on proper hardware changes both the price and the accuracy, and is not measured here.
