"""Run one arm over the frozen eval set.

python eval/run_eval.py --model Qwen/Qwen3-1.7B-Base --arm base-1.7B-0shot \
    [--adapter none|PATH] [--shots 0|3] [--quant none|4bit] \
    [--template train/chat_template.jinja] [--device cuda|cpu] [--batch-size 8] \
    [--limit N] [--dtype fp16|bf16|fp32] [--protocol A|B] [--native-template] [--eval-set PATH]

Writes eval/outputs/<arm>/answers.jsonl (id, raw, stop_reason, latency_ms) and
eval/outputs/<arm>/run.json. Decoding is fixed: greedy, max_new_tokens 200,
eos ids [151645, 151643], left padding. System prompt applied to every block
except R. Few-shot demonstrations (eval/fewshot.json) are inserted as
user/assistant turns after the system prompt; block R gets neither.
--protocol checks the frozen evaluation protocol (eval/FROZEN.md) before decoding:
A = H200 bf16 (4-bit arms with bf16 compute), B = T4 fp16 (4-bit arms in 4-bit).
--native-template: reference rows of official instruct models ("reference, not pipeline"): the model's own chat
template with enable_thinking=False instead of train/chat_template.jinja; decoding unchanged.
--eval-set: another item file in the eval_set.jsonl format (red-team drafts); default eval/eval_set.jsonl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
EVAL_SET = ROOT / "eval" / "eval_set.jsonl"
SYSTEM_PROMPT = ROOT / "handbook" / "system_prompt.txt"
FEWSHOT = ROOT / "eval" / "fewshot.json"
IM_END, ENDOFTEXT = 151645, 151643
MAX_NEW_TOKENS = 200


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        # no git on the H200: scripts/h200/sync_up.sh writes the commit into COMMIT
        commit = ROOT / "COMMIT"
        return commit.read_text(encoding="utf-8").strip() if commit.exists() else "unknown"


PROTOCOLS = {"A": ("H200", "bf16"), "B": ("T4", "fp16")}


def check_protocol(protocol: str, gpu: str, dtype: str) -> None:
    want_gpu, want_dtype = PROTOCOLS[protocol]
    if want_gpu not in gpu or dtype != want_dtype:
        sys.exit(f"protocol {protocol} needs {want_gpu} / {want_dtype}, got {gpu or 'no GPU'} / {dtype}")


def package_versions() -> dict:
    import importlib.metadata as md
    out = {}
    for p in ("torch", "transformers", "peft", "bitsandbytes", "accelerate", "datasets", "trl"):
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            pass
    return out


def build_messages(item: dict, system_prompt: str, shots: list[dict]) -> list[dict]:
    if item["block"] == "R":
        return list(item["messages"])
    msgs = [{"role": "system", "content": system_prompt}]
    for d in shots:
        msgs.append({"role": "user", "content": d["user"]})
        msgs.append({"role": "assistant", "content": d["assistant"]})
    msgs += item["messages"]
    return msgs


def load_model(args):
    kwargs = {}
    dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[args.dtype]
    if args.quant == "4bit":
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
        kwargs["device_map"] = {"": 0}
    else:
        kwargs["dtype"] = dtype
    model = AutoModelForCausalLM.from_pretrained(args.model, revision=args.revision, **kwargs)
    if args.adapter and args.adapter != "none":
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
    if args.quant != "4bit":
        model.to(args.device)
    model.eval()
    return model


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--revision", default=None)
    ap.add_argument("--tokenizer", default=None, help="defaults to --model")
    ap.add_argument("--adapter", default="none")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--shots", type=int, choices=[0, 3], default=0)
    ap.add_argument("--quant", choices=["none", "4bit"], default="none")
    ap.add_argument("--template", default=str(ROOT / "train" / "chat_template.jinja"))
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default=None)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="only the first N items (smoke test)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--protocol", choices=sorted(PROTOCOLS), default=None)
    ap.add_argument("--native-template", action="store_true", help="instruct reference rows: own template, no thinking")
    ap.add_argument("--eval-set", default=str(EVAL_SET))
    ap.add_argument("--system-prompt", default=str(SYSTEM_PROMPT), help="robustness arms only (eval/system_prompt_paraphrase.txt)")
    args = ap.parse_args()
    if args.dtype is None:
        args.dtype = {"A": "bf16", "B": "fp16"}.get(args.protocol) or ("fp16" if args.device.startswith("cuda") else "fp32")
    gpu_name = torch.cuda.get_device_name(0) if args.device.startswith("cuda") else platform.processor()
    if args.protocol:
        check_protocol(args.protocol, gpu_name, args.dtype)

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "eval" / "outputs" / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(args.tokenizer or args.model, revision=args.revision)
    if not args.native_template:
        tok.chat_template = Path(args.template).read_text(encoding="utf-8")
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    # base tokenizers end on <|endoftext|>; the official instruct ones on <|im_end|>: stop ids are the same pair
    assert tok.convert_tokens_to_ids("<|im_end|>") == IM_END and tok.eos_token_id in ((IM_END, ENDOFTEXT) if args.native_template else (ENDOFTEXT,))

    system_prompt = Path(args.system_prompt).read_text(encoding="utf-8").strip()
    shots = json.loads(FEWSHOT.read_text(encoding="utf-8")) if args.shots else []
    items = [it for it in (json.loads(l) for l in Path(args.eval_set).read_text(encoding="utf-8").splitlines() if l.strip())
             if not it.get("_meta")]  # _meta: the canary record of redteam_set.jsonl
    if args.limit:
        items = items[: args.limit]

    model = load_model(args)
    if args.device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    extra = {"enable_thinking": False} if args.native_template else {}
    prompts = [tok.apply_chat_template(build_messages(it, system_prompt, shots), tokenize=False, add_generation_prompt=True, **extra)
               for it in items]
    order = sorted(range(len(items)), key=lambda i: len(prompts[i]))  # length-sorted batches
    results: dict[str, dict] = {}
    t_start = time.perf_counter()
    for b in range(0, len(order), args.batch_size):
        idx = order[b: b + args.batch_size]
        enc = tok([prompts[i] for i in idx], return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        t0 = time.perf_counter()
        with torch.no_grad():
            gen = model.generate(**enc, do_sample=False, max_new_tokens=MAX_NEW_TOKENS, eos_token_id=[IM_END, ENDOFTEXT], pad_token_id=tok.pad_token_id, repetition_penalty=1.0, temperature=None, top_p=None, top_k=None)
        dt = (time.perf_counter() - t0) * 1000 / len(idx)
        new = gen[:, enc["input_ids"].shape[1]:]
        for row, i in zip(new.tolist(), idx):
            stop = "length"
            cut = len(row)
            for k, t in enumerate(row):
                if t in (IM_END, ENDOFTEXT):
                    stop = "im_end" if t == IM_END else "endoftext"
                    cut = k
                    break
            # with left padding and batched eos, trailing pads after the stop are pad_token (== endoftext)
            raw = tok.decode(row[:cut], skip_special_tokens=False)
            results[items[i]["id"]] = {"id": items[i]["id"], "raw": raw, "stop_reason": stop, "latency_ms": round(dt, 1)}
        print(f"[{min(b + args.batch_size, len(order))}/{len(order)}] batch {len(idx)} x {enc['input_ids'].shape[1]} tokens, {dt:.0f} ms/item", flush=True)
    wall = time.perf_counter() - t_start

    with (out_dir / "answers.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(results[it["id"]], ensure_ascii=False) + "\n")
    run = {
        "arm": args.arm, "git_commit": git_commit(), "model": args.model, "revision": args.revision,
        "adapter": None if args.adapter == "none" else args.adapter, "dtype": args.dtype, "quant": args.quant,
        "shots": args.shots, "protocol": args.protocol,
        "template": "native (enable_thinking=False)" if args.native_template else (str(Path(args.template).relative_to(ROOT)) if Path(args.template).is_absolute() else args.template),
        "reference_not_pipeline": bool(args.native_template),
        "system_prompt": {"path": str(Path(args.system_prompt).resolve().relative_to(ROOT)) if Path(args.system_prompt).resolve().is_relative_to(ROOT) else args.system_prompt,
                          "sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()},
        "eval_set": str(Path(args.eval_set).resolve().relative_to(ROOT)) if Path(args.eval_set).resolve().is_relative_to(ROOT) else args.eval_set,
        "decoding": {"do_sample": False, "max_new_tokens": MAX_NEW_TOKENS, "eos_token_id": [IM_END, ENDOFTEXT], "padding_side": "left"},
        "n_items": len(items), "batch_size": args.batch_size, "device": args.device,
        "gpu": gpu_name,
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1e9, 3) if args.device.startswith("cuda") else None,
        "wall_clock_s": round(wall, 1), "mean_latency_ms": round(sum(r["latency_ms"] for r in results.values()) / len(results), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "python": platform.python_version(), "packages": package_versions(),
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
