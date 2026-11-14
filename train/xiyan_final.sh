#!/bin/bash
# Stage C: the one configuration chosen on dev, dev2 and hard (tuned prompt + 4 decline examples + retry 2), run once on the sets selection never saw.
cd /c/agent/nlsql-lab
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
for s in hard2 decline core; do
  ./venv/Scripts/python.exe scripts/run_eval.py --model xiyan --set $s --max-tokens 1024 --label xiyan7b-final-$s --prompt tuned --decline-shots 4 --retry 2 > runs/xiyan7b-final-$s.log 2>&1
  tail -1 runs/xiyan7b-final-$s.log
done
# exploratory only (the guard was rejected on the selection sets): the same plus the decline guard, decline set
./venv/Scripts/python.exe scripts/run_eval.py --model xiyan --set decline --max-tokens 1024 --label xiyan7b-finalguard-decline --prompt tuned --decline-shots 4 --retry 2 --guard > runs/xiyan7b-finalguard-decline.log 2>&1
tail -1 runs/xiyan7b-finalguard-decline.log
echo done > train/xiyan_final.done
