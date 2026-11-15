#!/bin/bash
cd /c/agent/nlsql-lab
lms load nlsql-tuned-run6-3b --identifier tuned6-q8 -c 8192 --gpu max -y > train/package6_load.log 2>&1
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
for s in core decline hard hard2; do
  ./venv/Scripts/python.exe scripts/run_eval.py --model tuned6-q8 --prompt tuned --max-tokens 512 --retry 2 --set $s --label tuned6gguf-$s > train/package6_$s.log 2>&1
done
lms unload --all > /dev/null 2>&1
echo done > train/package6.done
