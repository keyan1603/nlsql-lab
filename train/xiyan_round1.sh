#!/bin/bash
# Stage A round 1: one change at a time, on the selection sets only (dev, dev2, hard).
cd /c/agent/nlsql-lab
lms unload --all
lms load xiyansql-qwencoder-7b-2504@q4_k_m --identifier xiyan -c 8192 -y
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
S="dev dev2 hard"
train/xiyan_run.sh plain "dev dev2"
train/xiyan_run.sh tuned "$S" --prompt tuned
train/xiyan_run.sh tuned-dialect "$S" --prompt tuned --dialect
train/xiyan_run.sh tuned-d4 "$S" --prompt tuned --decline-shots 4
train/xiyan_run.sh mschema "dev dev2" --prompt mschema
echo done > train/xiyan_round1.done
