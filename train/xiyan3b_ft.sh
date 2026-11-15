#!/bin/bash
# XiYan-3B adapter: the same two-stage recipe as the Qwen 3B run 6 (run4: train.jsonl; run6: continuation with the terse and counter data).
cd /c/agent/nlsql-lab
until [ -f train/package6.done ] && [ -f train/base_xiyan3b/dl.done ]; do sleep 30; done
sleep 20
./venv-train/Scripts/python.exe train/train_lora.py --base train/base_xiyan3b --out train/out/run7a_xiyan3b --epochs 1 --micro 2 --accum 8 --tok-budget 1300 > train/run7a_xiyan3b.log 2>&1
./venv-train/Scripts/python.exe train/train_lora.py --base train/base_xiyan3b --init train/out/run7a_xiyan3b/epoch1 --train train/data/cont2_train.jsonl --val train/data/cont2_val.jsonl --out train/out/run7_xiyan3b --epochs 1 --lr 1e-4 --micro 2 --accum 8 --tok-budget 1300 > train/run7_xiyan3b.log 2>&1
echo trained > train/xiyan3b_train.done
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base_xiyan3b --adapter train/out/run7_xiyan3b/epoch1 --port 18235 > train/serve7.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in dev2 dev core decline hard hard2; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run7_xiyan3b-epoch1 --prompt tuned --max-tokens 512 --set $s --label tuned7-$s > train/score7_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
echo scored > train/xiyan3b_ft.done
