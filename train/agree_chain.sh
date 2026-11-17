#!/bin/bash
cd /c/agent/nlsql-lab
export PATH=$PATH:/c/Users/keyan/.lmstudio/bin
export LMSTUDIO_BASE_URL=http://127.0.0.1:1235/v1
# wait for open-agree to finish: its summary file is written last, only when the run completes.
# (An earlier version waited for any python3.13.exe to disappear, which also matched unrelated processes and broke when the run died.)
while [ ! -f runs/hybrid-open-agree.summary.json ]; do sleep 60; done
./venv/Scripts/python.exe scripts/run_hybrid.py --label sealed-agree-heldout --policy sealed --agreement --sets heldout >> runs/hybrid-sealed-agree.log 2>&1
lms unload --all > /dev/null 2>&1
touch train/hybrid_agree.done
