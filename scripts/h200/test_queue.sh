#!/usr/bin/env bash
# Local test of the scheduler loops (queue.sh, run_matrix.sh) with a stub ssh; no server is contacted.
#   bash scripts/h200/test_queue.sh
# Regression guard: a `while read ... done < file` loop whose body calls ssh lost every line after the first,
# because ssh read the rest of the job list from stdin (2026-10-28, baseline queue). The stub ssh here reads
# its whole stdin on every call and ignores -n (the worst case), so the loops must read their list on another
# file descriptor. Each loop gets a three-line list; all three jobs must be launched, in order.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
fails=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fails=$((fails + 1)); fi; }

mkdir -p "$tmp/bin"
cat > "$tmp/bin/ssh" <<'STUB'
#!/usr/bin/env bash
# stub: swallow stdin like a real ssh session would, log the remote command, answer what queue_lib asks
cat > /dev/null
cmd="${*: -1}"
echo "$cmd" >> "$STUB_LOG"
case "$cmd" in
    *"date +%s"*)        date +%s ;;
    *"date -d '2000"*)   echo 946684800 ;;                          # a deadline in the past
    *"date -d '"*)       echo $(( $(date +%s) + 86400 )) ;;        # cutoff: tomorrow
    *"date "*)           echo 00:00 ;;
    *"df -B1G"*)         echo 500 ;;                               # free GB
    *"GPU_WANTED"*)      [ -n "${WANTED:-}" ] && echo "GPU_WANTED present (00:00): gtd probe" ;;
    *"launch.sh"*)                                                 # NOT_READY=<run>: weights missing on the first try
        if [ -n "${NOT_READY:-}" ] && [[ "$cmd" == *"launch.sh $NOT_READY "* ]] && [ ! -e "$STUB_LOG.$NOT_READY" ]; then
            touch "$STUB_LOG.$NOT_READY"; echo "waiting for weights: org/x@main: missing"; exit 75
        fi
        echo "started" ;;
    *"cat "*exit_code*)  echo 0 ;;
    *"test ! -e"*)       exit 0 ;;                                 # run name unused
    *"test -f"*exit_code*) exit 0 ;;                               # run finished
    *)                   : ;;                                      # lock / GPU_WANTED checks: nothing held
esac
STUB
chmod +x "$tmp/bin/ssh"
export PATH="$tmp/bin:$PATH" STUB_LOG="$tmp/ssh.log" CUTOFF="2099-01-01 00:00" JOBLOG="$tmp/jobs.csv" QUEUE_DIR="$tmp/queues"

cat > "$tmp/jobs.txt" <<'EOF'
# three jobs
qa 1 echo a
qb 1 echo b
qc 1 echo c
EOF
: > "$STUB_LOG"
POST_JOB=true bash "$root/scripts/h200/queue.sh" "$tmp/jobs.txt" > "$tmp/queue.out" 2>&1 < /dev/null
launched="$(grep -o 'launch.sh q[abc] ' "$STUB_LOG" | awk '{print $2}' | tr '\n' ' ')"
check "queue.sh visits all three jobs in order (got: ${launched})" '[ "$launched" = "qa qb qc " ]'
check "queue.sh reaches its end" 'grep -q "queue .* done" "$tmp/queue.out"'

cat > "$tmp/matrix.txt" <<'EOF'
# config seed estimate
train/configs/tier_s_pilot_lora.yaml 0 1
train/configs/tier_s_pilot_lora.yaml 1 1
train/configs/tier_s_pilot_lora.yaml 2 1
EOF
: > "$STUB_LOG"
echo stand-in > "$tmp/manifest.sha256"
SFT_MANIFEST="$tmp/manifest.sha256" POST_RUN=true bash "$root/scripts/h200/run_matrix.sh" "$tmp/matrix.txt" > "$tmp/matrix.out" 2>&1 < /dev/null
launched="$(grep -o 'launch.sh tier_s_pilot_lora-s[0-9]' "$STUB_LOG" | awk '{print $2}' | tr '\n' ' ')"
check "run_matrix.sh visits all three runs in order (got: ${launched})" '[ "$launched" = "tier_s_pilot_lora-s0 tier_s_pilot_lora-s1 tier_s_pilot_lora-s2 " ]'
check "run_matrix.sh reaches its end" 'grep -q "matrix .* done" "$tmp/matrix.out"'

# optional 4th column (ablation data dir): own run name, passed on to train_eval.sh
printf 'train/configs/tier_s_pilot_lora.yaml 0 1 data/sft/v1_rewrite\n' > "$tmp/ablation.txt"
: > "$STUB_LOG"
SFT_MANIFEST="$tmp/manifest.sha256" POST_RUN=true bash "$root/scripts/h200/run_matrix.sh" "$tmp/ablation.txt" > /dev/null 2>&1 < /dev/null
check "run_matrix.sh: data-dir column -> run tier_s_pilot_lora-s0-v1_rewrite with the data dir passed on" 'grep -q "launch.sh tier_s_pilot_lora-s0-v1_rewrite .*train_eval.sh tier_s_pilot_lora-s0-v1_rewrite train/configs/tier_s_pilot_lora.yaml 0 data/sft/v1_rewrite" "$STUB_LOG"'

: > "$STUB_LOG"
SFT_MANIFEST="$tmp/missing.sha256" POST_RUN=true bash "$root/scripts/h200/run_matrix.sh" "$tmp/matrix.txt" > "$tmp/refuse.out" 2>&1 < /dev/null
rc=$?
check "run_matrix.sh refuses without the SFT v1 manifest (exit $rc, nothing launched)" '[ $rc -eq 3 ] && ! grep -q launch.sh "$STUB_LOG"'

# weights pre-flight (launch.sh exit 75): queue.sh runs the next ready job and comes back; run_matrix.sh retries in order
: > "$STUB_LOG"
NOT_READY=qb WEIGHTS_RECHECK_S=0 POST_JOB=true bash "$root/scripts/h200/queue.sh" "$tmp/jobs.txt" > "$tmp/queue2.out" 2>&1 < /dev/null
launched="$(grep -o 'launch.sh q[abc] ' "$STUB_LOG" | awk '{print $2}' | tr '
' ' ')"
check "queue.sh: qb not ready -> qa, qc run first, qb retried (got: ${launched})" '[ "$launched" = "qa qb qc qb " ] && grep -q "WAIT qb" "$tmp/queue2.out"'
: > "$STUB_LOG"
NOT_READY=tier_s_pilot_lora-s1 WEIGHTS_RECHECK_S=0 SFT_MANIFEST="$tmp/manifest.sha256" POST_RUN=true     bash "$root/scripts/h200/run_matrix.sh" "$tmp/matrix.txt" > "$tmp/matrix2.out" 2>&1 < /dev/null
launched="$(grep -o 'launch.sh tier_s_pilot_lora-s[0-9]' "$STUB_LOG" | awk '{print $2}' | sed 's/tier_s_pilot_lora-//' | tr '
' ' ')"
check "run_matrix.sh: s1 not ready -> waits and retries s1 before s2 (got: ${launched})" '[ "$launched" = "s0 s1 s1 s2 " ]'

# NO_LAUNCH_AFTER in the past: nothing is launched
: > "$STUB_LOG"
NO_LAUNCH_AFTER="2000-01-01 00:00" POST_JOB=true bash "$root/scripts/h200/queue.sh" "$tmp/jobs.txt" > "$tmp/nla.out" 2>&1 < /dev/null
check "NO_LAUNCH_AFTER passed: no launch, queue stops with a DEFER line" '! grep -q "launch.sh q" "$STUB_LOG" && grep -q "DEFER qa: no new launch after" "$tmp/nla.out"'

# GPU_WANTED present: nothing is launched, the queue stops and says why
: > "$STUB_LOG"
WANTED=1 POST_JOB=true bash "$root/scripts/h200/queue.sh" "$tmp/jobs.txt" > "$tmp/wanted.out" 2>&1 < /dev/null
check "GPU_WANTED present: no launch, queue stops with a report" '! grep -q "launch.sh q" "$STUB_LOG" && grep -q "queue stopped at qa (GPU_WANTED present" "$tmp/wanted.out"'

# queue isolation: the queue runs from a frozen copy; editing the repo's scripts while it runs changes nothing
cp -r "$root/scripts/h200" "$tmp/repo_scripts_backup"
mkdir -p "$tmp/slowbin"; cat > "$tmp/slowbin/ssh" <<'STUB2'
#!/usr/bin/env bash
cat > /dev/null; cmd="${*: -1}"; echo "$cmd" >> "$STUB_LOG"
case "$cmd" in
    *"date +%s"*) date +%s ;; *"date -d '"*) echo $(( $(date +%s) + 86400 )) ;; *"date "*) echo 00:00 ;;
    *"df -B1G"*) echo 500 ;; *"launch.sh"*) sleep 1; echo started ;; *"cat "*exit_code*) echo 0 ;; *) : ;;
esac
STUB2
chmod +x "$tmp/slowbin/ssh"
: > "$STUB_LOG"
PATH="$tmp/slowbin:$PATH" POST_JOB=true bash "$root/scripts/h200/queue.sh" "$tmp/jobs.txt" > "$tmp/iso.out" 2>&1 < /dev/null &
qpid=$!
sleep 2
printf '#!/usr/bin/env bash
echo BROKEN; exit 99
' > "$root/scripts/h200/queue_lib.sh"   # "edit" the repo copy mid-run
wait "$qpid"
cp "$tmp/repo_scripts_backup/queue_lib.sh" "$root/scripts/h200/queue_lib.sh"               # restore
launched="$(grep -o 'launch.sh q[abc] ' "$STUB_LOG" | awk '{print $2}' | tr '
' ' ')"
check "isolation: queue finishes all jobs although queue_lib.sh was overwritten mid-run (got: ${launched})" '[ "$launched" = "qa qb qc " ] && ! grep -q BROKEN "$tmp/iso.out"'
check "isolation: frozen copy and log under runs/_queues/<name>/" 'ls "$tmp/queues"/jobs-*/queue.log >/dev/null 2>&1 && ls "$tmp/queues"/jobs-*/scripts/h200/launch.sh >/dev/null 2>&1'
check "isolation: launches go through the frozen server copy" 'grep -q "runs/_queues/jobs-.*/scripts/h200/launch.sh qa" "$STUB_LOG"'

# isolation: job commands calling scripts/h200/ are rewritten to the frozen server copy, keeping the space before
# the path (2026-10-29: a lost backreference became a control byte and both 14B probes failed with exit 127)
printf 'qp 1 bash scripts/h200/probe.sh qp train/configs/x.yaml
' > "$tmp/probejobs.txt"
: > "$STUB_LOG"
POST_JOB=true bash "$root/scripts/h200/queue.sh" "$tmp/probejobs.txt" > /dev/null 2>&1 < /dev/null
frozen="$(ls "$tmp/queues"/probejobs-*/probejobs.txt)"
check "isolation: rewritten job command keeps 'bash <space>/…/runs/_queues/…/scripts/h200/probe.sh'" 'grep -q "^qp 1 bash ${CHINOR_WS:-<workspace>}/chinor/runs/_queues/probejobs-[0-9T]*/scripts/h200/probe.sh qp " "$frozen" && [ "$(LC_ALL=C tr -d "\11\12\40-\176" < "$frozen" | wc -c)" -eq 0 ]'

echo "$fails failure(s)"
[ "$fails" -eq 0 ]
