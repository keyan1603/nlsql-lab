#!/bin/bash
cd /c/agent/nlsql-lab
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base3b --adapter train/out/run4_3b/epoch1 --port 18235 > train/serve5.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run4_3b-epoch1 --prompt tuned --max-tokens 512 --retry 2 --set $s --label tuned4r2-$s > train/score4r2_$s.log 2>&1; done
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run4_3b-epoch1 --prompt tuned --max-tokens 512 --retry 2 --retry-empty --set $s --label tuned4r2e-$s > train/score4r2e_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
for l in tuned4r2 tuned4r2e; do for s in core hard hard2 decline; do ./venv/Scripts/python.exe -c "
import json;d=json.load(open('runs/$l-$s.summary.json'));print('$l $s',d['correct'],d['questions'],d['execution_accuracy'],'err',d['sql_errors'],'decl',d['declined_correctly'],d['should_decline'],'inv',d['invented_answers'],'calls',d['model_calls'],'lat',d['latency_mean_s'])"; done; done
echo finished
