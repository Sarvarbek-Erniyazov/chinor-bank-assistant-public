#!/usr/bin/env bash
# Copy a finished run back from the H200.
#   bash scripts/h200/sync_down.sh <run_name> [dest]
# results/<run_name>/ -> <dest>/ (default eval/outputs/, i.e. one folder per arm);
# runs/<run_name>/{log.txt,run.json} -> results/raw/<run_name>/.
# Weights, checkpoints and adapters are not copied (adapters go to the Hub with upload_adapter.sh).
set -euo pipefail
name="${1:-}"
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "usage: sync_down.sh <run_name> [dest]" >&2; exit 2; }
root="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"   # REPO_ROOT: set by a frozen queue
dest="${2:-eval/outputs}"
ws=${CHINOR_WS:-<workspace>}/chinor
cd "$root"
mkdir -p "$dest" "results/raw/$name"
excl=(--exclude=ckpt --exclude=adapter --exclude='*.safetensors' --exclude='*.bin' --exclude='*.pt')
if command -v rsync >/dev/null; then
    rsync -rlt "${excl[@]}" "${CHINOR_HOST:-<host>}:$ws/results/$name/" "$dest/"
    rsync -t "${CHINOR_HOST:-<host>}:$ws/runs/$name/log.txt" "${CHINOR_HOST:-<host>}:$ws/runs/$name/run.json" "results/raw/$name/"
else
    ssh ${CHINOR_HOST:-<host>} "test -d $ws/results/$name && tar -czf - ${excl[*]} -C $ws/results/$name ." | tar -xzf - -C "$dest"
    ssh ${CHINOR_HOST:-<host>} "tar -czf - -C $ws/runs/$name log.txt run.json" | tar -xzf - -C "results/raw/$name"
fi
echo "synced $name -> $dest/ and results/raw/$name/"
