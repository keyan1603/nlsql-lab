#!/bin/bash
# Round 1 of the improvement round: each technique on its own, XiYan Q4_K_M, both halves of the stress set.
# usage: scripts/improve_round.sh <model identifier> "<tag>|<run_eval flags>" ...
cd "$(dirname "$0")/.."
MODEL=$1; shift
export LMSTUDIO_BASE_URL=${LMSTUDIO_BASE_URL:-http://127.0.0.1:1235/v1}
for cfg in "$@"; do
  TAG=${cfg%%|*}; FLAGS=${cfg#*|}
  for SET in ${SETS:-hard hard2}; do
    ./venv/Scripts/python -u scripts/run_eval.py --model "$MODEL" --label "imp-$TAG-$SET" --set $SET $FLAGS 2>&1 | tail -3
  done
done
echo IMPROVEDONE
