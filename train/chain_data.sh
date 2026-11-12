#!/bin/bash
# Resumable chain: finish the blind-answer backlog, finish round 1 generation, then round 2, answering each batch of new candidates.
cd /c/agent/nlsql-lab
export GEMINI_DAILY_CAP=${GEMINI_DAILY_CAP:-900}
P=./venv/Scripts/python.exe
S=scripts/make_training_data.py
$P $S answer --max-requests 60
$P $S generate --max-requests 60 --rounds 1
$P $S verify
$P $S answer --max-requests 60
$P $S generate --max-requests 100 --rounds 2
$P $S verify
$P $S answer --max-requests 100
echo CHAINDONE
