#!/usr/bin/env bash
# POST_JOB for queue.sh (preference runs, pref_train_eval.sh): results/runs/<run>/ (train run.json, loss.csv, eval),
# then eval/outputs/<run>/ and eval/outputs/rt-<run>/ (answers.jsonl, run.json) as for the SFT arms (run_matrix.sh).
#   POST_JOB=sync_pref bash scripts/h200/queue.sh scripts/h200/jobs/pref_v1.txt
set -euo pipefail
run="$1"
bash "$(dirname "${BASH_SOURCE[0]}")/sync_down.sh" "$run" "results/runs/$run"
for arm in "$run" "rt-$run"; do
    src="results/runs/$run/eval/$arm"
    [ -f "$src/answers.jsonl" ] || { echo "sync_pref: no $src/answers.jsonl" >&2; continue; }
    mkdir -p "eval/outputs/$arm"
    cp "$src/answers.jsonl" "$src/run.json" "eval/outputs/$arm/"
done
