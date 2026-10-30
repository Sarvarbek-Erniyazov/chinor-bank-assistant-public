#!/usr/bin/env bash
# On the H200, inside launch.sh: gate before the special-token reruns (ADR-023 amendment). Qwen3-1.7B-Base rsLoRA
# with trainable <|im_start|>/<|im_end|> rows, 100 steps on SFT v1 (no val eval), then Protocol-A greedy generation
# on 10 eval items (every 22nd of the 220: all blocks). Pass: >= 9 / 10 answers stop on <|im_end|>.
#   bash scripts/h200/launch.sh <run> bash scripts/h200/gate_tokens.sh <run>
# Writes $CHINOR/results/<run>/gate.json; exit 1 if the gate fails.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
run="${1:?usage: gate_tokens.sh <run>}"; config=train/configs/tier_s_main_rslora_tok.yaml
out="$CHINOR/results/$run"
cd "${REPO_DIR:-$CHINOR/repo}"   # the synced repo, also when this script runs from a frozen queue copy
PYX="${TRAIN_PY:-$CHINOR/venv-gen/bin/python}"
mkdir -p "$out"
"$PYX" train/sft.py --config "$config" --seed 0 --out "$out/train" --max-steps 100 --save-steps 100000 --no-eval || exit $?
"$PYX" -c 'import sys; l = open("eval/eval_set.jsonl").read().splitlines(); open(sys.argv[1], "w").write("\n".join(l[i] for i in range(0, 220, 22)) + "\n")' "$out/gate_items.jsonl"
"$PYX" eval/run_eval.py --model Qwen/Qwen3-1.7B-Base --adapter "$out/train/adapter" --arm "$run" --protocol A \
    --dtype bf16 --batch-size 10 --eval-set "$out/gate_items.jsonl" --out-dir "$out/eval" || exit $?
"$PYX" - "$out" <<'PYEOF'
import collections, json, sys
from pathlib import Path
out = Path(sys.argv[1])
rows = [json.loads(l) for l in (out / "eval" / "answers.jsonl").read_text().splitlines() if l.strip()]
stops = collections.Counter(r["stop_reason"] for r in rows)
res = {"items": len(rows), "stop_reasons": dict(stops), "im_end": stops.get("im_end", 0),
       "pass": stops.get("im_end", 0) >= 9, "rule": ">= 9 / 10 stop on <|im_end|>"}
(out / "gate.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res))
sys.exit(0 if res["pass"] else 1)
PYEOF
