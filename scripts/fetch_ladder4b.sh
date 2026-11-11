#!/bin/bash
# Download the seven approved Qwen3-4B-Instruct-2507 quantizations, four at a time, resuming on connection resets.
cd "$(dirname "$0")/.."
R=mradermacher/Qwen3-4B-Instruct-2507-GGUF
fetch() { for i in 1 2 3 4 5 6; do ./venv/Scripts/python scripts/fetch_model.py "$1" "$2" && return 0; sleep 20; done; return 1; }
export -f fetch
printf '%s\n' Q8_0 Q6_K Q5_K_M Q4_K_M Q3_K_M Q3_K_S Q2_K | xargs -P 4 -I{} bash -c "fetch $R Qwen3-4B-Instruct-2507.{}.gguf"
echo FETCHDONE
