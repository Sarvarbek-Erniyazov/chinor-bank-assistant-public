"""Protocol-A prompts of eval-v1 as token ids, for the GGUF demo runs (eval/run_gguf.py).

python eval/gguf_prompts.py [--tokenizer Qwen/Qwen3-1.7B-Base] [--out results/runs/gguf-prompts/prompts.jsonl]
The prompts are built exactly as eval/run_eval.py builds them (build_messages: frozen system prompt
handbook/system_prompt.txt for every block except R, no few-shot turns; train/chat_template.jinja;
add_generation_prompt; tokenised without added special tokens), so a GGUF run receives the same input ids as the
recorded Protocol-A run. One line per item in eval_set order: id, block, text, ids. Also writes <out>.meta.json with
the tokenizer id and revision and the SHA-256 of the system prompt, template and output file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from run_eval import EVAL_SET, SYSTEM_PROMPT, build_messages  # noqa: E402

TEMPLATE = ROOT / "train" / "chat_template.jinja"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", default="Qwen/Qwen3-1.7B-Base")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "runs" / "gguf-prompts" / "prompts.jsonl")
    a = ap.parse_args()
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    tok.chat_template = TEMPLATE.read_text(encoding="utf-8")
    system_prompt = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    items = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines = []
    for it in items:
        text = tok.apply_chat_template(build_messages(it, system_prompt, []), tokenize=False, add_generation_prompt=True)
        ids = tok(text, add_special_tokens=False)["input_ids"]
        lines.append(json.dumps({"id": it["id"], "block": it["block"], "text": text, "ids": ids}, ensure_ascii=False))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    body = ("\n".join(lines) + "\n").encode("utf-8")
    a.out.write_bytes(body)
    revision = None
    try:
        from huggingface_hub import try_to_load_from_cache
        p = try_to_load_from_cache(a.tokenizer, "tokenizer.json")
        revision = Path(p).parent.name if isinstance(p, str) else None
    except Exception:
        pass
    meta = {"tokenizer": a.tokenizer, "revision": revision, "items": len(lines),
            "system_prompt_sha256": sha(system_prompt.encode("utf-8")), "template_sha256": sha(TEMPLATE.read_bytes()),
            "prompts_sha256": sha(body)}
    a.out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
