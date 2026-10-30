#!/usr/bin/env bash
# Started by launch.sh only. Takes the GPU lock over from the launcher, runs the command, records the
# exit code and end time in run.json, and releases the lock when it exits (also on SIGTERM/SIGINT).
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
source "$here/gpu_lock.sh"
me=$$
if [ "${USE_LOCK:-0}" = 1 ]; then
    lock_handover "$LAUNCHER_PID" "$me" || { echo "GPU lock was not handed over; not starting" >&2; exit 75; }
fi

child=""
finish() {
    local ec=$1
    "$PY" - "$RUN_DIR/run.json" "$ec" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
p, ec = sys.argv[1], int(sys.argv[2])
run = json.load(open(p))
run["exit_code"] = ec
run["end_time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
json.dump(run, open(p, "w"), indent=2)
PYEOF
    echo "$ec" > "$RUN_DIR/exit_code"
    printf '=== end %s exit %s\n' "$(date -u +%FT%TZ)" "$ec"
    [ "${USE_LOCK:-0}" = 1 ] && lock_release "$me"
}
on_signal() {
    [ -n "$child" ] && kill -TERM "$child" 2>/dev/null && wait "$child" 2>/dev/null
    finish 143; exit 143
}
trap on_signal TERM INT HUP

"$@" &
child=$!
wait "$child"
ec=$?
finish "$ec"
exit "$ec"
