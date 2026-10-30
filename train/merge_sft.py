"""Merge an SFT LoRA adapter (incl. its trained special-token rows) into the base in bf16: the "sft-merged" model
that the preference stage starts from and uses as its reference (C4).

python train/merge_sft.py --base Qwen/Qwen3-14B-Base --adapter <run>/train/adapter --out <dir> [--device cpu]
Steps: load base (bf16) + PeftModel, record the special-token rows (151644/151645) of embed_tokens and lm_head as the
adapter model sees them, merge_and_unload, check the merged rows equal them and differ from the base, check the
merged model's next-token distribution matches the adapter model's on a short prompt (same top-5 in order,
probabilities within 0.01; raw logits move by bf16 rounding), save
with the tokenizer and train/chat_template.jinja. Writes <out>/merge.json: per-file SHA-256, manifest_sha256 (SHA-256
of the sorted "<sha256>  <file>" lines), adapter SHA-256, checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
ROWS = [151644, 151645]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def rows(model) -> dict[str, torch.Tensor]:
    """The special-token rows as the model computes them (through any trainable-token wrapper)."""
    ids = torch.tensor(ROWS, device=next(model.parameters()).device)
    with torch.no_grad():
        emb = model.get_input_embeddings()(ids).float().cpu()
    return {"embed_tokens": emb, "lm_head": _head_rows(model.get_output_embeddings(), ids)}


def _head_rows(head, ids) -> torch.Tensor:
    # effective lm_head row j = the logits of token j for the unit vectors e_0 … e_{hidden-1}, in chunks of 512
    hid = model_hidden(head)
    dt = next(head.parameters()).dtype
    out = []
    with torch.no_grad():
        for start in range(0, hid, 512):
            e = torch.zeros(min(512, hid - start), hid, dtype=dt, device=ids.device)
            e[torch.arange(e.shape[0]), torch.arange(start, start + e.shape[0])] = 1
            out.append(head(e)[:, ids].float().cpu())
    return torch.cat(out).T  # len(ROWS) x hidden


def model_hidden(head) -> int:
    w = [p for n, p in head.named_parameters() if n.endswith("weight") and p.dim() == 2]
    return w[0].shape[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    t0 = time.time()
    out = Path(a.out)
    assert not out.exists(), f"{out} exists (names are never reused)"
    tok = AutoTokenizer.from_pretrained(a.base)
    tok.chat_template = (ROOT / "train" / "chat_template.jinja").read_text(encoding="utf-8")
    base = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16).to(a.device)
    base_rows = rows(base)
    model = PeftModel.from_pretrained(base, a.adapter).eval()
    probe = tok.apply_chat_template([{"role": "user", "content": "How do I freeze my card?"}], tokenize=False,
                                    add_generation_prompt=True)
    enc = tok(probe, return_tensors="pt", add_special_tokens=False).to(a.device)
    with torch.no_grad():
        ref_logits = model(**enc).logits[0, -1].float().cpu()
    ad_rows = rows(model)
    merged = model.merge_and_unload().eval()
    m_rows = rows(merged)
    with torch.no_grad():
        m_logits = merged(**enc).logits[0, -1].float().cpu()
    checks = {}
    for k in ("embed_tokens", "lm_head"):
        checks[f"{k}_rows_equal_adapter"] = bool(torch.allclose(m_rows[k], ad_rows[k], atol=1e-2))
        checks[f"{k}_rows_differ_from_base"] = bool((m_rows[k] - base_rows[k]).abs().max() > 1e-3)
    checks["logits_max_abs_diff"] = round(float((m_logits - ref_logits).abs().max()), 4)
    checks["same_top5"] = m_logits.topk(5).indices.tolist() == ref_logits.topk(5).indices.tolist()
    checks["probs_max_abs_diff"] = round(float((m_logits.softmax(-1) - ref_logits.softmax(-1)).abs().max()), 5)
    # bf16 merge rounding: logits of magnitude ~20-30 move by a few bf16 steps (0.125-0.25), so the check is on
    # the distribution: same top-5 tokens in order, next-token probabilities within 0.01
    ok = all(checks[k] for k in checks if k.endswith(("_adapter", "_base", "top5"))) and checks["probs_max_abs_diff"] <= 0.01
    print(json.dumps(checks))
    assert ok, f"merge check failed: {checks}"
    merged.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    files = {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file()}
    manifest = "".join(f"{h}  {n}\n" for n, h in sorted(files.items()))
    ad = Path(a.adapter) / "adapter_model.safetensors"
    meta = {"base": a.base, "adapter": a.adapter, "adapter_sha256": sha256(ad), "rows": ROWS, "dtype": "bf16",
            "device": a.device, "checks": checks, "files": files,
            "manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(), "wall_clock_s": round(time.time() - t0, 1)}
    (out / "merge.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"merged -> {out}; manifest_sha256 {meta['manifest_sha256']}")


if __name__ == "__main__":
    main()
