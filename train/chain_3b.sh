#!/bin/bash
cd /c/agent/nlsql-lab
until grep -q "^done" train/run3.log; do sleep 20; done
sleep 20
./venv-train/Scripts/python.exe train/serve_hf.py --adapter train/out/run3/epoch2 --port 18235 > train/serve3.log 2>&1 &
sleep 100
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run3-epoch2 --prompt tuned --max-tokens 512 --set $s --label tuned3-$s > train/score3_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
sleep 15
echo scored > train/score3.done
./venv-train/Scripts/python.exe train/train_lora.py --base train/base3b --out train/out/run4_3b --epochs 1 --micro 2 --accum 8 --tok-budget 1300 > train/run4_3b.log 2>&1
