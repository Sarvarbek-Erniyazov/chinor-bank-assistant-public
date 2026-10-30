#!/usr/bin/env bash
# On the H200: state of every run, last 20 log lines, GPU lock and nvidia-smi summary.
#   ssh <host> 'bash <workspace>/chinor/repo/scripts/h200/status.sh [run_name]'
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
source "$here/gpu_lock.sh"
for run in "$CHINOR"/runs/${1:-*}/; do
    [ -f "$run/pid" ] || continue
    name="$(basename "$run")"; pid="$(cat "$run/pid")"
    if pid_alive "$pid"; then state="RUNNING (pid $pid)"
    elif [ -f "$run/exit_code" ]; then state="finished, exit $(cat "$run/exit_code")"
    else state="DEAD without exit code (pid $pid)"; fi
    echo "=== $name: $state"
    [ -n "${1:-}" ] || pid_alive "$pid" || [ ! -f "$run/exit_code" ] || continue
    tail -n 20 "$run/log.txt" 2>/dev/null
done
echo "=== GPU lock: $( [ -f "$GPU_LOCK" ] && lock_read || echo free )"
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null
