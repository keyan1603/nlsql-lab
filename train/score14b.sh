#!/bin/bash
# Score XiYanSQL-QwenCoder-14B (Q4_K_M, mostly on CPU on a 4 GB GPU) with the same configuration as the final 7B run.
cd /c/agent/nlsql-lab
export PATH=$PATH:/c/Users/keyan/.lmstudio/bin
lms unload --all > /dev/null 2>&1
lms load xiyansql-qwencoder-14b-2504 --gpu 0.4 --identifier xiyan14b -c 8192 -y > train/load14b.log 2>&1
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
for s in core hard hard2 heldout decline; do
  ./venv/Scripts/python.exe scripts/run_eval.py --model xiyan14b --prompt tuned --decline-shots 4 --retry 2 --max-tokens 1024 --set $s --label xiyan14b-final-$s > train/score14b_$s.log 2>&1
done
lms unload --all > /dev/null 2>&1
echo done > train/score14b.done
