#!/usr/bin/env bash
# One-time checks of the H200 over ssh; prints a pass/fail table (markdown) and the user packages.
#   bash scripts/h200/check.sh
# Read-only on the server: it lists nothing outside the allowed paths and writes nothing.
set -uo pipefail
ssh ${CHINOR_HOST:-<host>} "CHINOR_WS='${CHINOR_WS:-<workspace>}' bash -s" <<'REMOTE' > "${TMPDIR:-/tmp}/${CHINOR_HOST:-<host>}_check.$$" 2>&1
PY="$(command -v python3 || command -v python)"
row() { printf 'ROW|%s|%s|%s\n' "$1" "$2" "$3"; }
g="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1 | head -n 4 | paste -sd ';' -)"
[[ "$g" == *H200* ]] && row gpu PASS "$g" || row gpu FAIL "$g"
t="$("$PY" -c 'import torch; print(torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available(), "bf16", torch.cuda.is_available() and torch.cuda.is_bf16_supported())' 2>&1 | tail -n 1)"
[[ "$t" == *"available True bf16 True"* ]] && row torch PASS "$PY: $t" || row torch FAIL "$PY: $t"
for u in https://github.com https://huggingface.co/api/models/Qwen/Qwen3-0.6B-Base https://pypi.org/simple/pip/; do
    c="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$u" 2>/dev/null)"
    [[ "$c" =~ ^(200|301|302)$ ]] && row "http $u" PASS "$c" || row "http $u" FAIL "${c:-no response}"
done
for d in ${CHINOR_WS:-<workspace>}/chinor ${CHINOR_WS:-<workspace>}/hf; do
    if [ -d "$d" ]; then row "df $d" PASS "$(df -h --output=size,used,avail,target "$d" | tail -n 1 | tr -s ' ')"
    else row "df $d" PASS "not created yet; filesystem: $(df -h --output=size,used,avail,target ${CHINOR_WS:-<workspace>} | tail -n 1 | tr -s ' ')"; fi
done
row "user site" PASS "$("$PY" -m site --user-site 2>&1) (HOME=$HOME)"
command -v tmux >/dev/null && row tmux PASS "$(tmux -V)" || row tmux FAIL "not installed (runs use nohup; not required)"
command -v setsid >/dev/null && row setsid PASS "$(command -v setsid)" || row setsid FAIL missing
[ -f ${CHINOR_WS:-<workspace>}/GPU_LOCK ] && row "GPU_LOCK" PASS "held: $(head -n 1 ${CHINOR_WS:-<workspace>}/GPU_LOCK)" || row "GPU_LOCK" PASS "free"
echo "PIP_USER_BEGIN"
"$PY" -m pip list --user 2>&1
echo "PIP_USER_END"
REMOTE
rc=$?
out="${TMPDIR:-/tmp}/${CHINOR_HOST:-<host>}_check.$$"
if [ $rc -ne 0 ] && ! grep -q '^ROW|' "$out"; then cat "$out"; rm -f "$out"; echo "ssh failed (exit $rc)" >&2; exit 1; fi
echo "| Check | Result | Detail |"
echo "|---|---|---|"
grep '^ROW|' "$out" | awk -F'|' '{ printf "| %s | %s | %s |\n", $2, $3, $4 }'
echo
echo "pip list --user:"
sed -n '/^PIP_USER_BEGIN$/,/^PIP_USER_END$/p' "$out" | sed '1d;$d'
fails="$(grep -c '^ROW|[^|]*|FAIL' "$out")"
rm -f "$out"
echo
echo "$fails check(s) failed"
