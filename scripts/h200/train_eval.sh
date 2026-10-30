#!/usr/bin/env bash
# On the H200, inside launch.sh: one SFT run followed by its Protocol-A evaluation.
#   bash scripts/h200/launch.sh <run> bash scripts/h200/train_eval.sh <run> <config> <seed>
# $CHINOR/results/<run>/train/   sft.py output (run.json, loss.csv, adapter/, ckpt/)
# $CHINOR/results/<run>/eval/<run>/   answers.jsonl, run.json of the adapter under Protocol A
# TRAIN_PY and EVAL_PY default to chinor/venv-gen: train/sft.py uses transformers.Trainer without TRL or
# datasets, which cannot run on the image's NumPy 1 (ADR-020).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
run="${1:?usage: train_eval.sh <run> <config> <seed> [data_dir]}"; config="${2:?config}"; seed="${3:?seed}"
data_dir="${4:-}"   # default data/sft/v1; data/sft/v1_rewrite for the rewrite ablation only
TPY="${TRAIN_PY:-$CHINOR/venv-gen/bin/python}"
EPY="${EVAL_PY:-$CHINOR/venv-gen/bin/python}"
out="$CHINOR/results/$run"
cd "${REPO_DIR:-$CHINOR/repo}"   # the synced repo, also when this script runs from a frozen queue copy
model="$("$EPY" -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["model"])' "$config")"
# QLoRA adapters are evaluated on the NF4 base they were trained on (run_eval --quant 4bit: NF4, double quant)
quant="$("$EPY" -c 'import sys, yaml; print("4bit" if yaml.safe_load(open(sys.argv[1])).get("quant") == "nf4" else "none")' "$config")"

echo "=== train $run ($config, seed $seed) $(date -u +%FT%TZ)"
"$TPY" train/sft.py --config "$config" --seed "$seed" --out "$out/train" ${data_dir:+--data-dir "$data_dir"}
if [ -d "$out/train/model" ]; then   # full fine-tuning: evaluate the saved weights, base tokenizer
    echo "=== eval $run (full fine-tuned weights, Protocol A) $(date -u +%FT%TZ)"
    "$EPY" eval/run_eval.py --model "$out/train/model" --tokenizer "$model" --adapter none --arm "$run" \
        --protocol A --dtype bf16 --batch-size 32 --out-dir "$out/eval/$run"
else
    echo "=== eval $run ($model + adapter, quant $quant, Protocol A) $(date -u +%FT%TZ)"
    "$EPY" eval/run_eval.py --model "$model" --adapter "$out/train/adapter" --quant "$quant" --arm "$run" \
        --protocol A --dtype bf16 --batch-size 32 --out-dir "$out/eval/$run"
fi
echo "=== done $run $(date -u +%FT%TZ)"
