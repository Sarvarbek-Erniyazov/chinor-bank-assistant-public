#!/usr/bin/env bash
# Start one run in the background on the H200.
#   bash scripts/h200/launch.sh <name> <cmd...>
# Creates $CHINOR/runs/<name>/ with log.txt, pid, run.json; the command runs from $CHINOR/repo under
# nohup + setsid, so it survives the SSH session. The GPU lock ($GPU_LOCK) is taken before the start
# and released when the run's process exits; a lock held by a live PID of another project refuses the
# start. NO_GPU_LOCK=1 skips the lock for CPU/network-only jobs (weight downloads).
# RESUME=1 allows reusing the name of a finished run (appends to its log).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
source "$here/gpu_lock.sh"
export PYTHONNOUSERSITE=1   # every job: never read or write the shared user site (~/.local)

name="${1:-}"; shift || true
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] && [ $# -gt 0 ] || { echo "usage: launch.sh <name> <cmd...>" >&2; exit 2; }
repo="${REPO_DIR:-$CHINOR/repo}"
run="${RUNS_DIR:-$CHINOR/runs}/$name"

if [ -f "$run/pid" ] && pid_alive "$(cat "$run/pid")"; then
    echo "run $name is already running (pid $(cat "$run/pid"))" >&2; exit 1
fi
if [ -f "$run/run.json" ] && [ "${RESUME:-0}" != 1 ]; then
    echo "run $name exists ($run); use a new name or RESUME=1" >&2; exit 1
fi
if [ "${NO_GPU_LOCK:-0}" != 1 ]; then
    # pre-flight: every model the command needs must be fully in HF_HOME before the GPU lock is taken;
    # downloads run only as separate CPU jobs (NO_GPU_LOCK=1). Exit 75 = weights not ready, nothing created.
    if ! ( cd "$repo" && "${WEIGHTS_PY:-$PY}" "$here/weights_ready.py" -- "$@" ); then
        echo "not starting $name: weights not ready (GPU lock not taken)" >&2
        exit 75
    fi
fi
mkdir -p "$run"

if [ "${NO_GPU_LOCK:-0}" != 1 ]; then
    lock_acquire $$ || exit 1
    use_lock=1
else
    use_lock=0
fi

commit="$(cat "$repo/COMMIT" 2>/dev/null || echo unknown)"
cmdline="$(printf '%q ' "$@")"
# config hash: the command line plus the content of every argument that is a file in the repo
cfg_hash="$( { printf '%s\n' "$cmdline"; for a in "$@"; do [ -f "$repo/$a" ] && cat "$repo/$a"; [[ "$a" == --*=* ]] && [ -f "$repo/${a#*=}" ] && cat "$repo/${a#*=}"; done; true; } | sha256sum | cut -c1-16)"
argval() { local key="$1"; shift; local prev=""; for a in "$@"; do [ "$prev" = "$key" ] && { echo "$a"; return; }; [[ "$a" == "$key="* ]] && { echo "${a#*=}"; return; }; prev="$a"; done; }
seed="$(argval --seed "$@")"; seed="${seed:-${SEED:-}}"
dtype="$(argval --dtype "$@")"
gpu="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || true)"

RUN_JSON="$run/run.json" "$PY" - "$name" "$commit" "$cfg_hash" "$seed" "$gpu" "$dtype" "$cmdline" "$use_lock" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
name, commit, cfg, seed, gpu, dtype, cmd, lock = sys.argv[1:9]
p = os.environ["RUN_JSON"]
prev = json.load(open(p)) if os.path.exists(p) else None
run = {"name": name, "commit": commit, "config_hash": cfg, "seed": int(seed) if seed.isdigit() else (seed or None),
       "gpu": gpu or None, "dtype": dtype or None, "cmd": cmd.strip(), "gpu_lock": lock == "1",
       "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
       "start_time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
if prev:
    run["previous"] = prev
json.dump(run, open(p, "w"), indent=2)
PYEOF

cd "$repo"
printf '\n=== %s start %s (commit %s)\n$ %s\n' "$name" "$(date -u +%FT%TZ)" "$commit" "$cmdline" >> "$run/log.txt"
setsid_cmd="$(command -v setsid || true)"   # absent only in Git Bash (lock test on Windows)
LAUNCHER_PID=$$ USE_LOCK=$use_lock RUN_DIR="$run" \
    nohup $setsid_cmd bash "$here/run_wrapper.sh" "$@" >> "$run/log.txt" 2>&1 < /dev/null &
child=$!
echo "$child" > "$run/pid"

if [ "$use_lock" = 1 ]; then
    # wait until the wrapper has taken over the lock (or has already finished)
    for _ in $(seq 1 50); do
        read -r _p hp _s <<< "$(lock_read)"
        [ "$hp" != "$$" ] && break
        pid_alive "$child" || break
        sleep 0.1
    done
    lock_release $$   # no-op unless the wrapper never took over
fi
echo "started $name pid $child; log $run/log.txt"
