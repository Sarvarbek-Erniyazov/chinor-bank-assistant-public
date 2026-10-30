#!/usr/bin/env bash
# Local machine: run a list of GPU jobs on the H200 one launch.sh run at a time under the scheduling rules
# of queue_lib.sh (cutoff, lock and GPU_WANTED check, lock released between jobs), syncing each down.
#   [CUTOFF_FILE=f] [POST_JOB=sync_run] [HOLD_AFTER=<run> HOLD_MIN=20] bash scripts/h200/queue.sh <jobfile> [dest]
# The queue first freezes itself (queue_lib.sh freeze_queue) and runs only from runs/_queues/<name>/.
# HOLD_AFTER: before the first job, wait until that run has ended plus HOLD_MIN minutes (GPU left to GTD).
# Job file: one "<run> <estimate_min> <cmd...>" per line, # comments allowed; cmd runs from the synced repo.
# Each finished run is synced with sync_down.sh <run> [dest]. A deferred job stops the queue (later jobs in
# the file are lower priority). A failed job is reported and the queue continues.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/queue_lib.sh"
freeze_queue "${BASH_SOURCE[0]}" "$@"   # re-executes from runs/_queues/<name>/ (queue isolation)
cd "${REPO_ROOT:?}"
jobs="${1:?usage: queue.sh <jobfile> [dest]}"; dest="${2:-eval/outputs}"
[ -n "${HOLD_AFTER:-}" ] && hold_after "$HOLD_AFTER" "${HOLD_MIN:-20}"
# jobs whose weights are not ready yet (launch.sh exit 75) stay pending; the queue runs the next ready job and
# retries the pending ones every 60 s, in file order
pending=()
while read -r run est cmd <&3; do
    [[ -z "${run:-}" || "$run" == \#* ]] && continue
    pending+=("$run $est $cmd")
done 3< "$jobs"
while [ ${#pending[@]} -gt 0 ]; do
    still=(); progressed=0
    for job in "${pending[@]}"; do
        read -r run est cmd <<< "$job"
        run_gpu_job "$run" "$est" $cmd; rc=$?
        [ $rc -eq 2 ] && { echo "queue stopped at $run (cutoff)"; exit 0; }
        [ $rc -eq 3 ] && { echo "queue stopped at $run (GPU_WANTED present; nothing new started)"; exit 0; }
        [ $rc -eq 4 ] && { echo "queue stopped at $run (disk below the 60 GB floor)"; exit 0; }
        [ $rc -eq 5 ] && { still+=("$job"); continue; }
        progressed=1
        [ $rc -ne 0 ] && { echo "launch of $run failed" >&2; continue; }
        post="${POST_JOB:-sync_down}"   # a name = a script of the frozen copy (sync_down, sync_run); else a command
        if [ -f "$here/$post.sh" ]; then bash "$here/$post.sh" "$run" "$dest"; else $post "$run" "$dest"; fi
    done
    pending=("${still[@]}")
    [ ${#pending[@]} -gt 0 ] && [ $progressed -eq 0 ] && { echo "waiting for weights: ${#pending[@]} job(s); re-check in 1 min"; sleep "${WEIGHTS_RECHECK_S:-60}"; }
done
echo "queue $jobs done"
