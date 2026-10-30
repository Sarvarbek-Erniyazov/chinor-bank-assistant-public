"""Preference training (C4 §6): DPO or SimPO with a fresh rsLoRA on sft-merged.

python train/pref.py --config train/configs/pref_dpo_rules.yaml --seed 0 --out <dir>
Policy: sft-merged (14B rsLoRA v1.2 seed 0, merged in bf16 by train/merge_sft.py) + a fresh rsLoRA (r 16, alpha 32,
all linear projections). DPO reference: the same model with the adapter disabled (= sft-merged), never the raw base.
SimPO has no reference model.
  DPO:   loss = -log σ(β[(log πθ(yw) - log πref(yw)) - (log πθ(yl) - log πref(yl))]),  β = 0.1
  SimPO: loss = -log σ(β/|yw| · log πθ(yw) - β/|yl| · log πθ(yl) - γ),                 β = 2.0, γ = 1.0
log π(y) = sum of token log-probs over the assistant tokens only (train/sft.py tokenize: the same masking as SFT);
|y| = number of those tokens. Optional SFT term (config sft_alpha, default 0): loss += α · (-log πθ(yw) / |yw|), the
per-token NLL of the chosen response; α = 0 is pure DPO / SimPO. Step-0 check (DPO): the policy starts equal to the
reference (fresh LoRA, B = 0), so the first step's mean preference loss must be ln 2 ± 0.01; otherwise the run aborts. Rewards: DPO β(log πθ - log πref), SimPO β/|y| · log πθ; reward accuracy = share of
pairs with chosen reward > rejected reward. AdamW, lr 1e-5, cosine, 10 % warmup, 2 epochs, effective batch 16 pairs,
max_length 1024, bf16, gradient checkpointing.
Writes <out>/adapter/, <out>/loss.csv (step, epoch, loss, reward_acc, chosen_reward, rejected_reward, margin,
chosen_len, rejected_len, lr) and <out>/run.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
import yaml

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = ROOT / "handbook" / "system_prompt.txt"
LOG_FIELDS = ["step", "epoch", "loss", "reward_acc", "chosen_reward", "rejected_reward", "margin", "chosen_len",
              "rejected_len", "lr"]


def seq_logps(logits: torch.Tensor, labels: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Summed log-probs of the labelled tokens (labels != -100) and their count, per sequence.
    logits[:, t] predicts labels[:, t + 1] (causal shift)."""
    logits, labels = logits[:, :-1].float(), labels[:, 1:]
    mask = labels != -100
    lp = torch.gather(F.log_softmax(logits, -1), 2, labels.clamp(min=0).unsqueeze(-1)).squeeze(-1)
    return (lp * mask).sum(-1), mask.sum(-1)


def dpo_loss(pc, pr, rc, rr, beta: float = 0.1) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """pc / pr: policy log π of chosen / rejected; rc / rr: reference. Returns per-pair loss and the two rewards."""
    cw, rw = beta * (pc - rc), beta * (pr - rr)
    return -F.logsigmoid(cw - rw), cw, rw


def simpo_loss(pc, pr, lc, lr, beta: float = 2.0, gamma: float = 1.0) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """pc / pr: policy log π of chosen / rejected; lc / lr: their lengths in tokens."""
    cw, rw = beta * pc / lc, beta * pr / lr
    return -F.logsigmoid(cw - rw - gamma), cw, rw


def with_sft(loss: torch.Tensor, pc: torch.Tensor, lc: torch.Tensor, alpha: float = 0.0) -> torch.Tensor:
    """Per-pair preference loss plus alpha times the per-token NLL of the chosen response."""
    return loss + alpha * (-pc / lc) if alpha else loss


def step0_ok(loss_mean: float, tol: float = 0.01) -> bool:
    return abs(loss_mean - math.log(2)) <= tol


def pad(rows: list[dict], pad_id: int) -> dict:
    n = max(len(r["input_ids"]) for r in rows)
    ids = torch.full((len(rows), n), pad_id, dtype=torch.long)
    labels = torch.full((len(rows), n), -100, dtype=torch.long)
    attn = torch.zeros((len(rows), n), dtype=torch.long)
    for k, r in enumerate(rows):
        m = len(r["input_ids"])
        ids[k, :m], labels[k, :m], attn[k, :m] = torch.tensor(r["input_ids"]), torch.tensor(r["labels"]), 1
    return {"input_ids": ids, "labels": labels, "attention_mask": attn}


def encode_pairs(tok, pairs: list[dict], max_length: int) -> list[dict]:
    from sft import tokenize
    system = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    out = []
    for p in pairs:
        msgs = [{"role": "system", "content": system}] + p["messages"]
        c = tokenize(tok, msgs + [{"role": "assistant", "content": p["chosen"]}], max_length)
        r = tokenize(tok, msgs + [{"role": "assistant", "content": p["rejected"]}], max_length)
        if any(l != -100 for l in c["labels"]) and any(l != -100 for l in r["labels"]):
            out.append({"chosen": c, "rejected": r})
    return out


def lr_at(step: int, total: int, warmup: int, peak: float) -> float:
    if step < warmup:
        return peak * (step + 1) / warmup
    return peak * 0.5 * (1 + math.cos(math.pi * (step - warmup) / max(1, total - warmup)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-steps", type=int, default=None, help="smoke test")
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    assert cfg["loss"] in ("dpo", "simpo")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(cfg["model"])
    tok.chat_template = (ROOT / "train" / "chat_template.jinja").read_text(encoding="utf-8")
    pairs = [json.loads(l) for l in (ROOT / cfg["pairs"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    data = encode_pairs(tok, pairs, cfg["max_length"])
    model = AutoModelForCausalLM.from_pretrained(cfg["model"], dtype=torch.bfloat16).to("cuda")
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    l = cfg["lora"]
    model = get_peft_model(model, LoraConfig(r=l["r"], lora_alpha=l["alpha"], lora_dropout=l["dropout"],
                                             target_modules=l["target_modules"], use_rslora=True, bias="none",
                                             task_type="CAUSAL_LM"))
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=cfg["learning_rate"], weight_decay=0.0)
    micro, accum = cfg["per_device_train_batch_size"], cfg["gradient_accumulation_steps"]
    assert micro * accum == 16, "effective batch is 16 pairs"
    steps_per_epoch = len(data) // 16
    total = a.max_steps or steps_per_epoch * cfg["num_train_epochs"]
    warmup = max(1, round(cfg["warmup_ratio"] * total))
    beta, gamma, alpha = cfg["beta"], cfg.get("gamma", 0.0), cfg.get("sft_alpha", 0.0)
    step0 = None
    order = []
    for e in range(cfg["num_train_epochs"]):
        idx = list(range(len(data)))
        random.Random(a.seed * 1000 + e).shuffle(idx)
        order += idx[: steps_per_epoch * 16]
    log, t0 = [], time.time()
    model.train()
    for step in range(total):
        for g in opt.param_groups:
            g["lr"] = lr_at(step, total, warmup, cfg["learning_rate"])
        stats = []
        for m in range(accum):
            batch = [data[i] for i in order[(step * 16 + m * micro): (step * 16 + (m + 1) * micro)]]
            enc = {k: v.to("cuda") for k, v in pad([b["chosen"] for b in batch] + [b["rejected"] for b in batch], tok.pad_token_id).items()}
            lp, n = seq_logps(model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).logits, enc["labels"])
            pc, pr, lc, lr_ = lp[:micro], lp[micro:], n[:micro], n[micro:]
            if cfg["loss"] == "dpo":
                with torch.no_grad(), model.disable_adapter():
                    rlp, _ = seq_logps(model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).logits, enc["labels"])
                loss, cw, rw = dpo_loss(pc, pr, rlp[:micro], rlp[micro:], beta)
            else:
                loss, cw, rw = simpo_loss(pc, pr, lc, lr_, beta, gamma)
            pref_loss = loss
            loss = with_sft(loss, pc, lc.float(), alpha)
            (loss.mean() / accum).backward()
            stats.append((pref_loss.detach(), cw.detach(), rw.detach(), lc.float(), lr_.float()))
        if step == 0:
            step0 = torch.cat([x[0] for x in stats]).mean().item()
            print(json.dumps({"step0_pref_loss": round(step0, 6), "ln2": round(math.log(2), 6)}), flush=True)
            if cfg["loss"] == "dpo" and not step0_ok(step0):
                raise SystemExit(f"step-0 check failed: DPO loss {step0:.4f} is not ln 2 ± 0.01 (policy != reference at start)")
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        cat = lambda j: torch.cat([s[j] for s in stats])
        cw, rw = cat(1), cat(2)
        row = {"step": step + 1, "epoch": round((step + 1) / steps_per_epoch, 3) if steps_per_epoch else 0,
               "loss": cat(0).mean().item(), "reward_acc": (cw > rw).float().mean().item(), "chosen_reward": cw.mean().item(),
               "rejected_reward": rw.mean().item(), "margin": (cw - rw).mean().item(), "chosen_len": cat(3).mean().item(),
               "rejected_len": cat(4).mean().item(), "lr": opt.param_groups[0]["lr"]}
        log.append(row)
        if (step + 1) % 10 == 0 or step + 1 == total:
            print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}), flush=True)
    model.save_pretrained(out / "adapter")
    with (out / "loss.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(log)
    ad = out / "adapter" / "adapter_model.safetensors"
    merge = Path(cfg["model"]) / "merge.json"
    meta = {"config": a.config, "config_values": cfg, "seed": a.seed, "pairs": cfg["pairs"],
            "pairs_sha256": hashlib.sha256((ROOT / cfg["pairs"]).read_bytes()).hexdigest(), "pairs_used": len(data),
            "steps": total, "step0_pref_loss": step0, "sft_alpha": alpha, "sft_merged_manifest_sha256": json.loads(merge.read_text())["manifest_sha256"] if merge.exists() else None,
            "adapter_sha256": hashlib.sha256(ad.read_bytes()).hexdigest(), "wall_clock_s": round(time.time() - t0, 1),
            "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1e9, 3), "gpu": torch.cuda.get_device_name(0),
            "final": log[-1] if log else None}
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "train"))
    main()
