#!/usr/bin/env bash
# Copy the local working tree to <host>:<workspace>/chinor/repo/ (no git on the server).
#   bash scripts/h200/sync_up.sh
# Writes COMMIT (HEAD, "-dirty" if the tree has uncommitted changes), skips everything in .rsync-exclude.
# Never deletes on the server. Uses rsync when available, otherwise a tar stream over ssh.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dest=${CHINOR_WS:-<workspace>}/chinor/repo
cd "$root"
commit="$(git rev-parse HEAD)"
[ -n "$(git status --porcelain)" ] && { commit="$commit-dirty"; echo "warning: uncommitted changes; COMMIT=$commit" >&2; }
echo "$commit" > COMMIT


ssh ${CHINOR_HOST:-<host>} "mkdir -p $dest"
if command -v rsync >/dev/null; then
    rsync -rlt --exclude-from=.rsync-exclude ./ "${CHINOR_HOST:-<host>}:$dest/"
else
    tar -czf - --exclude-from=.rsync-exclude . | ssh ${CHINOR_HOST:-<host>} "tar -xzf - -m --no-same-owner -C $dest"
fi
echo "synced $commit -> ${CHINOR_HOST:-<host>}:$dest"
