#!/usr/bin/env bash
# Test of the GPU lock in launch.sh with dummy runners. Uses a temporary lock file and run folder,
# never the real <workspace>/GPU_LOCK.
#   bash scripts/h200/test_gpu_lock.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
export GPU_LOCK="$tmp/GPU_LOCK" RUNS_DIR="$tmp/runs" REPO_DIR="$tmp/repo"
mkdir -p "$REPO_DIR" "$RUNS_DIR"
echo testcommit > "$REPO_DIR/COMMIT"
source "$here/gpu_lock.sh"
fails=0
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; fails=$((fails + 1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }
lockpid() { read -r _ p _ <<< "$(lock_read)"; echo "$p"; }
wait_dead() { for _ in $(seq 1 100); do pid_alive "$1" || return 0; sleep 0.1; done; return 1; }

# 1. a live gtd process holds the lock -> chinor refuses, lock untouched
sleep 30 & gtd=$!
echo "gtd $gtd 2026-10-28T10:00:00Z" > "$GPU_LOCK"
out="$(bash "$here/launch.sh" t1 sleep 1 2>&1)"; rc=$?
check "live gtd lock refuses start" '[ $rc -ne 0 ]'
check "refusal names holder and start time" '[[ "$out" == *"gtd"*"$gtd"*"2026-10-28T10:00:00Z"* ]]'
check "gtd lock unchanged" '[ "$(lock_read)" = "gtd $gtd 2026-10-28T10:00:00Z" ]'
check "no run started" '[ ! -f "$RUNS_DIR/t1/pid" ]'
kill "$gtd" 2>/dev/null; wait "$gtd" 2>/dev/null

# 2. gtd's PID is dead -> stale lock removed, chinor runner A takes it under its own PID
bash "$here/launch.sh" runA sleep 3 >/dev/null 2>&1; rc=$?
pa="$(cat "$RUNS_DIR/runA/pid" 2>/dev/null)"
check "stale gtd lock replaced, runner A started" '[ $rc -eq 0 ] && pid_alive "$pa"'
check "lock names project chinor and runner A pid" '[ "$(lock_read | cut -d" " -f1)" = chinor ] && [ "$(lockpid)" = "$pa" ]'

# 3. second dummy runner B while A holds the lock -> refused
out="$(bash "$here/launch.sh" runB sleep 1 2>&1)"; rc=$?
check "runner B refused while A runs" '[ $rc -ne 0 ] && [[ "$out" == *chinor*"$pa"* ]]'

# 4. A exits -> lock released, exit code recorded
wait_dead "$pa"; sleep 0.3
check "lock released after A exits" '[ ! -f "$GPU_LOCK" ]'
check "runner A exit_code 0 in run.json" 'grep -q "\"exit_code\": 0" "$RUNS_DIR/runA/run.json"'

# 5. B now starts; killed with TERM -> lock released
bash "$here/launch.sh" runB sleep 30 >/dev/null 2>&1
pb="$(cat "$RUNS_DIR/runB/pid")"
check "runner B starts once the lock is free" 'pid_alive "$pb" && [ "$(lockpid)" = "$pb" ]'
kill -TERM "$pb"; wait_dead "$pb"; sleep 0.3
check "lock released after B is terminated" '[ ! -f "$GPU_LOCK" ]'
check "runner B exit_code 143" '[ "$(cat "$RUNS_DIR/runB/exit_code")" = 143 ]'

# 6. a command that fails immediately still releases the lock
bash "$here/launch.sh" runC false >/dev/null 2>&1
pc="$(cat "$RUNS_DIR/runC/pid")"; wait_dead "$pc"; sleep 0.3
check "lock released after an instant failure" '[ ! -f "$GPU_LOCK" ] && [ "$(cat "$RUNS_DIR/runC/exit_code")" = 1 ]'

# 7. a finished name is not reused without RESUME=1; NO_GPU_LOCK skips the lock
out="$(bash "$here/launch.sh" runA true 2>&1)"; rc=$?
check "finished run name refused without RESUME=1" '[ $rc -ne 0 ]'
sleep 30 & gtd=$!
echo "gtd $gtd 2026-10-28T11:00:00Z" > "$GPU_LOCK"
NO_GPU_LOCK=1 bash "$here/launch.sh" dl true >/dev/null 2>&1; rc=$?
check "NO_GPU_LOCK job starts and leaves the gtd lock alone" '[ $rc -eq 0 ] && [ "$(lock_read)" = "gtd $gtd 2026-10-28T11:00:00Z" ]'
kill "$gtd" 2>/dev/null; wait "$gtd" 2>/dev/null

cd / && rm -rf -- "$tmp"
echo "$fails failure(s)"
[ "$fails" -eq 0 ]
