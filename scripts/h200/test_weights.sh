#!/usr/bin/env bash
# Local test of the weights pre-flight in launch.sh with a fake, incomplete HF cache (no server, no Hub).
#   bash scripts/h200/test_weights.sh
# A GPU job whose model is not fully present must not take the GPU lock or create its run folder (exit 75 and
# "waiting for weights"); once the cache is complete the same job starts. Uses a temporary lock file and cache.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'cd /; rm -rf -- "$tmp"' EXIT
export GPU_LOCK="$tmp/GPU_LOCK" RUNS_DIR="$tmp/runs" REPO_DIR="$tmp/repo" HF_HOME="$tmp/hf" CHINOR_HF_HOME="$tmp/hf"
mkdir -p "$REPO_DIR" "$RUNS_DIR"
echo testcommit > "$REPO_DIR/COMMIT"
fails=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fails=$((fails + 1)); fi; }

# fake model org/tiny at revision abc123: manifest says two files, the cache has one full and one partial
snap="$HF_HOME/hub/models--org--tiny/snapshots/abc123"
mkdir -p "$snap"
printf '{"a": 1}' > "$snap/config.json"                         # 8 bytes
head -c 100 /dev/zero > "$snap/model.safetensors"                # 100 of 400 bytes
cat > "$tmp/manifest.json" <<'EOF'
{"org/tiny": {"sha": "abc123", "files": {"config.json": 8, "model.safetensors": 400}}}
EOF
export WEIGHTS_MANIFEST="$tmp/manifest.json"
cmd=(python -c "print('job ran')" --model org/tiny)

out="$(bash "$here/launch.sh" w1 "${cmd[@]}" 2>&1)"; rc=$?
check "incomplete cache: launch refuses with exit 75 (got $rc)" '[ $rc -eq 75 ]'
check "incomplete cache: says which model it waits for" '[[ "$out" == *"waiting for weights: org/tiny@main: incomplete model.safetensors"* ]]'
check "incomplete cache: GPU lock not taken" '[ ! -f "$GPU_LOCK" ]'
check "incomplete cache: no run folder created (name stays free)" '[ ! -e "$RUNS_DIR/w1" ]'

out="$(bash "$here/launch.sh" w2 python -c "print(1)" --model org/absent 2>&1)"; rc=$?
check "model not in the cache at all: refused (exit $rc)" '[ $rc -eq 75 ] && [[ "$out" == *"org/absent@main: not in the cache"* ]]'

head -c 400 /dev/zero > "$snap/model.safetensors"                # download finished
bash "$here/launch.sh" w1 "${cmd[@]}" > /dev/null 2>&1; rc=$?
check "complete cache: the same job starts and takes the lock (exit $rc)" '[ $rc -eq 0 ] && [ -f "$RUNS_DIR/w1/pid" ]'
pid="$(cat "$RUNS_DIR/w1/pid" 2>/dev/null)"
for _ in $(seq 1 300); do [ -f "$RUNS_DIR/w1/exit_code" ] && break; sleep 0.1; done; sleep 0.5
check "complete cache: job ran and released the lock" '[ "$(cat "$RUNS_DIR/w1/exit_code" 2>/dev/null)" = 0 ] && [ ! -f "$GPU_LOCK" ]'

NO_GPU_LOCK=1 bash "$here/launch.sh" w3 python -c "print(1)" --model org/absent > /dev/null 2>&1; rc=$?
check "CPU job (NO_GPU_LOCK=1) skips the pre-flight" '[ $rc -eq 0 ]'

echo "$fails failure(s)"
[ "$fails" -eq 0 ]
