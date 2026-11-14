#!/bin/bash
# Usage: train/xiyan_run.sh <config-name> "<sets>" <run_eval flags...>
# Runs scripts/run_eval.py for each set against the XiYan model already loaded in LM Studio as identifier "xiyan".
# Labels: xy-<config>-<set>. Needs LMSTUDIO_BASE_URL (set here). Resumes a partly finished run.
cd /c/agent/nlsql-lab
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
name=$1; sets=$2; shift 2
for s in $sets; do
  ./venv/Scripts/python.exe scripts/run_eval.py --model xiyan --set $s --max-tokens 1024 --label xy-$name-$s "$@" > runs/xy-$name-$s.log 2>&1
  tail -1 runs/xy-$name-$s.log
done
