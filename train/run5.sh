#!/bin/bash
cd /c/agent/nlsql-lab
./venv-train/Scripts/python.exe train/train_lora.py --base train/base3b --init train/out/run4_3b/epoch1 --train train/data/cont_train.jsonl --val train/data/cont_val.jsonl --out train/out/run5_3b --epochs 1 --lr 1e-4 --micro 2 --accum 8 --tok-budget 1300 > train/run5_3b.log 2>&1
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base3b --adapter train/out/run5_3b/epoch1 --port 18235 > train/serve6.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in dev core decline hard hard2; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run5_3b-epoch1 --prompt tuned --max-tokens 512 --set $s --label tuned5-$s > train/score5_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
echo scored5 > train/score5.done
