#!/bin/bash
# Stage A round 2: combine the levers that looked useful in round 1 (selection sets only).
cd /c/agent/nlsql-lab
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
S="dev dev2 hard"
train/xiyan_run.sh tuned-dialect-d4 "$S" --prompt tuned --dialect --decline-shots 4
train/xiyan_run.sh tuned-dialect-d6 "$S" --prompt tuned --dialect --decline-shots 6
train/xiyan_run.sh tuned-dialect-d6-a2 "$S" --prompt tuned --dialect --decline-shots 6 --answer-shots 2
echo done > train/xiyan_round2.done
