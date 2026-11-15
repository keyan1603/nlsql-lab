#!/bin/bash
cd /c/agent/nlsql-lab
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
./venv/Scripts/python.exe scripts/run_eval.py --model omnisql7b-q4km --set core --max-tokens 1024 --label omnisql7b-q4km > train/score_omni_core.log 2>&1
./venv/Scripts/python.exe scripts/run_eval.py --model omnisql7b-q4km --set decline --max-tokens 1024 --label omnisql7b-q4km-decline > train/score_omni_decline.log 2>&1
echo done > train/score_omni.done
