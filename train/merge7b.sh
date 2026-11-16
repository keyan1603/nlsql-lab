#!/bin/bash
cd /c/agent/nlsql-lab
PY=./venv-train/Scripts/python.exe
$PY -c "from huggingface_hub import snapshot_download; snapshot_download('XGenerationLab/XiYanSQL-QwenCoder-7B-2504', local_dir='train/base7b')" > train/dl7b.log 2>&1 || { echo FAIL-dl > train/merge7b.fail; exit 1; }
touch train/dl7b.done
$PY train/merge_and_convert.py --base train/base7b --adapter train/out/xiyan7b_kaggle/out/run2/epoch2 --name xiyan7b-ft-e2 --outtype q8_0 > train/merge7b_e2.log 2>&1 || { echo FAIL-merge > train/merge7b.fail; exit 1; }
rm -rf train/out/xiyan7b-ft-e2/*.safetensors
touch train/merge7b_e2.done
