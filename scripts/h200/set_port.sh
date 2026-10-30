#!/usr/bin/env bash
# Rewrite the Port (and, if given, HostName) line of the "Host <host>" block in ~/.ssh/config
# (local machine only). Both can change per session; they live only in ~/.ssh/config, never in the repo.
#   bash scripts/h200/set_port.sh <port> [host]
# If the block does not exist yet it is added from scripts/h200/ssh_config_block.txt; the host
# (argument or CHINOR_SSH_HOST) and CHINOR_SSH_USER must then be given for that first run.
set -euo pipefail
port="${1:-}"; host="${2:-}"
[[ "$port" =~ ^[0-9]{1,5}$ ]] || { echo "usage: set_port.sh <port> [host]" >&2; exit 2; }
[ -z "$host" ] || [[ "$host" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "invalid host: $host" >&2; exit 2; }
CHINOR_SSH_HOST="${host:-${CHINOR_SSH_HOST:-}}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cfg="$HOME/.ssh/config"
mkdir -p "$HOME/.ssh"
touch "$cfg"

if ! grep -Eq '^[[:space:]]*Host[[:space:]]+'"${CHINOR_HOST:-<host>}"'[[:space:]]*$' "$cfg"; then
    : "${CHINOR_SSH_HOST:?no ${CHINOR_HOST:-<host>} block yet: set CHINOR_SSH_HOST (and CHINOR_SSH_USER) for the first run}"
    : "${CHINOR_SSH_USER:?no ${CHINOR_HOST:-<host>} block yet: set CHINOR_SSH_USER for the first run}"
    { [ -s "$cfg" ] && echo; sed -e "s/CHINOR_SSH_HOST/$CHINOR_SSH_HOST/" -e "s/CHINOR_SSH_USER/$CHINOR_SSH_USER/" "$here/ssh_config_block.txt"; } >> "$cfg"
    echo "added Host ${CHINOR_HOST:-<host>} block to $cfg"
fi

cp "$cfg" "$cfg.bak"
awk -v port="$port" -v host="$host" '
    /^[[:space:]]*(Host|Match)[[:space:]]/ {
        if (inblk && !done) { print "    Port " port; done = 1 }
        inblk = ($0 ~ /^[[:space:]]*Host[[:space:]]+'"${CHINOR_HOST:-<host>}"'[[:space:]]*$/)
        print; next
    }
    inblk && /^[[:space:]]*Port[[:space:]]+/ { if (!done) { print "    Port " port; done = 1 }; next }
    inblk && host != "" && /^[[:space:]]*HostName[[:space:]]+/ { print "    HostName " host; next }
    { print }
    END { if (inblk && !done) print "    Port " port }
' "$cfg.bak" > "$cfg.tmp"
mv "$cfg.tmp" "$cfg"
chmod 600 "$cfg" 2>/dev/null || true
echo "${CHINOR_HOST:-<host>} Port -> $port${host:+, HostName -> $host}"
awk '/^[[:space:]]*Host[[:space:]]+'"${CHINOR_HOST:-<host>}"'[[:space:]]*$/{p=1;print;next} /^[[:space:]]*(Host|Match)[[:space:]]/{p=0} p' "$cfg"
