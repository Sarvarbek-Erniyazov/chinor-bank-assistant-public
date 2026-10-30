#!/usr/bin/env bash
# On the H200, inside launch.sh: one preference run (train/pref.py) followed by its Protocol-A eval and red-team eval.
#   bash scripts/h200/launch.sh <run> bash scripts/h200/pref_train_eval.sh <run> <config> <seed>
# $CHINOR/results/<run>/train/          pref.py output (run.json, loss.csv, adapter/)
# $CHINOR/results/<run>/eval/<run>/     eval-v1 answers under Protocol A (sft-merged + adapter)
# $CHINOR/results/<run>/eval/rt-<run>/  redteam-v1 answers under Protocol A
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
run="${1:?usage: pref_train_eval.sh <run> <config> <seed>}"; config="${2:?config}"; seed="${3:?seed}"
PY="${TRAIN_PY:-$CHINOR/venv-gen/bin/python}"
out="$CHINOR/results/$run"
cd "${REPO_DIR:-$CHINOR/repo}"
model="$("$PY" -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["model"])' "$config")"
echo "=== train $run ($config, seed $seed) $(date -u +%FT%TZ)"
"$PY" train/pref.py --config "$config" --seed "$seed" --out "$out/train"
for set in eval rt; do
    arm="$run"; es=eval/eval_set.jsonl
    [ "$set" = rt ] && { arm="rt-$run"; es=eval/redteam_set.jsonl; }
    echo "=== eval $arm ($model + adapter, $es, Protocol A) $(date -u +%FT%TZ)"
    "$PY" eval/run_eval.py --model "$model" --adapter "$out/train/adapter" --arm "$arm" --eval-set "$es" \
        --protocol A --dtype bf16 --batch-size 32 --out-dir "$out/eval/$arm"
done
echo "=== done $run $(date -u +%FT%TZ)"
