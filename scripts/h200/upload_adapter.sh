#!/usr/bin/env bash
# Upload a run's adapter from the H200 to the Hugging Face Hub.
#   HF_TOKEN=... bash scripts/h200/upload_adapter.sh <run_name> <hf_repo> [subdir]     (on the local machine)
# The token is read from the local environment, sent over the ssh session's stdin (never on a command
# line, never echoed or written to a file) and exists on the server only in the environment of the
# single upload process. The adapter is taken from results/<run_name>/<subdir> (default: adapter).
# New repositories are created private.
set -euo pipefail
ws=${CHINOR_WS:-<workspace>}/chinor

if [ "${1:-}" = "--remote" ]; then
    shift
    run="$1"; repo="$2"; sub="${3:-adapter}"
    IFS= read -r tok || true
    [ -n "$tok" ] || { echo "no token received; refusing" >&2; exit 1; }
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    source "$here/env.sh"
    dir="$ws/results/$run/$sub"
    [ -d "$dir" ] || { echo "no adapter at $dir" >&2; exit 1; }
    if command -v hf >/dev/null; then cli=(hf upload); else cli=(huggingface-cli upload); fi
    HF_TOKEN="$tok" "${cli[@]}" "$repo" "$dir" . --repo-type model --private \
        --commit-message "adapter from run $run (commit $(cat "$ws/repo/COMMIT" 2>/dev/null || echo unknown))"
    exit
fi

run="${1:-}"; repo="${2:-}"; sub="${3:-adapter}"
[[ "$run" =~ ^[A-Za-z0-9._-]+$ && "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ && "$sub" =~ ^[A-Za-z0-9._/-]+$ ]] \
    || { echo "usage: HF_TOKEN=... upload_adapter.sh <run_name> <user/repo> [subdir]" >&2; exit 2; }
[ -n "${HF_TOKEN:-}" ] || { echo "HF_TOKEN is not set in this shell; refusing" >&2; exit 1; }
printf '%s\n' "$HF_TOKEN" | ssh ${CHINOR_HOST:-<host>} "bash $ws/repo/scripts/h200/upload_adapter.sh --remote $run $repo $sub"
