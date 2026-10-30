"""SFT-LoRA on SFT data v1 with transformers.Trainer (Stage 2).

python train/sft.py --config train/configs/tier_s_pilot_lora.yaml --seed 0 --out <dir> [--max-steps N] [--save-steps N]
                    [--stop-at N] [--no-eval] [--data-dir data/sft/_provisional]

Config switches besides LoRA (throughput probes, later stages): `quant: nf4` loads the frozen base in 4-bit NF4
with bf16 compute (QLoRA); `full_ft: true` trains every parameter, embeddings and lm_head included (no LoRA).

Data: data/sft/v1/{train,val}.jsonl (messages). Every example is rendered with train/chat_template.jinja and
tokenised here; labels are the token ids on the assistant spans marked by the template's {% generation %}
blocks (the same rule as train/tests/test_masking.py) and -100 everywhere else. The collator pads on the
right and sets the label of every position with attention_mask 0 to -100 (by position, not by token id:
pad == eos == <|endoftext|> for Qwen3). LoRA / QLoRA: only adapter weights train, never embed_tokens or
lm_head (tied or untied); full FT: every parameter trains. Both are asserted (check_trainable, ADR-023), and
run.json records tie_word_embeddings (tied in Qwen3 0.6B / 1.7B / 4B, untied in 8B / 14B).

No TRL and no `datasets` (ADR-020): on the H200 image, TRL 1.16 and datasets 5.1 need pyarrow >= 21/24,
which needs NumPy 2, while the image's torch is built for NumPy 1. Runs from chinor/venv-gen.

<out>/ckpt/      trainer checkpoints (save_steps); a run resumes from the latest one automatically
<out>/adapter/   final LoRA adapter (LoRA, QLoRA)
<out>/model/     final weights and tokenizer (full fine-tuning; with save_steps 0 no intermediate checkpoints)
<out>/run.json   COMMIT, config hash, data manifest hash, seed, gpu, dtype, peak VRAM, tokens/s, wall-clock,
                 trainable parameters, final train/val loss, resume information
<out>/loss.csv   step, epoch, loss, eval_loss, learning_rate, grad_norm
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import yaml

# transformers.Trainer imports `datasets` whenever it is importable. On the H200, venv-gen sees the image's own
# `datasets` through --system-site-packages, which fails against huggingface_hub 2.3 (HfFolder). This module
# never uses `datasets` (ADR-020), so it is hidden before transformers is imported anywhere in the process.
sys.modules.setdefault("datasets", None)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "train" / "chat_template.jinja"
DATA = ROOT / "data" / "sft" / "v1"
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
EFFECTIVE_BATCH = 16
REQUIRED = ["model", "max_length", "per_device_train_batch_size", "gradient_accumulation_steps", "learning_rate",
            "warmup_ratio", "num_train_epochs", "weight_decay", "optim", "group_by_length"]


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in cfg]
    assert not missing, f"{path}: missing keys {missing}"
    assert cfg["per_device_train_batch_size"] * cfg["gradient_accumulation_steps"] == EFFECTIVE_BATCH, \
        f"{path}: effective batch must be {EFFECTIVE_BATCH}"
    if cfg.get("full_ft"):
        assert "lora" not in cfg and not cfg.get("quant"), f"{path}: full fine-tuning has no LoRA block and no quantisation"
        return cfg
    lora = cfg.get("lora")
    assert lora, f"{path}: missing key lora"
    assert sorted(lora["target_modules"]) == sorted(LORA_TARGETS), f"{path}: LoRA must target {LORA_TARGETS}"
    assert not (lora.get("use_rslora") and lora.get("use_dora")), f"{path}: rslora and dora are separate variants"
    assert cfg.get("quant") in (None, "nf4"), f"{path}: quant must be nf4 or absent"
    return cfg


def config_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def data_manifest() -> dict:
    """sha256 of manifest.sha256 plus the train/val hashes it lists (C1 §4)."""
    m = DATA / "manifest.sha256"
    files = dict(reversed(line.split("  ", 1)) for line in m.read_text(encoding="utf-8").splitlines() if line.strip())
    for name in ("train.jsonl", "val.jsonl"):
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == files[name], f"{name} differs from manifest"
    return {"manifest_sha256": hashlib.sha256(m.read_bytes()).hexdigest(),
            "train.jsonl": files["train.jsonl"], "val.jsonl": files["val.jsonl"]}


def load_tokenizer(model_id: str):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    tok.chat_template = TEMPLATE.read_text(encoding="utf-8")
    assert tok.pad_token_id is not None
    return tok


def tokenize(tok, messages: list[dict], max_length: int) -> dict:
    """input_ids and labels (-100 outside assistant spans), truncated to max_length."""
    enc = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=False,
                                  return_assistant_tokens_mask=True, return_dict=True)
    ids, mask = list(enc["input_ids"]), list(enc["assistant_masks"])
    labels = [i if m == 1 else -100 for i, m in zip(ids, mask)]
    return {"input_ids": ids[:max_length], "labels": labels[:max_length]}


def build_dataset(tok, split: str, max_length: int) -> tuple[list[dict], dict]:
    """A list of {"input_ids", "labels"}: a plain map-style dataset (Trainer infers lengths from input_ids)."""
    rows = [json.loads(l) for l in (DATA / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    ds = [tokenize(tok, r["messages"], max_length) for r in rows]
    stats = {"examples": len(rows), "tokens": sum(len(t["input_ids"]) for t in ds),
             "supervised_tokens": sum(sum(l != -100 for l in t["labels"]) for t in ds),
             "truncated": sum(len(t["input_ids"]) == max_length for t in ds)}
    return ds, stats


class PadCollator:
    """Right-pad input_ids with pad_id; attention_mask 1 on real tokens; labels -100 wherever attention_mask is 0."""

    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, features: list[dict]) -> dict:
        import torch
        n = max(len(f["input_ids"]) for f in features)
        ids = torch.full((len(features), n), self.pad_id, dtype=torch.long)
        labels = torch.full((len(features), n), -100, dtype=torch.long)
        attn = torch.zeros((len(features), n), dtype=torch.long)
        for k, f in enumerate(features):
            m = len(f["input_ids"])
            ids[k, :m] = torch.tensor(f["input_ids"], dtype=torch.long)
            labels[k, :m] = torch.tensor(f["labels"], dtype=torch.long)
            attn[k, :m] = 1
        labels[attn == 0] = -100
        return {"input_ids": ids, "attention_mask": attn, "labels": labels}


def lora_config(cfg: dict, tied: bool = True):
    """lora.trainable_token_rows (ADR-023 amended): these rows of embed_tokens and lm_head train as well, via PEFT
    trainable_token_indices. Tied models (Qwen3 0.6B / 1.7B / 4B): embed_tokens only; peft 0.21 puts a tied layer
    on lm_head that shares the same delta. Untied (8B / 14B): embed_tokens and lm_head each get their own delta."""
    from peft import LoraConfig
    l = cfg["lora"]
    rows = l.get("trainable_token_rows")
    tokens = None if not rows else ({"embed_tokens": list(rows)} if tied else {"embed_tokens": list(rows), "lm_head": list(rows)})
    return LoraConfig(r=l["r"], lora_alpha=l["alpha"], lora_dropout=l["dropout"], target_modules=l["target_modules"],
                      use_rslora=bool(l.get("use_rslora", False)), use_dora=bool(l.get("use_dora", False)),
                      trainable_token_indices=tokens, bias="none", task_type="CAUSAL_LM")


def check_trainable(model, full_ft: bool = False, token_rows: list[int] | None = None) -> dict:
    """LoRA / QLoRA: adapter parameters train, never the full embed_tokens or lm_head (tied or untied); with
    token_rows, exactly those rows train in addition: one delta of len(rows) x hidden when tied, one each for
    embed_tokens and lm_head when untied. Full FT: every parameter trains (trainable count == total count).
    Parameters are counted once each, so a tied embedding / lm_head (and a tied delta) counts once."""
    trainable = [(n, p.numel()) for n, p in model.named_parameters() if p.requires_grad]
    n_train = sum(c for _, c in trainable)
    n_all = sum(p.numel() for p in model.parameters())
    out = {"trainable": n_train, "total": n_all, "percent": round(100 * n_train / n_all, 4)}
    if full_ft:
        assert n_train == n_all, f"full FT: {n_train:,} of {n_all:,} parameters trainable"
        return out
    rows = [(n, c) for n, c in trainable if "trainable_tokens_delta" in n]
    bad = [n for n, _ in trainable if ("lora_" not in n and "trainable_tokens_delta" not in n)
           or (("embed_tokens" in n or "lm_head" in n) and "trainable_tokens_delta" not in n)]
    assert trainable and not bad, f"non-adapter trainable parameters: {bad[:5]}"
    if token_rows:
        cfg = model.config
        hidden, tied = cfg.hidden_size, bool(getattr(cfg, "tie_word_embeddings", False))
        expect = len(token_rows) * hidden * (1 if tied else 2)
        assert sum(c for _, c in rows) == expect, f"token-row parameters {sum(c for _, c in rows):,} != {expect:,} ({rows})"
        out["token_rows"] = {"ids": list(token_rows), "parameters": expect, "tied": tied}
    else:
        assert not rows, f"token rows train without lora.trainable_token_rows: {rows}"
    return out


def latest_checkpoint(ckpt_dir: Path) -> str | None:
    c = sorted(ckpt_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])) if ckpt_dir.exists() else []
    return str(c[-1]) if c else None


def build_trainer(cfg: dict, seed: int, out: Path, max_steps: int | None = None, save_steps: int | None = None,
                  evaluate: bool = True):
    import torch
    from peft import get_peft_model
    from transformers import AutoModelForCausalLM, Trainer, TrainingArguments, set_seed

    set_seed(seed)  # LoRA initialisation depends on it
    tok = load_tokenizer(cfg["model"])
    train_ds, train_stats = build_dataset(tok, "train", cfg["max_length"])
    val_ds, val_stats = build_dataset(tok, "val", cfg["max_length"])
    kw = {}
    if cfg.get("quant") == "nf4":
        from transformers import BitsAndBytesConfig
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                       bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(cfg["model"], dtype=torch.bfloat16, attn_implementation="sdpa", **kw)
    if not cfg.get("full_ft"):
        if cfg.get("quant") == "nf4":
            from peft import prepare_model_for_kbit_training
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                                    gradient_checkpointing_kwargs={"use_reentrant": False})
        model = get_peft_model(model, lora_config(cfg, tied=bool(model.config.tie_word_embeddings)))
        model.enable_input_require_grads()  # gradient checkpointing with frozen embeddings
    args = TrainingArguments(
        output_dir=str(out / "ckpt"), seed=seed, data_seed=seed,
        bf16=True, use_cpu=not torch.cuda.is_available(),  # CPU only in tests
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=cfg.get("per_device_eval_batch_size", cfg["per_device_train_batch_size"]),
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["learning_rate"], lr_scheduler_type="cosine", warmup_steps=cfg["warmup_ratio"],
        num_train_epochs=cfg["num_train_epochs"], max_steps=max_steps if max_steps else -1,
        weight_decay=cfg["weight_decay"], optim=cfg["optim"],
        # transformers 5 replaced group_by_length=True with this sampler option
        train_sampling_strategy="group_by_length" if cfg["group_by_length"] else "random",
        eval_strategy="steps" if evaluate else "no", eval_steps=cfg.get("eval_steps", 50),
        # save_steps 0 in a config: no intermediate checkpoints. 14B full FT: save_total_limit 1 and save_only_model
        # (one rolling weights-only checkpoint, no optimizer state; a crash fallback, not resumable with the optimizer)
        save_strategy="steps" if (save_steps or cfg.get("save_steps", 100)) else "no",
        save_steps=save_steps or cfg.get("save_steps", 100) or 100,
        save_total_limit=cfg.get("save_total_limit", 2), save_only_model=cfg.get("save_only_model", False),
        logging_steps=cfg.get("logging_steps", 10), report_to="none",
        remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
                      data_collator=PadCollator(tok.pad_token_id), processing_class=tok)
    return trainer, tok, {"train": train_stats, "val": val_stats}


def commit_id() -> str:
    f = ROOT / "COMMIT"
    if f.exists():
        return f.read_text().strip()
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def write_loss_csv(log_history: list[dict], path: Path) -> None:
    keys = ["step", "epoch", "loss", "eval_loss", "learning_rate", "grad_norm"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        last = None
        for row in log_history:
            if "loss" in row or "eval_loss" in row:
                rec = {k: row.get(k) for k in keys}
                if rec != last:  # the final evaluation can appear twice after a resume
                    w.writerow(rec)
                last = rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-steps", type=int, default=None, help="dry run only")
    ap.add_argument("--save-steps", type=int, default=None, help="dry run only")
    ap.add_argument("--no-eval", action="store_true", help="throughput probes: no evaluation during or after training")
    ap.add_argument("--data-dir", default=None, help="default data/sft/v1; data/sft/_provisional for mechanics-only runs")
    ap.add_argument("--stop-at", type=int, default=None,
                    help="dry run only: end training cleanly after this global step (after its checkpoint is saved)")
    a = ap.parse_args()
    import torch

    commit = commit_id()  # read at start: a later sync_up rewrites COMMIT
    global DATA
    if a.data_dir:
        DATA = (ROOT / a.data_dir) if not Path(a.data_dir).is_absolute() else Path(a.data_dir)
    cfg = load_config(a.config)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = data_manifest()
    trainer, tok, data_stats = build_trainer(cfg, a.seed, out, a.max_steps, a.save_steps, evaluate=not a.no_eval)
    params = check_trainable(trainer.model, full_ft=bool(cfg.get("full_ft")),
                             token_rows=None if cfg.get("full_ft") else cfg["lora"].get("trainable_token_rows"))
    print(f"trainable parameters: {params['trainable']:,} of {params['total']:,} ({params['percent']} %)", flush=True)

    if a.stop_at:
        from transformers import TrainerCallback

        class StopAt(TrainerCallback):
            def on_step_end(self, args, state, control, **kw):
                if state.global_step >= a.stop_at:
                    control.should_training_stop = True
                    control.should_save = True
                return control
        trainer.add_callback(StopAt())

    resume = latest_checkpoint(out / "ckpt")
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    result = trainer.train(resume_from_checkpoint=resume)
    wall = time.time() - t0
    trainer.save_model(str(out / ("model" if cfg.get("full_ft") else "adapter")))
    final_eval = {} if a.no_eval else trainer.evaluate()

    steps_done = trainer.state.global_step - (int(Path(resume).name.split("-")[1]) if resume else 0)
    frac = steps_done / max(1, trainer.state.max_steps)  # share of the full run done in this process
    epochs = cfg["num_train_epochs"] if not a.max_steps else trainer.state.epoch
    tokens = data_stats["train"]["tokens"] * epochs * frac
    sup = data_stats["train"]["supervised_tokens"] * epochs * frac
    if a.max_steps:  # partial epoch: estimate from the examples actually seen
        seen = steps_done * cfg["per_device_train_batch_size"] * cfg["gradient_accumulation_steps"]
        tokens = data_stats["train"]["tokens"] / data_stats["train"]["examples"] * seen
        sup = data_stats["train"]["supervised_tokens"] / data_stats["train"]["examples"] * seen
    train_losses = [r["loss"] for r in trainer.state.log_history if "loss" in r]
    run = {
        "config": a.config, "config_hash": config_hash(a.config), "config_values": cfg, "seed": a.seed,
        "COMMIT": commit, "data_dir": str(DATA.relative_to(ROOT)) if DATA.is_relative_to(ROOT) else str(DATA),
        "data": manifest, "data_stats": data_stats,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu", "dtype": "bf16",
        "torch": torch.__version__, "python": platform.python_version(),
        "trainable_parameters": params, "mode": "full_ft" if cfg.get("full_ft") else ("qlora" if cfg.get("quant") else "lora"),
        "tie_word_embeddings": bool(getattr(trainer.model.config, "tie_word_embeddings", False)),
        "resumed_from": resume, "global_step": trainer.state.global_step, "max_steps": trainer.state.max_steps,
        "steps_this_process": steps_done,
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else None,
        "wall_clock_s": round(wall, 1),
        "tokens_per_s": round(tokens / wall, 1), "supervised_tokens_per_s": round(sup / wall, 1),
        "train_runtime_s": result.metrics.get("train_runtime"),
        "final_train_loss": train_losses[-1] if train_losses else None,
        "mean_train_loss": result.metrics.get("train_loss"),
        "final_val_loss": final_eval.get("eval_loss"),
    }
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8", newline="\n")
    write_loss_csv(trainer.state.log_history, out / "loss.csv")
    print(json.dumps({k: run[k] for k in ("global_step", "peak_vram_gb", "tokens_per_s", "supervised_tokens_per_s",
                                          "wall_clock_s", "final_train_loss", "final_val_loss")}, indent=2))


if __name__ == "__main__":
    main()
    # Every output is written; skip interpreter teardown, which segfaulted once after a finished run
    # (robust-determinism, 2026-10-29, exit 139) and would abort train_eval.sh before the eval step.
    # An exception in main() still exits non-zero above.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
