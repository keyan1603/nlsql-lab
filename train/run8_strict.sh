#!/bin/bash
# Retrain the 3B (run4 -> run6 recipe) on data without pairs that filter on held-out test cells, then score it.
cd /c/agent/nlsql-lab
until [ -f train/score7r2.done ]; do sleep 60; done
./venv-train/Scripts/python.exe train/train_lora.py --base train/base3b --train train/data/strict_train.jsonl --val train/data/strict_val.jsonl --out train/out/run8a_3b --epochs 1 --micro 2 --accum 8 --tok-budget 1300 > train/run8a_3b.log 2>&1
./venv-train/Scripts/python.exe train/train_lora.py --base train/base3b --init train/out/run8a_3b/epoch1 --train train/data/strict_cont2_train.jsonl --val train/data/strict_cont2_val.jsonl --out train/out/run8_3b --epochs 1 --lr 1e-4 --micro 2 --accum 8 --tok-budget 1300 > train/run8_3b.log 2>&1
echo done > train/run8_train.done
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base3b --adapter train/out/run8_3b/epoch1 --port 18235 > train/serve8.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in dev2 dev; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run8_3b-epoch1 --prompt tuned --max-tokens 512 --set $s --label tuned8-$s > train/score8_$s.log 2>&1; done
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run8_3b-epoch1 --prompt tuned --max-tokens 512 --retry 2 --set $s --label tuned8r2-$s > train/score8r2_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
./venv/Scripts/python.exe scripts/route_eval.py --local-run tuned8r2 > train/route8.log 2>&1
echo done > train/run8_ft.done
