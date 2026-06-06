#!/bin/bash
set -o pipefail
tag="${1:?usage: bash arun.sh <tag>}"
cd ~/aaa || exit 1
log="runlog_${tag}.txt"
{
  echo "===== arun ${tag}  $(date -u) ====="
  git pull --rebase --autostash
  echo "----- batch -----"; python3 batch.py "$tag"
  echo "----- analyze -----"; python3 analyze_h1b.py "$tag"
} 2>&1 | tee "$log"
git add -A
git commit -m "run ${tag}" >> "$log" 2>&1
git push >> "$log" 2>&1 || { git pull --rebase --autostash >> "$log" 2>&1 && git push >> "$log" 2>&1; }
echo ">>> DONE ${tag} — Claude에게: ${tag} 푸시함  (읽을 것: analysis_out/${tag}/rows.csv + ${log})"
