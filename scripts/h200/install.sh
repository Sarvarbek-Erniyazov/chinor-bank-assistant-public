#!/usr/bin/env bash
# On the H200: install requirements-h200.txt (without vllm) into $CHINOR/venv without touching torch.
#   bash scripts/h200/install.sh [--plan-only]
# The venv uses --system-site-packages, so torch is the server's own build; nothing is installed with
# --user or written under $HOME (shared with other projects and sessions). vLLM lives in venv-gen
# (install_gen.sh).
# 1. dry-run of the plan; abort if torch, torchvision, torchaudio, triton or nvidia-* would be installed
# 2. pip install into the venv (same arguments)
# 3. versions -> docs/environment_h200.md (in the synced repo; copied back to the local machine)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
source "$here/venv_lib.sh"
repo="$(cd "$here/../.." && pwd)"
mkdir -p "$CHINOR/logs"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
log="$CHINOR/logs/install-$ts.log"
exec > >(tee -a "$log") 2>&1

VPY="$(make_venv "$CHINOR/venv")"
export PIP_CONSTRAINT="$CHINOR/logs/constraint-torch-$ts.txt"
torch_constraint "$PIP_CONSTRAINT"
req="$CHINOR/logs/req-main-$ts.txt"
grep -Ev '^[[:space:]]*(#|$)' "$repo/requirements-h200.txt" | grep -Ev '^vllm' > "$req"
grep -i '^numpy==' "$PIP_CONSTRAINT" >> "$req" || true   # requested explicitly so a NumPy 2 left in the venv is replaced

echo "== dry-run: requirements-h200.txt (without vllm)"
"$VPY" -m pip install --dry-run --quiet --report "$CHINOR/logs/plan-main-$ts.json" -r "$req"
guard "$VPY" "$CHINOR/logs/plan-main-$ts.json"
[ "${1:-}" = "--plan-only" ] && exit 0

echo "== install"
"$VPY" -m pip install -r "$req"

echo "== pip check"
"$VPY" -m pip check > "$CHINOR/logs/pip-check-venv-$ts.txt" 2>&1 || true
grep -v DEPRECATION "$CHINOR/logs/pip-check-venv-$ts.txt" | grep -E -i "numpy|pyarrow|datasets|trl|torch|transformers|peft|pandas" || echo "  (no conflicts involving the training stack)"

echo "== bridge test"
bridge_ok=yes
"$VPY" "$repo/scripts/h200/bridge_test.py" --datasets --out "$CHINOR/logs/bridge-venv.json" || bridge_ok=no

echo "== import test"
"$VPY" -c 'import numpy, transformers, trl, peft, datasets, accelerate, bitsandbytes, transformers.trainer_utils; print("training stack imports: numpy", numpy.__version__)'
vllm_ok="$("$VPY" -c 'import json; print("yes" if json.load(open("'"$CHINOR"'/logs/venv-gen.json"))["vllm_import_ok"] else "no")' 2>/dev/null || echo no)"

echo "== versions -> docs/environment_h200.md"
"$VPY" - "$repo/docs/environment_h200.md" "$vllm_ok" <<'PYEOF'
import importlib.metadata as md, platform, subprocess, sys
out, vllm_ok = sys.argv[1], sys.argv[2]
import torch
pk = ["torch", "transformers", "trl", "peft", "datasets", "accelerate", "bitsandbytes", "huggingface_hub", "vllm", "numpy", "scipy", "rapidfuzz", "pyyaml", "jinja2"]
ver = {}
for p in pk:
    try: ver[p] = md.version(p)
    except md.PackageNotFoundError: ver[p] = "not installed"
smi = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
lines = ["# Environment — H200 (Tier L)", "", "Written by `scripts/h200/install.sh` (venv `${CHINOR_WS:-<workspace>}/chinor/venv`, system site packages for torch).", "",
         "## Versions", "", "| Component | Version |", "|---|---|",
         f"| Python | {platform.python_version()} |", f"| GPU | {smi} |",
         f"| CUDA (torch) | {torch.version.cuda} |", f"| bf16 supported | {torch.cuda.is_bf16_supported()} |"]
lines += [f"| {p} | {ver[p]} |" for p in pk]
lines += ["", f"vLLM import test (venv-gen, `logs/venv-gen.json`): **{'pass' if vllm_ok == 'yes' else 'FAIL (generator falls back to transformers bf16 batched)'}**", ""]
open(out, "w").write("\n".join(lines))
print("\n".join(lines))
PYEOF
echo "log: $log"
[ "$bridge_ok" = yes ] || { echo "bridge test FAILED (logs/bridge-venv.json)"; exit 1; }
