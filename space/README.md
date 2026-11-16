---
title: Chinor Bank Assistant demo
sdk: gradio
sdk_version: 6.30.0
python_version: "3.11"
app_file: app.py
pinned: false
---

# Chinor Bank Assistant: live demo (GGUF Q8_0 on CPU)

Chinor Bank is fictional; every policy and number is invented. One question, two of four Qwen3-1.7B models, answered
one after the other and streamed: the base model; SFT rsLoRA without trainable special-token rows (b); the same
with the two token rows trained (c1, same data v1 and seed 0 as b); SFT on data v1.2 (c). **GGUF Q8_0 on CPU, not
the evaluation protocol**: scores of these files are in `results/gguf_demo_models.md`, the choice of Q8_0 in
docs/decisions.md ADR-036.

## Files

- `app.py`: the Gradio interface (two tabs: demo; links to the recorded-answer viewer and the repository).
- `chinor_demo.py`: prompts, decoding, end-of-turn marking, rule flags, request log (no Gradio; tested).
- `build_space.py`: writes `data/assets.json` and `vendor/` from committed files (run from the repository root:
  `python space/build_space.py`; part of `scripts/regen_outputs.py`).
- `config.json`: `models_dir` (the one place the GGUF files are looked for; env `CHINOR_MODELS_DIR` overrides it),
  2 threads, n_ctx 4096, SHA-256 check of each file on first load, log file, port.
- `requirements.txt`: every package pinned (pip freeze of the app environment, Python 3.11).

## Behaviour

- Decoding as the evaluation: frozen system prompt (`vendor/system_prompt.txt`), project chat template
  (`vendor/chat_template.jinja`), greedy, at most 200 new tokens, stop on 151645 `<|im_end|>` or 151643
  `<|endoftext|>`. An example question gets its eval item's Protocol-A messages (R item: no system prompt).
- Under each answer: stop reason, tokens, seconds, tokens/s. Text after the intended end of the turn (the scorer's
  stop strings and `eval/turn_cut.py`, as in the viewer) is shown and marked, never hidden.
- Examples: only the pre-registered items of `results/qualitative_ids.json`.
- Flags, labelled "automatic rule check, lenient": `hard_violation` and numbers in neither the handbook nor the
  user message, the functions of `eval/score.py` that need no item rubric, on the text the scorer reads.
- One request at a time (queue concurrency 1), 2 threads. Log: one JSON line per request (stdout and
  `logs/requests.jsonl`) with time, model names, token counts, seconds, stop reasons and flags; no question or
  answer text.

## Install and run

Local (Windows or Linux), from the repository root:

```
python -m venv venv-space
venv-space/bin/pip install -r space/requirements.txt          # Windows: venv-space\Scripts\pip
CHINOR_MODELS_DIR=<folder with the four *-Q8_0.gguf files> venv-space/bin/python space/app.py
```

llama-cpp-python on a Linux Space: **prebuilt wheel, no source build.** `requirements.txt` adds the CPU wheel index
`https://abetlen.github.io/llama-cpp-python/whl/cpu`, which has
`llama_cpp_python-0.3.36-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` (SHA-256
`c8a3e98093e950d7a770f794842e36f2db82b2933e8762ed7b5ffd435011e8e4`, downloaded and hashed; the Windows wheel used
locally is `ae5e88a2cf464e5a2dde7c8898c2d5c71cc24d03cac6396bf7509456bde0b9fb`). The model files are not in git; on
a Space `models_dir` would point at a folder filled from a Hub model repository (not set up).

Not tested on Windows, so unverified for a Space: installing `requirements.txt` on Linux (the pins come from a
Windows freeze; `colorama` is marked Windows-only); that the Linux wheel imports and runs (it was only downloaded);
the Space's own Gradio install from `sdk_version`; host and port from the Space's environment
(`GRADIO_SERVER_NAME` / `GRADIO_SERVER_PORT`); speed and memory on the Space's 2 vCPU (the 2-thread figures in
`results/gguf_demo_models.md` are from an i7-13700, an estimate, not a measurement of the Space); model download
from the Hub.
