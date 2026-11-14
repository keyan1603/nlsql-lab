#!/bin/bash
# Stage A round 3: on the base chosen by the pre-stated rule (highest answerable + decline total on dev, dev2, hard: tuned-d4), add retry and the decline guard.
cd /c/agent/nlsql-lab
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
S="dev dev2 hard"
train/xiyan_run.sh tuned-d4-r2 "$S" --prompt tuned --decline-shots 4 --retry 2
train/xiyan_run.sh tuned-d4-guard "$S" --prompt tuned --decline-shots 4 --guard
echo done > train/xiyan_round3.done
