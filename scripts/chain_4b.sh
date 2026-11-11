#!/bin/bash
# Wait for the first download pass, fetch whatever is still missing, then sweep the 4B ladder on both halves of the stress set.
cd "$(dirname "$0")/.."
until grep -q FETCHDONE runs/fetch4b.log; do sleep 60; done
R=mradermacher/Qwen3-4B-Instruct-2507-GGUF
D=/c/Users/keyan/.lmstudio/models/mradermacher/Qwen3-4B-Instruct-2507-GGUF
for q in Q8_0 Q6_K Q5_K_M Q4_K_M Q3_K_M Q3_K_S Q2_K; do
  for i in 1 2 3 4 5 6 7 8; do [ -f "$D/Qwen3-4B-Instruct-2507.$q.gguf" ] && break; ./venv/Scripts/python scripts/fetch_model.py $R Qwen3-4B-Instruct-2507.$q.gguf || sleep 20; done
done
for SET in hard hard2; do
  ./venv/Scripts/python -u scripts/quant_sweep.py --model-prefix mradermacher/qwen3-4b-instruct-2507 --family qwen4b --set $SET
done
echo CHAINDONE
