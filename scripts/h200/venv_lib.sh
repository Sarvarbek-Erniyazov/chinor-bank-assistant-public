# Sourced by install.sh and install_gen.sh (after env.sh). Venvs live in $CHINOR and use
# --system-site-packages, so torch is always the server's own build; nothing is installed with --user.
#
# The NGC image sets PIP_CONSTRAINT=/etc/pip/constraint.txt, which pins ~300 packages including transitive
# ones (regex, safetensors, ...) that the pinned stack needs newer. Inside our venvs that file is replaced
# by one that keeps only the image's torch stack (torch, torchvision, torchaudio, triton, nvidia-*) and its
# NumPy (the image's torch is built for NumPy 1; NumPy 2 breaks torch.from_numpy); the dry-run guard below
# aborts on the torch names in any case.

make_venv() {  # make_venv <dir>: create once, print its python
    [ -x "$1/bin/python" ] || "$PY" -m venv --system-site-packages "$1" >&2
    echo "$1/bin/python"
}

torch_constraint() {  # torch_constraint <out>: image pins of the torch stack and NumPy only
    local image="${PIP_CONSTRAINT_IMAGE:-/etc/pip/constraint.txt}"
    : > "$1"
    [ -f "$image" ] && grep -i -E '^(torch|torchvision|torchaudio|triton|nvidia-[a-z0-9-]+|numpy)==' "$image" >> "$1" || true
    echo "  constraint: $(wc -l < "$1") torch-stack/NumPy pin(s) from $image: $(grep -i '^numpy==' "$1" || echo 'no numpy pin')" >&2
}

guard() {  # guard <python> <pip report.json>: print the plan, fail on torch/CUDA wheels
    "$1" - "$2" <<'PYEOF'
import json, re, sys
plan = [(i["metadata"]["name"].lower(), i["metadata"]["version"]) for i in json.load(open(sys.argv[1])).get("install", [])]
for n, v in plan:
    print(f"  plan: {n}=={v}")
bad = [f"{n}=={v}" for n, v in plan if n in ("torch", "torchvision", "torchaudio", "triton") or re.match(r"nvidia-", n)]
if bad:
    print("ABORT: the plan would install " + ", ".join(bad)); sys.exit(1)
print(f"  {len(plan)} package(s), no torch/CUDA wheels")
PYEOF
}
