#!/usr/bin/env bash
# Release the H200 workspace at the end of the project. Run on the local machine; every server step goes over ssh.
#   bash scripts/h200/release_server.sh               dry run (default): what would be deleted, with sizes; deletes nothing
#   bash scripts/h200/release_server.sh --check-sync  compare the server's results/runs listing with the local copy
#   bash scripts/h200/release_server.sh --execute     delete, after typing the confirmation phrase; free disk before/after
# Deletes: the Chinor workspace ($CHINOR_WS/chinor: repo copy, runs, results incl. adapters and full-FT weights, venvs)
# and the Chinor-only models in the shared HF cache (CHINOR_MODELS). Refuses to touch anything under $CHINOR_WS/gtd,
# the GPU lock, GPU_WANTED, or any cache model that GTD's configs mention (read-only grep of $CHINOR_WS/gtd, excluding
# its environments). Host and workspace: CHINOR_HOST, CHINOR_WS.
set -euo pipefail
HOST="${CHINOR_HOST:-${CHINOR_HOST:-<host>}}"
WS="${CHINOR_WS:-${CHINOR_WS:-<workspace>}}"
CHINOR_MODELS=(Qwen/Qwen3-14B-Base Qwen/Qwen3-4B-Base Qwen/Qwen3-0.6B-Base Qwen/Qwen3-1.7B Qwen/Qwen3-14B)
mode="${1:---dry-run}"
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

if [ "$mode" = --check-sync ]; then
    remote="$(ssh -n "$HOST" "ls -1 $WS/chinor/results/runs 2>/dev/null; ls -1 $WS/chinor/results" | sort -u)"
    missing=0
    while read -r r; do
        [ -z "$r" ] && continue
        case "$r" in runs|_*|sft-merged*|judge-*|probe-*) continue ;; esac
        if [ ! -d "results/runs/$r" ] && [ ! -d "eval/outputs/$r" ] && [ ! -d "results/raw/$r" ]; then
            echo "not synced locally: $r"; missing=$((missing + 1))
        fi
    done <<< "$remote"
    echo "sync check: $(wc -l <<< "$remote") server entries, $missing not found locally"
    exit $((missing > 0))
fi

# targets: the workspace and each Chinor-only model, minus anything GTD references
plan="$(ssh "$HOST" "WS='$WS' MODELS='${CHINOR_MODELS[*]}' bash -s" <<'REMOTE'
set -u
echo "FREE $(df -B1G --output=avail "$WS" | tail -n 1 | tr -d ' ') GB"
echo "TARGET $(du -sBG "$WS/chinor" 2>/dev/null | cut -f1) $WS/chinor"
for m in $MODELS; do
    d="$WS/hf/hub/models--${m//\//--}"
    [ -d "$d" ] || { echo "ABSENT $m"; continue; }
    # read-only: does any GTD config / script (not its environments) name this model?
    if grep -rIlq --exclude-dir=env --exclude-dir=venv --exclude-dir=.venv --exclude-dir=site-packages --exclude-dir=.git \
           -E "${m//./\.}([^-A-Za-z0-9.]|\$)" "$WS/gtd" 2>/dev/null; then  # whole id: Qwen3-14B must not match Qwen3-14B-Base
        echo "KEEP $m (referenced by GTD)"; continue
    fi
    size="$(for l in $(find "$d" -type l); do readlink -f "$l"; done | sort -u | xargs -r du -cBG 2>/dev/null | tail -n 1 | cut -f1)"
    echo "TARGET ${size:-0G} $d (+ its blobs)"
done
REMOTE
)"
echo "$plan"
case "$plan" in *"$WS/gtd"*|*GPU_LOCK*|*GPU_WANTED*) echo "refusing: a target touches gtd/ or the lock" >&2; exit 2 ;; esac
[ "$mode" = --dry-run ] && { echo "dry run: nothing deleted. Run with --execute to delete the TARGET lines."; exit 0; }
[ "$mode" = --execute ] || { echo "unknown mode $mode" >&2; exit 2; }

ssh -n "$HOST" "test ! -f '$WS/GPU_LOCK' || ! grep -q '^chinor ' '$WS/GPU_LOCK'" || { echo "refusing: Chinor holds the GPU lock" >&2; exit 2; }
read -r -p "Type DELETE CHINOR to delete the TARGET lines above: " answer
[ "$answer" = "DELETE CHINOR" ] || { echo "not confirmed; nothing deleted"; exit 1; }
targets="$(grep '^TARGET' <<< "$plan" | awk '{print $3}')"
ssh "$HOST" "WS='$WS' TARGETS='$targets' bash -s" <<'REMOTE'
set -eu
before="$(df -B1G --output=avail "$WS" | tail -n 1 | tr -d ' ')"
for t in $TARGETS; do
    case "$t" in "$WS/gtd"*|"$WS/GPU_LOCK"|"$WS/GPU_WANTED") echo "skip $t"; continue ;; esac
    if [ -d "$t/blobs" ]; then  # a cache model: its blob targets first (they may live in the shared blob store)
        for l in $(find "$t" -type l); do f="$(readlink -f "$l")"; [ -f "$f" ] && rm -f -- "$f"; done
        rm -rf -- "$WS/hf/hub/.locks/$(basename "$t")"
    fi
    rm -rf -- "$t" && echo "deleted $t"
done
sleep 90  # NFS free-space lag
echo "free disk: before ${before} GB, after $(df -B1G --output=avail "$WS" | tail -n 1 | tr -d ' ') GB"
REMOTE
