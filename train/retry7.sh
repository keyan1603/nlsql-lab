#!/bin/bash
cd /c/agent/nlsql-lab
# wait until the XiYan-7B agent has had no eval running for 10 consecutive minutes
idle=0
while [ $idle -lt 2 ]; do
  if powershell -c "if (Get-CimInstance Win32_Process | ?{\$_.CommandLine -match '[r]un_eval.py|[s]erve_hf.py|[t]rain_lora.py'}) {exit 1} else {exit 0}"; then idle=$((idle+1)); else idle=0; fi
  sleep 30
done
lms unload --all > /dev/null 2>&1
sleep 10
./venv-train/Scripts/python.exe train/serve_hf.py --base train/base_xiyan3b --adapter train/out/run7_xiyan3b/epoch1 --port 18235 > train/serve7r2.log 2>&1 &
sleep 150
export LMSTUDIO_BASE_URL=http://127.0.0.1:18235/v1
for s in core hard hard2 decline; do ./venv/Scripts/python.exe scripts/run_eval.py --model tuned-run7_xiyan3b-epoch1 --prompt tuned --max-tokens 512 --retry 2 --set $s --label tuned7r2-$s > train/score7r2_$s.log 2>&1; done
taskkill //F //IM python3.13.exe > /dev/null 2>&1
./venv/Scripts/python.exe scripts/route_eval.py --local-run tuned7r2 > train/route7.log 2>&1
echo done > train/score7r2.done
