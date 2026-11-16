#!/usr/bin/env bash
# Copy the local working tree to <host>:<workspace>/chinor/repo/ (no git on the server).
#   bash scripts/h200/sync_up.sh
#   SYNC_LOCAL_DIR=<dir> bash scripts/h200/sync_up.sh    dry run: copy to a local folder instead (no ssh)
# Writes COMMIT (HEAD, "-dirty" if the tree has uncommitted changes), skips everything in .rsync-exclude and in the
# optional untracked .rsync-exclude.local (machine-specific patterns; the script works without it). Refuses to run
# if a path matched by .rsync-exclude.local is tracked. Never deletes on the server. Uses rsync when available,
# otherwise a tar stream over ssh.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dest=${CHINOR_WS:-<workspace>}/chinor/repo
cd "$root"
commit="$(git rev-parse HEAD)"
[ -n "$(git status --porcelain)" ] && { commit="$commit-dirty"; echo "warning: uncommitted changes; COMMIT=$commit" >&2; }
echo "$commit" > COMMIT

excludes=(--exclude-from=.rsync-exclude)
if [ -f .rsync-exclude.local ]; then
    excludes+=(--exclude-from=.rsync-exclude.local)
    while IFS= read -r p; do
        case "$p" in ''|'#'*) continue ;; esac
        if [ -n "$(git ls-files -- "$p" "$p/*")" ]; then echo "a path in .rsync-exclude.local is tracked: $p; refusing" >&2; exit 1; fi
    done < .rsync-exclude.local
fi

if [ -n "${SYNC_LOCAL_DIR:-}" ]; then
    mkdir -p "$SYNC_LOCAL_DIR"
    tar -cf - "${excludes[@]}" . | tar -xf - -m -C "$SYNC_LOCAL_DIR"
    echo "dry run: synced $commit -> $SYNC_LOCAL_DIR"
    exit 0
fi

ssh ${CHINOR_HOST:-<host>} "mkdir -p $dest"
if command -v rsync >/dev/null; then
    rsync -rlt "${excludes[@]}" ./ "${CHINOR_HOST:-<host>}:$dest/"
else
    tar -czf - "${excludes[@]}" . | ssh ${CHINOR_HOST:-<host>} "tar -xzf - -m --no-same-owner -C $dest"
fi
echo "synced $commit -> ${CHINOR_HOST:-<host>}:$dest"
