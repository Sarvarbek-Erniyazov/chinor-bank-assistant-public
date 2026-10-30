#!/usr/bin/env bash
# On the H200, inside launch.sh: determinism check. The dry-run config is trained twice with the same seed on the
# provisional assembly (20 steps, no eval); per-step losses and the adapter SHA-256 are compared.
#   bash scripts/h200/launch.sh <run> bash scripts/h200/determinism.sh <run> [config]
# Writes $CHINOR/results/<run>/determinism.json (+ both loss.csv / run.json); adapters are deleted after hashing.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
run="${1:?usage: determinism.sh <run> [config]}"; config="${2:-train/configs/tier_s_pilot_lora.yaml}"
out="$CHINOR/results/$run"
cd "${REPO_DIR:-$CHINOR/repo}"   # the synced repo, also when this script runs from a frozen queue copy
PYX="${TRAIN_PY:-$CHINOR/venv-gen/bin/python}"
for k in a b; do
    "$PYX" train/sft.py --config "$config" --seed 0 --out "$out/$k" --max-steps 20 --save-steps 100000 --no-eval \
        --data-dir data/sft/_provisional || exit $?
done
"$PYX" - "$out" <<'PYEOF'
import csv, hashlib, json, sys
from pathlib import Path
out = Path(sys.argv[1])
def losses(k):
    return {int(r["step"]): float(r["loss"]) for r in csv.DictReader(open(out / k / "loss.csv")) if r["loss"]}
def sha(k):
    return hashlib.sha256((out / k / "adapter" / "adapter_model.safetensors").read_bytes()).hexdigest()
la, lb = losses("a"), losses("b")
steps = sorted(set(la) | set(lb))
diff = {s: (la.get(s), lb.get(s)) for s in steps if la.get(s) != lb.get(s)}
res = {"config": "train/configs/tier_s_pilot_lora.yaml", "seed": 0, "steps": 20, "data": "data/sft/_provisional",
       "losses_a": la, "losses_b": lb, "identical_losses": not diff,
       "max_abs_loss_diff": max((abs(a - b) for a, b in diff.values() if a is not None and b is not None), default=0.0),
       "adapter_sha256_a": sha("a"), "adapter_sha256_b": sha("b")}
res["identical_adapters"] = res["adapter_sha256_a"] == res["adapter_sha256_b"]
(out / "determinism.json").write_text(json.dumps(res, indent=2))
print(json.dumps({k: res[k] for k in ("identical_losses", "max_abs_loss_diff", "identical_adapters")}))
PYEOF
ec=$?
rm -rf -- "$out/a/adapter" "$out/b/adapter" "$out/a/ckpt" "$out/b/ckpt"
exit $ec
