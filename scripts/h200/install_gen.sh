#!/usr/bin/env bash
# On the H200: create $CHINOR/venv-gen for data generation (rewrites, rejection sampling, judge).
#   bash scripts/h200/install_gen.sh
# Kept apart from $CHINOR/venv so that vLLM and its pins never touch the training stack.
# 1. dry-run of the generation packages (pins from requirements-h200.txt); abort if the plan contains
#    torch, torchvision, torchaudio, triton or nvidia-* (see venv_lib.sh for the constraint file)
# 2. install into the venv (no --user, nothing under $HOME, caches inside $CHINOR; see env.sh)
# 3. vllm --no-deps and an import test; the result decides the engine of data/rewrite_generate.py
#    (vLLM if it passes, transformers bf16 batched otherwise) and is written to logs/venv-gen.json
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/env.sh"
source "$here/venv_lib.sh"
repo="$(cd "$here/../.." && pwd)"
mkdir -p "$CHINOR/logs"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
log="$CHINOR/logs/install-gen-$ts.log"
exec > >(tee -a "$log") 2>&1

VPY="$(make_venv "$CHINOR/venv-gen")"
export PIP_CONSTRAINT="$CHINOR/logs/constraint-torch-$ts.txt"
torch_constraint "$PIP_CONSTRAINT"
req="$CHINOR/logs/req-gen-$ts.txt"
# peft too: transformers imports peft whenever it is importable, and the image's peft (built for
# transformers 4) breaks model loading under transformers 5
grep -E '^(transformers|peft|huggingface_hub|accelerate|pyyaml|jinja2|rapidfuzz)==' "$repo/requirements-h200.txt" > "$req"
vllm_spec="$(grep -E '^vllm' "$repo/requirements-h200.txt" | head -n 1)"

echo "== dry-run: $(tr '\n' ' ' < "$req")"
"$VPY" -m pip install --dry-run --quiet --report "$CHINOR/logs/plan-gen-$ts.json" -r "$req"
guard "$VPY" "$CHINOR/logs/plan-gen-$ts.json"

echo "== install"
"$VPY" -m pip install -r "$req"

echo "== $vllm_spec --no-deps"
"$VPY" -m pip install --no-deps "$vllm_spec"

echo "== import test"
vllm_ok=yes
"$VPY" -c 'import vllm, torch; from vllm import LLM, SamplingParams; print("vllm", vllm.__version__, "torch", torch.__version__)' \
    > "$CHINOR/logs/vllm-import-$ts.txt" 2>&1 || vllm_ok=no
tail -n 5 "$CHINOR/logs/vllm-import-$ts.txt"
if [ "$vllm_ok" = no ]; then
    # a failed import leaves an unusable package that engine=auto would try first: remove it from the venv
    "$VPY" -m pip uninstall -y vllm >/dev/null
fi
"$VPY" -c 'import transformers, torch, yaml, transformers.trainer_utils; from transformers import AutoModelForCausalLM; print("transformers", transformers.__version__, "torch", torch.__version__, "cuda", torch.cuda.is_available())'

"$VPY" - "$CHINOR/logs/venv-gen.json" "$vllm_ok" "$CHINOR/logs/vllm-import-$ts.txt" <<'PYEOF'
import importlib.metadata as md, json, platform, sys
out, ok, err = sys.argv[1:4]
ver = {}
for p in ["torch", "transformers", "peft", "huggingface_hub", "accelerate", "pyyaml", "jinja2", "rapidfuzz", "regex", "safetensors", "tokenizers", "vllm"]:
    try: ver[p] = md.version(p)
    except md.PackageNotFoundError: ver[p] = None
res = {"python": platform.python_version(), "versions": ver, "vllm_import_ok": ok == "yes",
       "vllm_import_error": None if ok == "yes" else open(err).read().strip().splitlines()[-1]}
json.dump(res, open(out, "w"), indent=2)
print(json.dumps(res, indent=2))
PYEOF
echo "log: $log"
