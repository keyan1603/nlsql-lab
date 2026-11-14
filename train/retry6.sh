#!/bin/bash
cd /c/agent/nlsql-lab
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base3b --adapter train/out/run6_3b/epoch1 --port 18235 > train/serve6r2.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run6_3b-epoch1 --prompt tuned --max-tokens 512 --retry 2 --set $s --label tuned6r2-$s > train/score6r2_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
echo done > train/score6r2.done
