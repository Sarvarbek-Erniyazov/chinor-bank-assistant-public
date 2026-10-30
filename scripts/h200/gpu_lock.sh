# GPU lock shared with the GTD project. Sourced by launch.sh and the lock test.
# Lock file ($GPU_LOCK, default <workspace>/GPU_LOCK): one line "project pid started_at".
# Rules: never edit or delete a lock held by a live PID of another project; a lock whose PID is
# dead is stale and may be removed; chinor only releases a lock whose line names its own PID.

GPU_LOCK="${GPU_LOCK:-${CHINOR_WS:-<workspace>}/GPU_LOCK}"
LOCK_PROJECT="${LOCK_PROJECT:-chinor}"

pid_alive() {
    # /proc works for PIDs of other users too (kill -0 would fail with EPERM there).
    [ -n "${1:-}" ] && [ "$1" -gt 0 ] 2>/dev/null && { [ -d "/proc/$1" ] || kill -0 "$1" 2>/dev/null; }
}

lock_read() {
    # prints "project pid started_at" or nothing
    [ -f "$GPU_LOCK" ] && head -n 1 "$GPU_LOCK" 2>/dev/null || true
}

# lock_acquire <pid>: 0 = taken by <pid>, 1 = held by a live process (message printed).
lock_acquire() {
    local pid="$1" line proj hpid since
    for _ in 1 2 3; do
        if ( set -o noclobber; printf '%s %s %s\n' "$LOCK_PROJECT" "$pid" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$GPU_LOCK" ) 2>/dev/null; then
            return 0
        fi
        line="$(lock_read)"
        read -r proj hpid since <<< "$line"
        if pid_alive "$hpid"; then
            echo "GPU lock held by project '${proj:-?}' pid ${hpid:-?} since ${since:-?} ($GPU_LOCK); not starting." >&2
            return 1
        fi
        # stale: remove only if the file still holds the same dead-PID line
        if [ "$(lock_read)" = "$line" ]; then
            echo "removing stale GPU lock: '$line' (pid ${hpid:-?} is not running)" >&2
            rm -f -- "$GPU_LOCK"
        fi
    done
    echo "could not take GPU lock $GPU_LOCK" >&2
    return 1
}

# lock_handover <old_pid> <new_pid>: rewrite our own line with the run's PID.
lock_handover() {
    local proj hpid since
    read -r proj hpid since <<< "$(lock_read)"
    [ "$proj" = "$LOCK_PROJECT" ] && [ "$hpid" = "$1" ] || return 1
    printf '%s %s %s\n' "$LOCK_PROJECT" "$2" "$since" > "$GPU_LOCK.tmp.$$" && mv -f -- "$GPU_LOCK.tmp.$$" "$GPU_LOCK"
}

# lock_release <pid>: remove the lock only if it is ours and names <pid>.
lock_release() {
    local proj hpid since
    read -r proj hpid since <<< "$(lock_read)"
    if [ "$proj" = "$LOCK_PROJECT" ] && [ "$hpid" = "$1" ]; then
        rm -f -- "$GPU_LOCK"
    fi
}
