# Sourced by the remote-side scripts. Nothing secret belongs here.
# CHINOR_WS: the server workspace root (holds chinor/, hf/, GPU_LOCK); export it on the server, e.g. in ~/.profile.
# Local scripts also read CHINOR_HOST, the ssh alias of the server.
export CHINOR=${CHINOR_WS:-<workspace>}/chinor
export HF_HOME="${CHINOR_HF_HOME:-${CHINOR_WS:-<workspace>}/hf}"   # shared with GTD: weights are downloaded once (CHINOR_HF_HOME: tests only)
export GPU_LOCK="${GPU_LOCK:-${CHINOR_WS:-<workspace>}/GPU_LOCK}"
# The account is shared with other projects and sessions: nothing is written under $HOME and the user
# site (~/.local, which holds another session's sitecustomize.py) is never read or written. Packages
# live in $CHINOR/venv and $CHINOR/venv-gen; every cache stays inside the chinor workspace.
export PYTHONNOUSERSITE=1
export XDG_CACHE_HOME="$CHINOR/.cache"
export PIP_CACHE_DIR="$CHINOR/.cache/pip"
export TRITON_CACHE_DIR="$CHINOR/.cache/triton"
export VLLM_CACHE_ROOT="$CHINOR/.cache/vllm"
export TORCH_HOME="$CHINOR/.cache/torch"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
PY="$(command -v python3 || command -v python)"
export PY
# 022, not 077: the shared HF cache must stay readable for GTD; the chinor workspace itself is chmod 700.
umask 022
