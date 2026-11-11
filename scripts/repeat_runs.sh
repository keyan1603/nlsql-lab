#!/bin/bash
# Run the Q8_0 and Q2_K levels of XiYan again on both halves of the stress set, to measure how much the score moves between identical runs.
cd "$(dirname "$0")/.."
TAG=${1:--rep1}
for SET in hard hard2; do
  ./venv/Scripts/python -u scripts/quant_sweep.py --model-prefix xiyansql-qwencoder-7b-2504 --family xiyan7b --set $SET --tag="$TAG" --quants Q8_0,Q2_K
done
echo REPEATDONE
