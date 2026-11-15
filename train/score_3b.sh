#!/bin/bash
cd /c/agent/nlsql-lab
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base3b --adapter train/out/run4_3b/epoch1 --port 18235 > train/serve4.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run4_3b-epoch1 --prompt tuned --max-tokens 512 --set $s --label tuned4-$s > train/score4_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
for s in core hard hard2 decline; do ./venv/Scripts/python.exe -c "
import json;d=json.load(open('runs/tuned4-$s.summary.json'));print('$s',d['correct'],d['questions'],d['execution_accuracy'],'err',d['sql_errors'],'decl',d['declined_correctly'],d['should_decline'],'inv',d['invented_answers'],'lat',d['latency_mean_s'])"; done
echo finished
