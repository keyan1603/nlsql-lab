#!/bin/bash
cd /c/agent/nlsql-lab
./venv-train/Scripts/python.exe train/train_lora.py --base train/base3b --init train/out/run4_3b/epoch1 --train train/data/cont2_train.jsonl --val train/data/cont2_val.jsonl --out train/out/run6_3b --epochs 1 --lr 1e-4 --micro 2 --accum 8 --tok-budget 1300 > train/run6_3b.log 2>&1
serve_and_score() {  # adapter run label sets...
  ad=$1; run=$2; lab=$3; shift 3
  ./venv-train/Scripts/python.exe train/serve_hf.py --base train/base3b --adapter $ad --port 18235 > train/serve_$lab.log 2>&1 &
  sleep 150
  export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
  for s in "$@"; do ./venv/Scripts/python.exe scripts/run_eval.py --model $run --prompt tuned --max-tokens 512 --set $s --label $lab-$s > train/score_${lab}_$s.log 2>&1; done
  taskkill //F //IM python3.13.exe > /dev/null 2>&1
  sleep 10
}
serve_and_score train/out/run6_3b/epoch1 tuned-run6_3b-epoch1 tuned6 dev2 dev core decline hard hard2
serve_and_score train/out/run5_3b/epoch1 tuned-run5_3b-epoch1 tuned5 dev2
serve_and_score train/out/run4_3b/epoch1 tuned-run4_3b-epoch1 tuned4 dev2 dev
echo done > train/score6.done
