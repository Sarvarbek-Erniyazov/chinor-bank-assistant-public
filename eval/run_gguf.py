"""Run eval-v1 on one demo GGUF with llama-cpp-python on CPU (labelled "GGUF <quant>, CPU, not Protocol A"; the
quantisation type is read from the build record, Q4_K_M when it names none).

python eval/run_gguf.py --gguf <file.gguf> --build-json <name.build.json> --name <name> --compare-arm <recorded arm>
    [--prompts results/runs/gguf-prompts/prompts.jsonl] [--threads 16] [--n-ctx 4096]
Runs in a separate environment with llama-cpp-python (no torch; nothing from the repo is imported). Inputs are the
Protocol-A prompt ids from eval/gguf_prompts.py, fed as token ids. Decoding: greedy (temperature 0, top-k 1), at
most 200 new tokens, stop on 151645 (<|im_end|>) or 151643 (<|endoftext|>), no repetition penalty, items in
eval_set order, one sequence at a time (llama-cpp-python reuses the KV cache of the common prompt prefix).
Checks before decoding: llama.cpp's own tokenisation of each prompt text (special tokens parsed) equals the ids;
the three special tokens round-trip.
Writes results/runs/gguf-<name>/generations.jsonl (id, gen_ids, raw_llama, stop_reason, n_tokens, latency_ms) and
run.json (environment, timings, peak RAM, the build record and the GGUF SHA-256). results/gguf_report.py decodes
the ids with the HF tokenizer as eval/run_eval.py does and scores them.
tokens_per_s = generated tokens / time spent in generation (prompt processing of the uncached part included).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IM_END, ENDOFTEXT, IM_START = 151645, 151643, 151644
MAX_NEW_TOKENS = 200
LABEL = "GGUF {quant}, CPU, not Protocol A"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def cpu_name() -> str:
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    return platform.processor() or platform.machine()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--build-json", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--compare-arm", required=True, help="recorded Protocol-A arm in eval/outputs/")
    ap.add_argument("--prompts", type=Path, default=ROOT / "results" / "runs" / "gguf-prompts" / "prompts.jsonl")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--n-ctx", type=int, default=4096)
    a = ap.parse_args()
    import llama_cpp
    import psutil
    out = ROOT / "results" / "runs" / f"gguf-{a.name}"
    assert not out.exists(), f"{out} exists (names are never reused)"
    prompts = [json.loads(l) for l in a.prompts.read_text(encoding="utf-8").splitlines() if l.strip()]
    build = json.loads(a.build_json.read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    llm = llama_cpp.Llama(model_path=str(a.gguf), n_ctx=a.n_ctx, n_threads=a.threads, n_threads_batch=a.threads,
                          seed=0, verbose=False)
    load_s = time.perf_counter() - t0
    special_ok = all(llm.tokenize(t.encode(), add_bos=False, special=True) == [i] for t, i in
                     (("<|im_start|>", IM_START), ("<|im_end|>", IM_END), ("<|endoftext|>", ENDOFTEXT)))
    tok_agree = sum(llm.tokenize(p["text"].encode("utf-8"), add_bos=False, special=True) == p["ids"] for p in prompts)
    rows, gen_time, gen_tokens = [], 0.0, 0
    for p in prompts:
        t = time.perf_counter()
        out_ids, stop = [], "length"
        for tok in llm.generate(p["ids"], top_k=1, top_p=1.0, min_p=0.0, typical_p=1.0, temp=0.0, repeat_penalty=1.0,
                                reset=True):
            if tok in (IM_END, ENDOFTEXT):
                stop = "im_end" if tok == IM_END else "endoftext"
                break
            out_ids.append(tok)
            if len(out_ids) == MAX_NEW_TOKENS:
                break
        dt = time.perf_counter() - t
        gen_time += dt
        gen_tokens += len(out_ids)
        rows.append({"id": p["id"], "gen_ids": out_ids,
                     "raw_llama": llm.detokenize(out_ids, special=True).decode("utf-8", errors="replace"),
                     "stop_reason": stop, "n_tokens": len(out_ids), "latency_ms": round(1000 * dt, 1)})
    mem = psutil.Process().memory_info()
    peak = getattr(mem, "peak_wset", None) or mem.rss
    out.mkdir(parents=True)
    (out / "generations.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                           encoding="utf-8", newline="\n")
    quant = build.get("quant") or "Q4_K_M"
    run = {"label": LABEL.format(quant=quant), "quant": quant, "name": a.name, "compare_arm": a.compare_arm, "protocol": "none (not Protocol A)",
           "gguf": {"file": a.gguf.name, "sha256": sha256(a.gguf), "bytes": a.gguf.stat().st_size},
           "build": {k: build.get(k) for k in ("llama_cpp_commit", "llama_cpp_python", "template", "template_sha256",
                                               "files", "checks", "checks_passed", "merge", "commands",
                                               "f16_reused", "template_already_in_f16")},
           "prompts": {"file": "results/runs/gguf-prompts/prompts.jsonl", "sha256": sha256(a.prompts)},
           "decoding": {"greedy": True, "temp": 0.0, "top_k": 1, "max_new_tokens": MAX_NEW_TOKENS,
                        "stop_ids": [IM_END, ENDOFTEXT], "repeat_penalty": 1.0, "batch": 1, "n_ctx": a.n_ctx},
           "checks": {"special_tokens_round_trip": special_ok, "prompt_tokenisation_equal_hf": tok_agree,
                      "prompts": len(prompts)},
           "threads": a.threads, "cpu": cpu_name(), "logical_cpus": os.cpu_count(),
           "ram_total_gb": round(psutil.virtual_memory().total / 1e9, 1), "os": platform.platform(),
           "python": platform.python_version(), "llama_cpp_python": llama_cpp.__version__,
           "load_s": round(load_s, 2), "generation_s": round(gen_time, 1), "generated_tokens": gen_tokens,
           "tokens_per_s": round(gen_tokens / gen_time, 2) if gen_time else None,
           "peak_ram_gb": round(peak / 1e9, 2), "git_commit": git_commit(),
           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: run[k] for k in ("name", "load_s", "tokens_per_s", "peak_ram_gb", "checks")}))


if __name__ == "__main__":
    main()
