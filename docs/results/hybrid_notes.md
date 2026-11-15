### Method

The live pipeline (`nlsql/hybrid.py`, `nlsql/hybrid_live.py`) runs, per question: the 3B decline gate (`nlsql-tuned-run6-3b`, Q8_0 GGUF), then the deterministic rules, then the 7B SQL model (`xiyansql-qwencoder-7b-2504@q4_k_m`, tuned prompt, 4 decline examples, up to 2 repairs), then the checks (SQL runs through the guard, non-empty result, no invented values), and only then the hosted model (gemini-3.5-flash-lite). Every question produces an audit record with a question hash, the tiers touched, the escalation reason, per-tier latency and token counts, and whether the question left the boundary. Policy `sealed` forbids the hosted tier and returns a structured "escalation required, withheld" result; policy `open` allows it. A `redacted` policy is not implemented: masking the literal values in a question makes it unanswerable, because the values are what the question asks about.

### Settings

Both local models stay loaded in LM Studio (port 1235) with partial GPU offload (7B `--gpu 0.5`, gate `--gpu 0.3`, context 8192), about 3.9 of 4.1 GB of GPU memory. Per-question latency therefore contains no model load time, but inference is slower than with one model loaded alone, and the seconds here are not comparable with the earlier single-model timings. Warm-up calls are excluded.

### Caveats

- Single runs on a 4 GB GPU. The hosted model is not bit-repeatable.
- The gate is one greedy call of at most 48 tokens with no repair; the saved gate runs used the full answer and up to 2 repairs.
- A missing SQL reply, an unparseable reply, a guard refusal, a timeout or a capped result count as an error and escalate; the saved-answer simulation escalated only genuine SQL errors.
- The prompts and settings differ slightly from the simulated pool numbers, so exact agreement with them (147 of 181 in both) is partly luck of the single run.
- No saved-answer simulation exists for the held-out set, so it has no simulated comparison.
- The egress monitor wraps the Python socket calls of this process. It does not see subprocesses, native extensions that bypass the socket module, or other processes on the machine. In `sealed` mode every connection was to the local model server on 127.0.0.1 and a deliberate test connection to a public address was blocked before any packet was sent. In `open` mode the outside destinations recorded were the hosted model endpoint only (the 69 escalated questions).
- Whether the guard blocked any SQL that the grader would have passed was not analysed.
