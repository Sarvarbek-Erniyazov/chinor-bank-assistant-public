# Local machine: GPU scheduling rules for the shared H200, sourced by queue.sh and run_matrix.sh.
#  - Hard cutoff: a GPU job starts only if now + its estimate <= the cutoff (server clock, "YYYY-MM-DD HH:MM",
#    KST); after the cutoff nothing new starts. The cutoff is read before every launch from CUTOFF_FILE when that
#    file exists (so it can be set while a queue runs), else from CUTOFF; "none" means no cutoff.
#  - One launch.sh run per job, so the GPU lock is released between every pair of jobs.
#  - Before each launch: the lock (<workspace>/GPU_LOCK, "project pid started_at", the only convention
#    GTD uses) must be free, otherwise wait and re-check every 60 s (or stop at the cutoff). If
#    <workspace>/GPU_WANTED exists, the queue starts nothing new and stops with a report (the running job
#    finishes). GPU_WANTED and GTD's lock are only read: never created, edited or deleted from here.
#  - Disk: a job starts only if free space on <workspace> stays >= MIN_FREE_GB (60) after its expected
#    writes (JOB_WRITE_GB, default 5); GTD refuses to launch under 40 GB. Below that, stop and report.
#  - Measured durations are appended to results/raw/gpu_jobs.csv for the next estimates.
# Nothing here kills, pauses or edits a process or a lock of another project.

WS=${CHINOR_WS:-<workspace>}/chinor
# Launch-side scripts of a frozen queue (set by freeze_queue); outside a queue the repo copy is used.
LAUNCH_SH="${LAUNCH_SH:-$WS/repo/scripts/h200/launch.sh}"

# freeze_queue <script> <list> [args...]: queue isolation. Unless already running from a frozen copy, copy
# scripts/h200/ and the list to runs/_queues/<name>/ (local, git-ignored) and the launch-side scripts to
# $WS/runs/_queues/<name>/ (server), rewrite job commands that call scripts/h200/ to the frozen server copy, and
# re-execute <script> from the local frozen copy. Editing the repo's scripts can then never reach a running queue
# (2026-10-29: a queue broke after its script was edited under it; a waiter started a queue; a stopped waiter
# left a second queue running). Waiter scripts never start queues.
freeze_queue() {
    [ -n "${QUEUE_FROZEN:-}" ] && return 0
    local script="$1" list="$2"; shift 2
    local root here_ name qdir
    here_="$(cd "$(dirname "$script")" && pwd)"
    root="$(cd "$here_/../.." && pwd)"
    name="$(basename "$list" .txt)-$(date +%Y%m%dT%H%M%S)"
    qdir="${QUEUE_DIR:-$root/runs/_queues}/$name"
    mkdir -p "$qdir/scripts/h200"
    cp "$here_"/*.sh "$here_"/*.py "$qdir/scripts/h200/"
    sed "s#\(^\| \)scripts/h200/#\1$WS/runs/_queues/$name/scripts/h200/#g" "$list" > "$qdir/$(basename "$list")"
    ssh ${CHINOR_HOST:-<host>} "mkdir -p $WS/runs/_queues/$name/scripts/h200 && tar -xf - -C $WS/runs/_queues/$name/scripts/h200"         < <(tar -cf - -C "$qdir/scripts/h200" .)
    {
        echo "frozen queue $name at $(date '+%F %T'): $(basename "$script") from $qdir"
        echo "  local copy: $qdir/scripts/h200 (git $(git -C "$root" rev-parse --short HEAD 2>/dev/null))"
        echo "  server copy: $WS/runs/_queues/$name/scripts/h200"
        echo "  list: $qdir/$(basename "$list") (job commands point at the server copy)"
    } | tee "$qdir/queue.log"
    QUEUE_FROZEN="$name" REPO_ROOT="$root" LAUNCH_SH="$WS/runs/_queues/$name/scripts/h200/launch.sh"         exec bash "$qdir/scripts/h200/$(basename "$script")" "$qdir/$(basename "$list")" "$@"
}
CUTOFF="${CUTOFF:-none}"
CUTOFF_FILE="${CUTOFF_FILE:-}"
# NO_LAUNCH_AFTER ("YYYY-MM-DD HH:MM", server clock): no new launch after this time, whatever the estimate
NO_LAUNCH_AFTER="${NO_LAUNCH_AFTER:-}"
JOBLOG="${JOBLOG:-results/raw/gpu_jobs.csv}"

server_now() { ssh -n ${CHINOR_HOST:-<host>} 'date +%s'; }
cutoff_value() { if [ -n "$CUTOFF_FILE" ] && [ -s "$CUTOFF_FILE" ]; then head -n 1 "$CUTOFF_FILE"; else echo "$CUTOFF"; fi; }
cutoff_epoch() {  # prints the cutoff as epoch seconds, or a far future time for "none"
    local c; c="$(cutoff_value)"
    if [ "$c" = none ]; then echo 9999999999; else ssh -n ${CHINOR_HOST:-<host>} "date -d '$c' +%s"; fi
}

# hold_after <run> <minutes>: wait until <run> has ended (exit_code written) and <minutes> have passed since,
# e.g. to leave the GPU to GTD's probe and selftest between two of our jobs.
hold_after() {
    local run="$1" min="$2" t_end
    until ssh -n ${CHINOR_HOST:-<host>} "test -f $WS/runs/$run/exit_code" 2>/dev/null; do sleep 30; done
    t_end="$(ssh -n ${CHINOR_HOST:-<host>} "stat -c %Y $WS/runs/$run/exit_code")"
    echo "HOLD: $run ended at $(ssh -n ${CHINOR_HOST:-<host>} "date -d @$t_end +%H:%M"); holding until $(ssh -n ${CHINOR_HOST:-<host>} "date -d @$((t_end + min * 60)) +%H:%M")"
    while [ "$(server_now)" -lt $((t_end + min * 60)) ]; do sleep 30; done
    echo "HOLD over at $(ssh -n ${CHINOR_HOST:-<host>} 'date +%H:%M')"
}

# gpu_wanted: prints a line if <workspace>/GPU_WANTED exists (read only), else nothing
gpu_wanted() {
    ssh -n ${CHINOR_HOST:-<host>} 'f='"${CHINOR_WS:-<workspace>}"'/GPU_WANTED; [ -e "$f" ] && echo "GPU_WANTED present ($(stat -c %y "$f" | cut -c1-16)): $(head -c 200 "$f" | tr "
" " ")"; true'
}

MIN_FREE_GB="${MIN_FREE_GB:-60}"
JOB_WRITE_GB="${JOB_WRITE_GB:-5}"

# disk_short: prints a line if free space minus the job's writes would fall below MIN_FREE_GB, else nothing
disk_short() {
    local free; free="$(ssh -n ${CHINOR_HOST:-<host>} "df -B1G --output=avail ${CHINOR_WS:-<workspace>} | tail -n 1 | tr -d ' '")"
    [ $((free - JOB_WRITE_GB)) -lt "$MIN_FREE_GB" ] && echo "free ${free} GB - ${JOB_WRITE_GB} GB job writes < ${MIN_FREE_GB} GB"
    true
}

# gpu_blocker: prints why the GPU is not free (lock held), or nothing
gpu_blocker() {
    ssh -n ${CHINOR_HOST:-<host>} 'f='"${CHINOR_WS:-<workspace>}"'/GPU_LOCK; [ -f "$f" ] && echo "lock held: $(head -n 1 "$f")"; true'
}

# run_gpu_job <run> <estimate_min> <cmd...>: start only within the cutoff and when the GPU is free;
# wait for the end; return 0 = finished (exit code in $JOB_EXIT), 2 = not started because of the cutoff,
# 3 = not started because GPU_WANTED exists (the queue stops and reports), 4 = not started because of disk space,
# 5 = not started because its weights are not fully in HF_HOME (launch.sh pre-flight, exit 75). A held lock makes
# it wait, not return.
run_gpu_job() {
    local run="$1" est="$2"; shift 2
    local now end blocker wanted short
    while :; do
        now="$(server_now)"; end=$((now + est * 60))
        if [ -n "$NO_LAUNCH_AFTER" ] && [ "$now" -gt "$(ssh -n ${CHINOR_HOST:-<host>} "date -d '$NO_LAUNCH_AFTER' +%s")" ]; then
            echo "DEFER $run: no new launch after $NO_LAUNCH_AFTER"
            return 2
        fi
        if [ "$end" -gt "$(cutoff_epoch)" ]; then
            echo "DEFER $run: estimate ${est} min would end at $(ssh -n ${CHINOR_HOST:-<host>} "date -d @$end +%H:%M") after cutoff $(cutoff_value)"
            return 2
        fi
        short="$(disk_short)"
        if [ -n "$short" ]; then echo "STOP before $run: disk: $short; starting nothing new"; return 4; fi
        wanted="$(gpu_wanted)"   # GTD wants the GPU: the running job (if any) has finished; start nothing new
        if [ -n "$wanted" ]; then echo "STOP before $run: $wanted; starting nothing new"; return 3; fi
        blocker="$(gpu_blocker)"
        [ -z "$blocker" ] && break
        echo "yield before $run: $blocker; re-check in 1 min"; sleep 60
    done
    ssh -n ${CHINOR_HOST:-<host>} "test ! -e $WS/runs/$run" || { echo "run name $run already used; refusing" >&2; return 1; }
    echo "START $run (estimate $est min) at $(ssh -n ${CHINOR_HOST:-<host>} 'date +%H:%M') unless its weights are not ready"
    local lrc=0
    ssh -n ${CHINOR_HOST:-<host>} "REPO_DIR=$WS/repo bash $LAUNCH_SH $run $*" || lrc=$?
    if [ "$lrc" -eq 75 ]; then echo "WAIT $run: weights not ready (lock not taken)"; return 5; fi
    [ "$lrc" -eq 0 ] || return 1
    until ssh -n ${CHINOR_HOST:-<host>} "test -f $WS/runs/$run/exit_code" 2>/dev/null; do sleep 30; done
    JOB_EXIT="$(ssh -n ${CHINOR_HOST:-<host>} "cat $WS/runs/$run/exit_code")"
    local t1; t1="$(server_now)"
    mkdir -p "$(dirname "$JOBLOG")"
    [ -f "$JOBLOG" ] || echo "run,estimate_min,measured_min,exit" > "$JOBLOG"
    echo "$run,$est,$(( (t1 - now + 59) / 60 )),$JOB_EXIT" >> "$JOBLOG"
    echo "END $run exit $JOB_EXIT after $(( (t1 - now + 59) / 60 )) min at $(ssh -n ${CHINOR_HOST:-<host>} 'date +%H:%M')"
}
