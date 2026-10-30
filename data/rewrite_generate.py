"""Generate candidate rewrites of the canonical answers for every task prompt (Stage 1, H200).

Generator: Qwen/Qwen3-32B in non-thinking mode (enable_thinking=False in the chat template), bf16.
Engine: vLLM when it imports, otherwise transformers bf16 batched generate (--engine forces one).
No verification happens here; data/verify.py checks every candidate afterwards.

Usage (on the H200, through scripts/h200/launch.sh):
  python data/rewrite_generate.py --out <workspace>/chinor/results/c1-rewrites
Writes <out>/rewrites_raw.jsonl (id, candidate_index, text, finish_reason) and <out>/run.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROMPT_TEMPLATE = ROOT / "data" / "rewrite_prompt.txt"
SYSTEM_PROMPT = ROOT / "handbook" / "system_prompt.txt"
INTENTS = ROOT / "handbook" / "intents.yaml"
PROMPTS = ROOT / "data" / "sft" / "v1" / "task_prompts.jsonl"


def build_instruction(template: str, system_prompt: str, query: str, entry: dict) -> str:
    fields = {
        "{system_prompt}": system_prompt.strip(),
        "{customer_message}": query.strip(),
        "{canonical_answer}": entry["canonical_answer"].strip(),
        "{required_facts}": "\n".join(f"- {f}" for f in entry["required_facts"]),
        "{forbidden}": "\n".join(f"- {f}" for f in entry["forbidden"]) or "- (none)",
    }
    for k, v in fields.items():
        template = template.replace(k, v)
    return template


def pick_engine(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import vllm  # noqa: F401
        return "vllm"
    except Exception as e:  # import errors of a mismatched build are not always ImportError
        print(f"vllm import failed ({type(e).__name__}: {e}); using transformers", file=sys.stderr)
        return "hf"


def gen_vllm(model_path, prompts, args):
    from vllm import LLM, SamplingParams
    import vllm
    llm = LLM(model=model_path, dtype="bfloat16", seed=args.seed, max_model_len=args.max_model_len,
              gpu_memory_utilization=args.gpu_memory_utilization)
    sp = SamplingParams(n=args.n, temperature=args.temperature, top_p=args.top_p, max_tokens=args.max_tokens, seed=args.seed)
    outs = llm.generate(prompts, sp)
    return [[(o.text, o.finish_reason) for o in r.outputs] for r in outs], f"vllm {vllm.__version__}"


def gen_hf(model_path, prompts, tok, args):
    import torch
    import transformers
    from transformers import AutoModelForCausalLM
    transformers.set_seed(args.seed)
    model = AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.bfloat16, device_map=args.device)
    model.eval()
    tok.padding_side = "left"
    eos = [tok.convert_tokens_to_ids("<|im_end|>"), tok.eos_token_id]
    res = []
    for s in range(0, len(prompts), args.batch_size):
        batch = prompts[s:s + args.batch_size]
        enc = tok(batch, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, do_sample=True, temperature=args.temperature, top_p=args.top_p,
                                 max_new_tokens=args.max_tokens, num_return_sequences=args.n,
                                 eos_token_id=eos, pad_token_id=tok.pad_token_id)
        gen = out[:, enc["input_ids"].shape[1]:]
        for i in range(len(batch)):
            cands = []
            for j in range(args.n):
                ids = gen[i * args.n + j].tolist()
                stop = next((k for k, t in enumerate(ids) if t in eos), None)
                cands.append((tok.decode(ids[:stop], skip_special_tokens=True), "stop" if stop is not None else "length"))
            res.append(cands)
        print(f"{min(s + args.batch_size, len(prompts))}/{len(prompts)} prompts", flush=True)
    return res, f"transformers {transformers.__version__}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-32B")
    ap.add_argument("--revision", default="main")
    ap.add_argument("--prompts", default=str(PROMPTS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", choices=["auto", "vllm", "hf"], default="auto")
    ap.add_argument("--dtype", choices=["bf16"], default="bf16")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--top_p", type=float, default=0.9)
    ap.add_argument("--max_tokens", type=int, default=220)
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--batch_size", type=int, default=32, help="transformers engine only")
    ap.add_argument("--device", default="cuda", help="transformers engine only")
    ap.add_argument("--max_model_len", type=int, default=4096, help="vllm engine only")
    ap.add_argument("--gpu_memory_utilization", type=float, default=0.85, help="vllm engine only")
    ap.add_argument("--limit", type=int, default=0, help="first N prompts only (smoke test)")
    args = ap.parse_args()

    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer

    # read at start: a later sync_up rewrites COMMIT while the run is still going
    commit_file = ROOT / "COMMIT"
    commit = commit_file.read_text().strip() if commit_file.exists() else \
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "unknown"

    rows = [json.loads(l) for l in Path(args.prompts).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[:args.limit]
    intents = yaml.safe_load(INTENTS.read_text(encoding="utf-8"))
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    system_prompt = SYSTEM_PROMPT.read_text(encoding="utf-8")

    model_path = snapshot_download(args.model, revision=args.revision,
                                   allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"])
    revision = Path(model_path).name
    tok = AutoTokenizer.from_pretrained(model_path)
    prompts = [tok.apply_chat_template([{"role": "user", "content": build_instruction(template, system_prompt, r["query"], intents[r["intent"]])}],
                                       tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in rows]
    assert prompts[0].rstrip().endswith("</think>"), "non-thinking mode not applied by the chat template"

    engine = pick_engine(args.engine)
    t0 = time.time()
    if engine == "vllm":
        outs, engine_version = gen_vllm(model_path, prompts, args)
    else:
        outs, engine_version = gen_hf(model_path, prompts, tok, args)
    wall = time.time() - t0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "rewrites_raw.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r, cands in zip(rows, outs):
            for j, (text, finish) in enumerate(cands):
                f.write(json.dumps({"id": r["id"], "candidate_index": j, "text": text.strip(), "finish_reason": finish}, ensure_ascii=False) + "\n")

    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        gpu = None
    run = {
        "model": args.model, "revision": revision, "engine": engine, "engine_version": engine_version,
        "dtype": args.dtype, "gpu": gpu, "python": platform.python_version(),
        "decoding": {"n": args.n, "temperature": args.temperature, "top_p": args.top_p, "max_tokens": args.max_tokens,
                     "seed": args.seed, "enable_thinking": False},
        "n_prompts": len(rows), "n_candidates": sum(len(c) for c in outs),
        "prompt_template_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
        "wall_clock_s": round(wall, 1), "COMMIT": commit,
    }
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
