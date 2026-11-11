#!/bin/bash
# Second pass: the other 4B levels are registered in LM Studio as qwen3-4b-instruct-2507@<quant>; levels already evaluated are skipped.
cd "$(dirname "$0")/.."
until grep -q CHAINDONE runs/chain_4b.log; do sleep 60; done
for SET in hard hard2; do
  ./venv/Scripts/python -u scripts/quant_sweep.py --model-prefix "qwen3-4b-instruct-2507@" --family qwen4b --set $SET
done
echo CHAINBDONE
