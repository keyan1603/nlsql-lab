#!/bin/bash
# Precondition: train/merge7b.sh finished and the GGUF was imported once with `lms import -y -c --user-repo local/xiyan7b-ft-e2 <gguf>`.
# Score the Kaggle-tuned 7B (epoch 2, Q8_0) with the same configuration as the prompt-only 7B final run, on the pre-registered sets.
cd /c/agent/nlsql-lab
export PATH=$PATH:/c/Users/keyan/.lmstudio/bin
lms unload --all > /dev/null 2>&1
lms load xiyan7b-ft-e2 --gpu 0.5 --identifier xiyan7bft -c 8192 -y > train/load7bft.log 2>&1
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
for s in hard hard2 core decline heldout; do
  ./venv/Scripts/python.exe scripts/run_eval.py --model xiyan7bft --prompt tuned --decline-shots 4 --retry 2 --max-tokens 1024 --set $s --label xiyan7bft-e2-$s > runs/xiyan7bft-e2-$s.log 2>&1
done
lms unload --all > /dev/null 2>&1
ok=1
for s in core hard hard2 heldout decline; do [ -f runs/xiyan7bft-e2-$s.summary.json ] || ok=0; done
[ "$ok" = 1 ] && touch train/score7b_ft.done || echo "scoring incomplete, no marker written" >&2
