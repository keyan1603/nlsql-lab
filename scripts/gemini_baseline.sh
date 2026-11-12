#!/bin/bash
# Phase 5: the hosted baseline. gemini-3.5-flash-lite, plain prompt, every question set, greedy decoding.
# 217 questions = 217 requests, well inside the free tier's 500 a day (nlsql/llm_gemini.py also caps a day at GEMINI_DAILY_CAP, default 450).
# A run that stops (quota, network) resumes where it stopped: re-run the same command.
# usage: scripts/gemini_baseline.sh [model]
cd "$(dirname "$0")/.."
MODEL=${1:-gemini-3.5-flash-lite}
for SET in core hard hard2 decline; do
  LABEL="gemini-flashlite"; [ "$SET" != "core" ] && LABEL="gemini-flashlite-$SET"
  ./venv/Scripts/python -u scripts/run_eval.py --model "$MODEL" --label "$LABEL" --set $SET --max-tokens 4096 2>&1 | tail -4
done
echo GEMINIDONE
