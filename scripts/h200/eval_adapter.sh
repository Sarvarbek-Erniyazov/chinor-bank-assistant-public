#!/usr/bin/env bash
# On the H200, inside launch.sh: Protocol-A eval of an existing LoRA run's adapter with another system prompt
# (robustness arms). Output: $CHINOR/results/<arm>/<arm>/ (nested, so queue.sh sync_down lands it in eval/outputs/<arm>/).
#   bash scripts/h200/launch.sh <arm> bash scripts/h200/eval_adapter.sh <arm> <source_run> <config> <system_prompt_file>
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
arm="${1:?arm}"; src="${2:?source run}"; config="${3:?config}"; sp="${4:?system prompt file}"
EPY="${EVAL_PY:-$CHINOR/venv-gen/bin/python}"
cd "${REPO_DIR:-$CHINOR/repo}"
model="$("$EPY" -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["model"])' "$config")"
echo "=== eval $arm ($model + $src adapter, system prompt $sp, Protocol A) $(date -u +%FT%TZ)"
"$EPY" eval/run_eval.py --model "$model" --adapter "$CHINOR/results/$src/train/adapter" --arm "$arm" \
    --protocol A --dtype bf16 --batch-size 32 --system-prompt "$sp" --out-dir "$CHINOR/results/$arm/$arm"
echo "=== done $arm $(date -u +%FT%TZ)"
