"""Speed of one demo GGUF with few CPU threads (labelled "2 threads on i7-13700; an estimate for a 2-vCPU machine, not a
measurement of a hosted service" when run with --threads 2 on that CPU). No scores are computed here.

python eval/gguf_speed.py --gguf <file.gguf> --name <run name> [--threads 2] [--first 40]
    [--prompts results/runs/gguf-prompts/prompts.jsonl] [--n-ctx 4096]
Runs in the llama-cpp-python environment (as eval/run_gguf.py; nothing from the repo is imported). The first --first
prompts of eval-v1 (eval_set order) are generated one after another with one Llama object and the decoding of
eval/run_gguf.py (greedy, at most 200 new tokens, stop on 151645 / 151643). llama-cpp-python reuses the KV cache of
the prompt prefix shared with the previous prompt (the frozen system prompt), as a single-process demo would; prompt
1 starts from an empty cache ("cold").
Per prompt: time to first token (call to first generated token: prompt processing of the uncached part plus one
decoding step), total time, generated tokens. Summary: cold TTFT (prompt 1); median / p90 / max TTFT of prompts 2..N;
decode tokens/s = (generated tokens - 1 per prompt) / (time after the first token), summed over prompts;
end-to-end tokens/s = generated tokens / total time; peak working set of the process (Windows peak_wset, else RSS).
Also: how many of the N generated id sequences equal the 16-thread run results/runs/gguf-<name>/generations.jsonl.
Writes results/runs/gguf-speed/<name>-t<threads>.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IM_END, ENDOFTEXT = 151645, 151643
MAX_NEW_TOKENS = 200


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


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--name", required=True, help="the eval run name: results/runs/gguf-<name>/")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--first", type=int, default=40)
    ap.add_argument("--prompts", type=Path, default=ROOT / "results" / "runs" / "gguf-prompts" / "prompts.jsonl")
    ap.add_argument("--n-ctx", type=int, default=4096)
    a = ap.parse_args()
    import llama_cpp
    import psutil
    out = ROOT / "results" / "runs" / "gguf-speed" / f"{a.name}-t{a.threads}.json"
    assert not out.exists(), f"{out} exists (names are never reused)"
    prompts = [json.loads(l) for l in a.prompts.read_text(encoding="utf-8").splitlines() if l.strip()][:a.first]
    t0 = time.perf_counter()
    llm = llama_cpp.Llama(model_path=str(a.gguf), n_ctx=a.n_ctx, n_threads=a.threads, n_threads_batch=a.threads,
                          seed=0, verbose=False)
    load_s = time.perf_counter() - t0
    rows = []
    for p in prompts:
        t = time.perf_counter()
        ids, ttft, stop = [], None, "length"
        for tok in llm.generate(p["ids"], top_k=1, top_p=1.0, min_p=0.0, typical_p=1.0, temp=0.0, repeat_penalty=1.0,
                                reset=True):
            if ttft is None:
                ttft = time.perf_counter() - t
            if tok in (IM_END, ENDOFTEXT):
                stop = "im_end" if tok == IM_END else "endoftext"
                break
            ids.append(tok)
            if len(ids) == MAX_NEW_TOKENS:
                break
        total = time.perf_counter() - t
        rows.append({"id": p["id"], "prompt_tokens": len(p["ids"]), "n_tokens": len(ids), "stop_reason": stop,
                     "ttft_s": round(ttft, 3), "total_s": round(total, 3), "gen_ids": ids})
    mem = psutil.Process().memory_info()
    peak = getattr(mem, "peak_wset", None) or mem.rss
    ref_p = ROOT / "results" / "runs" / f"gguf-{a.name}" / "generations.jsonl"
    same = None
    if ref_p.exists():
        ref = {g["id"]: g["gen_ids"] for g in (json.loads(l) for l in ref_p.read_text(encoding="utf-8").splitlines() if l.strip())}
        same = sum(r["gen_ids"] == ref.get(r["id"]) for r in rows)
    warm = [r["ttft_s"] for r in rows[1:]]
    after_first = sum(r["total_s"] - r["ttft_s"] for r in rows)
    res = {"label": f"{a.threads} threads on {cpu_name()}; an estimate for a 2-vCPU machine, not a measurement of a hosted service",
           "name": a.name, "gguf": {"file": a.gguf.name, "sha256": sha256(a.gguf), "bytes": a.gguf.stat().st_size},
           "threads": a.threads, "prompts": len(rows), "prompts_sha256": sha256(a.prompts), "n_ctx": a.n_ctx,
           "cpu": cpu_name(), "logical_cpus": os.cpu_count(), "os": platform.platform(),
           "llama_cpp_python": llama_cpp.__version__, "load_s": round(load_s, 2),
           "ttft_cold_s": rows[0]["ttft_s"] if rows else None,
           "ttft_warm_median_s": round(st.median(warm), 3) if warm else None,
           "ttft_warm_p90_s": round(st.quantiles(warm, n=10)[-1], 3) if len(warm) >= 2 else None,
           "ttft_warm_max_s": max(warm) if warm else None,
           "generated_tokens": sum(r["n_tokens"] for r in rows),
           "decode_tokens_per_s": round(sum(max(r["n_tokens"] - 1, 0) for r in rows) / after_first, 2) if after_first else None,
           "end_to_end_tokens_per_s": round(sum(r["n_tokens"] for r in rows) / sum(r["total_s"] for r in rows), 2),
           "peak_ram_gb": round(peak / 1e9, 2),
           "gen_ids_equal_16_thread_run": same, "compared_with": ref_p.relative_to(ROOT).as_posix() if ref_p.exists() else None,
           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "per_prompt": [{k: v for k, v in r.items() if k != "gen_ids"} for r in rows]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: res[k] for k in ("name", "threads", "ttft_cold_s", "ttft_warm_median_s", "decode_tokens_per_s",
                                          "end_to_end_tokens_per_s", "peak_ram_gb", "gen_ids_equal_16_thread_run")}))


if __name__ == "__main__":
    main()
