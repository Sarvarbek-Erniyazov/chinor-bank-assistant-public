#!/usr/bin/env bash
# Local machine: run a list of (config, seed) pairs on the H200, each as its own launch.sh run
# (train + Protocol-A eval, train_eval.sh), under the scheduling rules of queue_lib.sh: hard cutoff,
# lock and GPU_WANTED check before every launch, GPU lock released between runs. Each run is synced
# down when it ends.
#   CUTOFF='2026-10-29 01:45' bash scripts/h200/run_matrix.sh <matrix-file>
# Matrix file: one "<config> <seed> <estimate_min> [data_dir]" per line (# comments allowed). Run name:
# <config stem>-s<seed>, plus -<data_dir basename> when a data dir is given (the v1_rewrite ablation);
# names are never reused (a used name is refused).
# Per run, locally: results/runs/<run>/ (train run.json, loss.csv; eval run.json), eval/outputs/<run>/
# (answers.jsonl, run.json, scores.jsonl), adapters/tier_s/<run>/ (git-ignored).
# A run deferred by the cutoff stops the matrix; a failed run stops it too.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/queue_lib.sh"
freeze_queue "${BASH_SOURCE[0]}" "$@"   # re-executes from runs/_queues/<name>/ (queue isolation)
cd "${REPO_ROOT:?}"
matrix="${1:?usage: run_matrix.sh <matrix-file>}"
# Training runs use the committed SFT v1 data only: refuse before C1 §4 has written and committed its manifest.
# SFT_MANIFEST overrides the path in scripts/h200/test_queue.sh only.
manifest="${SFT_MANIFEST:-data/sft/v1/manifest.sha256}"
if [ ! -f "$manifest" ] || { [ -z "${SFT_MANIFEST:-}" ] && ! git ls-files --error-unmatch "$manifest" >/dev/null 2>&1; }; then
    echo "refusing: $manifest is missing or not committed (C1 §4 not assembled yet)" >&2; exit 3
fi

post_run() {  # sync one finished run down, collect its eval and adapter, score it
    local run="$1"
    bash "$here/sync_down.sh" "$run" "results/runs/$run"
    mkdir -p "eval/outputs/$run"
    cp "results/runs/$run/eval/$run/answers.jsonl" "results/runs/$run/eval/$run/run.json" "eval/outputs/$run/"
    # LoRA adapters only; full fine-tuned weights stay on the server (results/<run>/train/model)
    if ssh -n ${CHINOR_HOST:-<host>} "test -d $WS/results/$run/train/adapter"; then
        mkdir -p "${ADAPTER_DIR:-adapters/tier_s}/$run"
        ssh -n ${CHINOR_HOST:-<host>} "tar -czf - -C $WS/results/$run/train/adapter ." | tar -xzf - -C "${ADAPTER_DIR:-adapters/tier_s}/$run"
    fi
    "$PY" eval/score.py --arm "$run"
    drop_checkpoints "$run"
}

# Checkpoint rule (author's approval 2026-10-29): once the final adapter is synced and its SHA-256 matches on both
# sides (LoRA / QLoRA), or the final full-FT weights are hashed on the server, the run's intermediate checkpoints
# on the server are deleted. Hashes go to results/adapter_sha256.tsv / results/model_sha256.tsv. On a mismatch
# nothing is deleted.
drop_checkpoints() {
    local run="$1" h l
    if ssh -n ${CHINOR_HOST:-<host>} "test -d $WS/results/$run/train/adapter"; then
        h="$(ssh -n ${CHINOR_HOST:-<host>} "sha256sum $WS/results/$run/train/adapter/adapter_model.safetensors" | cut -c1-64)"
        l="$(sha256sum "${ADAPTER_DIR:-adapters/tier_s}/$run/adapter_model.safetensors" | cut -c1-64)"
        [ -n "$h" ] && [ "$h" = "$l" ] || { echo "KEEP checkpoints of $run: adapter hash mismatch (server $h, local $l)" >&2; return 0; }
        printf '%s\t%s\tlocal = server, %s\n' "$run" "$h" "$(date +%F)" >> results/adapter_sha256.tsv
    elif ssh -n ${CHINOR_HOST:-<host>} "test -d $WS/results/$run/train/model"; then
        ssh -n ${CHINOR_HOST:-<host>} "cd $WS/results/$run/train/model && sha256sum *.safetensors" \
            | awk -v r="$run" -v d="$(date +%F)" '{print r"\t"$2"\t"$1"\tserver, "d}' >> results/model_sha256.tsv
        grep -q "^$run	" results/model_sha256.tsv || { echo "KEEP checkpoints of $run: no weight hashes" >&2; return 0; }
    else
        return 0
    fi
    ssh -n ${CHINOR_HOST:-<host>} "rm -rf -- $WS/results/$run/train/ckpt" && echo "deleted checkpoints of $run (final weights hashed)"
}
PY="${LOCAL_PY:-.venv/Scripts/python}"

while read -r config seed est data_dir _ <&3; do
    [[ -z "${config:-}" || "$config" == \#* ]] && continue
    run="$(basename "$config" .yaml)-s$seed${data_dir:+-$(basename "$data_dir")}"
    # weights not ready (rc 5): the matrix is ordered, so wait and retry the same run
    until run_gpu_job "$run" "$est" bash scripts/h200/train_eval.sh "$run" "$config" "$seed" $data_dir; rc=$?; [ $rc -ne 5 ]; do
        sleep "${WEIGHTS_RECHECK_S:-60}"
    done
    [ $rc -eq 2 ] && { echo "matrix stopped at $run (cutoff)"; exit 0; }
    [ $rc -eq 3 ] && { echo "matrix stopped at $run (GPU_WANTED present; nothing new started)"; exit 0; }
    [ $rc -eq 4 ] && { echo "stopped at $run (disk below the 60 GB floor)"; exit 0; }
    [ $rc -ne 0 ] && { echo "launch of $run failed" >&2; exit 1; }
    if [ "$JOB_EXIT" != 0 ]; then
        bash "$here/sync_down.sh" "$run" "results/runs/$run"
        echo "run $run failed (exit $JOB_EXIT); log in results/raw/$run/log.txt" >&2; exit 1
    fi
    ${POST_RUN:-post_run} "$run"   # POST_RUN: override in scripts/h200/test_queue.sh
done 3< "$matrix"
echo "matrix $matrix done"
