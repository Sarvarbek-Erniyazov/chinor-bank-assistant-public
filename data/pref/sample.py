"""Preference stage §2: on-policy samples from sft-merged (C4). GPU, bf16.

python data/pref/sample.py --model <sft-merged dir> --prompts data/pref/v1/prompts.jsonl --out <dir> [--batch-prompts 32]
K = 8 samples per prompt, temperature 0.8, top_p 0.95, max_new_tokens 200, eos [151645, 151643], seed 20261029
(torch.manual_seed once, prompts in file order, length-sorted batches as in eval/run_eval.py). Prompt = the frozen
system prompt + the prompt's messages, rendered with train/chat_template.jinja (add_generation_prompt). Per sample:
id, k, raw (decoded up to the stop token), stop_reason (im_end / endoftext / length), n_tokens.
Writes <out>/samples.jsonl and <out>/run.json (settings, model manifest_sha256 from merge.json, wall-clock, stop
reasons, share of samples that are verbatim canonical answers: the intent's canonical_answer for task prompts, the
SFT reply for behaviour prompts, compared after whitespace normalisation).
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
SYSTEM_PROMPT = ROOT / "handbook" / "system_prompt.txt"
TEMPLATE = ROOT / "train" / "chat_template.jinja"
IM_END, ENDOFTEXT = 151645, 151643
K, TEMPERATURE, TOP_P, MAX_NEW_TOKENS, SEED = 8, 0.8, 0.95, 200, 20261029


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def references(prompts: list[dict]) -> dict[str, str]:
    canon = {k: v["canonical_answer"] for k, v in yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8")).items()}
    return {p["id"]: canon[p["intent"]] if p["category"] == "task" else p["reference"] for p in prompts}


def stop_cut(row: list[int]) -> tuple[str, int]:
    for k, t in enumerate(row):
        if t in (IM_END, ENDOFTEXT):
            return ("im_end" if t == IM_END else "endoftext"), k
    return "length", len(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompts", default=str(ROOT / "data" / "pref" / "v1" / "prompts.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch-prompts", type=int, default=32)
    ap.add_argument("--limit", type=int, default=None, help="first N prompts only (smoke test)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    prompts = jsonl(Path(a.prompts))[: a.limit]
    system = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    tok = AutoTokenizer.from_pretrained(a.model)
    tok.chat_template = TEMPLATE.read_text(encoding="utf-8")
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    assert tok.convert_tokens_to_ids("<|im_end|>") == IM_END
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).to("cuda").eval()
    texts = [tok.apply_chat_template([{"role": "system", "content": system}] + p["messages"], tokenize=False,
                                     add_generation_prompt=True) for p in prompts]
    order = sorted(range(len(prompts)), key=lambda i: len(texts[i]))
    torch.manual_seed(SEED)
    rows: dict[str, list[dict]] = {}
    t0 = time.perf_counter()
    for b in range(0, len(order), a.batch_prompts):
        idx = order[b: b + a.batch_prompts]
        enc = tok([texts[i] for i in idx], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
        with torch.no_grad():
            gen = model.generate(**enc, do_sample=True, temperature=TEMPERATURE, top_p=TOP_P, top_k=0,
                                 num_return_sequences=K, max_new_tokens=MAX_NEW_TOKENS, eos_token_id=[IM_END, ENDOFTEXT],
                                 pad_token_id=tok.pad_token_id, repetition_penalty=1.0)
        new = gen[:, enc["input_ids"].shape[1]:].tolist()
        for j, i in enumerate(idx):
            pid = prompts[i]["id"]
            rows[pid] = []
            for k in range(K):
                stop, cut = stop_cut(new[j * K + k])
                rows[pid].append({"id": pid, "k": k, "raw": tok.decode(new[j * K + k][:cut], skip_special_tokens=False),
                                  "stop_reason": stop, "n_tokens": cut})
        print(f"[{min(b + a.batch_prompts, len(order))}/{len(order)}] {time.perf_counter() - t0:.0f} s", flush=True)
    wall = time.perf_counter() - t0
    samples = [s for p in prompts for s in rows[p["id"]]]
    with (out / "samples.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    ref = references(prompts)
    verbatim = sum(ws(s["raw"]) == ws(ref[s["id"]]) for s in samples)
    merge = Path(a.model) / "merge.json"
    meta = {"model": a.model, "model_manifest_sha256": json.loads(merge.read_text())["manifest_sha256"] if merge.exists() else None,
            "prompts": a.prompts, "n_prompts": len(prompts), "n_samples": len(samples), "k": K, "temperature": TEMPERATURE,
            "top_p": TOP_P, "max_new_tokens": MAX_NEW_TOKENS, "eos_token_id": [IM_END, ENDOFTEXT], "seed": SEED,
            "dtype": "bf16", "gpu": torch.cuda.get_device_name(0), "batch_prompts": a.batch_prompts,
            "wall_clock_s": round(wall, 1), "stop_reasons": dict(Counter(s["stop_reason"] for s in samples)),
            "verbatim_reference": verbatim, "verbatim_reference_share": round(verbatim / len(samples), 4),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("n_samples", "wall_clock_s", "stop_reasons", "verbatim_reference_share")}))


if __name__ == "__main__":
    main()
