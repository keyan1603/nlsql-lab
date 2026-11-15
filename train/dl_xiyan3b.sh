#!/bin/bash
cd /c/agent/nlsql-lab/train/base_xiyan3b
for f in $(cat /tmp/xi3_files.txt); do
  mkdir -p "$(dirname "$f")"
  curl -L -sS -C - -o "$f" "https://huggingface.co/XGenerationLab/XiYanSQL-QwenCoder-3B-2502/resolve/main/$f" || exit 1
done
echo finished > dl.done
