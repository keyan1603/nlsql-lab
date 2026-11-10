#!/bin/bash
# Run the quantization sweep repeatedly until every quantization of the model has been evaluated; files that are still downloading are
# picked up on a later pass.
cd "$(dirname "$0")/.."
WANT=11
SET=${1:-core}
SUFFIX=""; [ "$SET" = "hard" ] && SUFFIX="-hard"
while true; do
  ./venv/Scripts/python -u scripts/quant_sweep.py --model-prefix xiyansql-qwencoder-7b-2504 --family xiyan7b --set $SET
  n=$(./venv/Scripts/python -c "import json,pathlib;p=pathlib.Path('runs/xiyan7b${SUFFIX}-sweep.json');print(len(json.loads(p.read_text())) if p.exists() else 0)")
  echo "sweep pass finished: $n of $WANT quantizations evaluated"
  [ "$n" -ge "$WANT" ] && break
  sleep 180
done
echo SWEEPDONE
