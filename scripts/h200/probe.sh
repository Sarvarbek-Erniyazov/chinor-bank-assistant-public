#!/usr/bin/env bash
# On the H200, inside launch.sh: a 20-step training throughput probe (no eval) on the provisional assembly;
# records run.json (peak VRAM, tokens/s) and deletes the adapter / checkpoints / weights afterwards.
#   bash scripts/h200/launch.sh <run> bash scripts/h200/probe.sh <run> <config>
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
run="${1:?usage: probe.sh <run> <config>}"; config="${2:?config}"
out="$CHINOR/results/$run"
cd "${REPO_DIR:-$CHINOR/repo}"   # the synced repo, also when this script runs from a frozen queue copy
"${TRAIN_PY:-$CHINOR/venv-gen/bin/python}" train/sft.py --config "$config" --seed 0 --out "$out" \
    --max-steps 20 --save-steps 100000 --no-eval --data-dir data/sft/_provisional
ec=$?
rm -rf -- "$out/adapter" "$out/model" "$out/ckpt"   # probes keep only run.json and loss.csv
exit $ec
