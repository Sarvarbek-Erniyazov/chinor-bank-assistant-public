#!/usr/bin/env bash
# POST_JOB for queue.sh: sync one finished run into its own folder results/runs/<run>/ (mechanics runs, probes).
#   POST_JOB='bash scripts/h200/sync_run.sh' bash scripts/h200/queue.sh <jobfile>
exec bash "$(dirname "${BASH_SOURCE[0]}")/sync_down.sh" "$1" "results/runs/$1"
