"""Stage-2a dry run on the H200 (C2a §2): masking on real data, VRAM, throughput, resume.

python train/dryrun.py --config train/configs/tier_s_pilot_lora.yaml --out <dir> [--steps 20] [--data-dir DIR]

1. Builds the trainer and decodes the labels of the first example of one real training batch: every token
   with a label must lie in an assistant span (template mask) and every padded position must be -100.
2. Trains to step steps/2 with --stop-at (checkpoint saved, nothing killed), then relaunches the same command
   without --stop-at: the run must resume from that checkpoint and reach --steps.
3. Writes docs/dryrun_tier_s.md (peak VRAM, tokens/s, masking table, resume check). Exit 1 on any failure,
   or if peak VRAM exceeds 40 GB for the 0.6B pilot.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
import sft  # noqa: E402

VRAM_LIMIT_GB = 40.0
DOC = ROOT / "docs" / "dryrun_tier_s.md"


def masking_check(cfg: dict, out: Path) -> tuple[bool, list[str], dict]:
    import torch
    trainer, tok, _ = sft.build_trainer(cfg, 0, out / "masking", max_steps=1)
    batch = next(iter(trainer.get_train_dataloader()))
    ids, labels = batch["input_ids"][0].tolist(), batch["labels"][0].tolist()
    attn = batch.get("attention_mask")
    attn = attn[0].tolist() if attn is not None else [1] * len(ids)
    n_real = sum(attn)
    # find the example: the unpadded ids are a row of the tokenised training set
    by_ids = {tuple(r["input_ids"]): r["labels"] for r in trainer.train_dataset}
    ref = by_ids.get(tuple(ids[:n_real]))
    problems = []
    if ref is None:
        problems.append("batch example not found in the tokenised training set")
    else:
        bad = [k for k in range(n_real) if labels[k] != ref[k]]
        if bad:
            problems.append(f"{len(bad)} positions whose label differs from the template mask (first {bad[:5]})")
    if any(labels[k] != -100 for k in range(n_real, len(ids))):
        problems.append("a padded position carries a label")
    sup = [i for i, l in zip(ids, labels) if l != -100]
    rows = [f"{'pos':>4} | {'token':<28} | {'id':>7} | label"]
    for k, (i, l) in enumerate(zip(ids, labels)):
        piece = tok.decode([i], skip_special_tokens=False).replace("\n", "\\n")
        rows.append(f"{k:>4} | {piece!r:<28} | {i:>7} | {l}{'  (pad)' if k >= n_real else ''}")
    info = {"tokens": len(ids), "real_tokens": n_real, "supervised": len(sup),
            "supervised_text": tok.decode(sup, skip_special_tokens=False), "table": rows}
    del trainer
    torch.cuda.empty_cache()
    return not problems, problems, info


def run_sft(config: str, out: Path, steps: int, stop_at: int | None, data_dir: str | None) -> dict:
    cmd = [sys.executable, str(ROOT / "train" / "sft.py"), "--config", config, "--seed", "0", "--out", str(out),
           "--max-steps", str(steps), "--save-steps", str(steps // 2)]
    if data_dir:
        cmd += ["--data-dir", data_dir]
    if stop_at:
        cmd += ["--stop-at", str(stop_at)]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    return json.loads((out / "run.json").read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "train" / "configs" / "tier_s_pilot_lora.yaml"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--data-dir", default=None, help="e.g. data/sft/_provisional (mechanics only)")
    a = ap.parse_args()
    if a.data_dir:
        sft.DATA = ROOT / a.data_dir
    cfg = sft.load_config(a.config)
    out = Path(a.out)
    half = a.steps // 2

    mask_ok, mask_problems, mask = masking_check(cfg, out)
    print("masking:", "ok" if mask_ok else mask_problems, flush=True)
    first = run_sft(a.config, out / "train", a.steps, stop_at=half, data_dir=a.data_dir)
    second = run_sft(a.config, out / "train", a.steps, stop_at=None, data_dir=a.data_dir)
    resume_ok = (first["global_step"] == half and second["resumed_from"] is not None
                 and second["resumed_from"].endswith(f"checkpoint-{half}")
                 and second["global_step"] == a.steps and second["steps_this_process"] == a.steps - half)
    vram = max(first["peak_vram_gb"] or 0, second["peak_vram_gb"] or 0)
    vram_ok = vram <= VRAM_LIMIT_GB

    yn = lambda b: "PASS" if b else "**FAIL**"
    lines = [
        "# Dry run — Tier S pilot (Qwen3-0.6B-Base, plain LoRA)", "",
        f"`train/dryrun.py` on {first['gpu']}, bf16, config `{Path(a.config).name}` (hash `{first['config_hash']}`), "
        f"commit `{first['COMMIT']}`, data `{first['data_dir']}` (manifest `{first['data']['manifest_sha256'][:16]}`)"
        + (" — **provisional assembly: mechanics only, not the committed SFT v1 data**" if a.data_dir else "") + ".", "",
        "| Check | Result | Detail |", "|---|---|---|",
        f"| Assistant-only masking on a real batch | {yn(mask_ok)} | {mask['supervised']} of {mask['real_tokens']} tokens supervised"
        f"{'; ' + '; '.join(mask_problems) if mask_problems else ''} |",
        f"| Peak VRAM ≤ {VRAM_LIMIT_GB:.0f} GB | {yn(vram_ok)} | {vram} GB (torch.cuda.max_memory_allocated) |",
        f"| Resume from checkpoint | {yn(resume_ok)} | stopped at step {first['global_step']}, resumed from "
        f"`{Path(second['resumed_from'] or '-').name}`, reached step {second['global_step']} of {second['max_steps']} |", "",
        "| Phase | Steps | Wall-clock (s) | Tokens/s | Supervised tokens/s | Peak VRAM (GB) | Last train loss | Val loss |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, r in (("1: start → stop", first), ("2: resume → end", second)):
        lines.append(f"| {name} | {r['steps_this_process']} | {r['wall_clock_s']} | {r['tokens_per_s']} | "
                     f"{r['supervised_tokens_per_s']} | {r['peak_vram_gb']} | {r['final_train_loss']} | {r['final_val_loss']} |")
    lines += ["", f"Trainable parameters: {first['trainable_parameters']['trainable']:,} of "
              f"{first['trainable_parameters']['total']:,} ({first['trainable_parameters']['percent']} %); "
              "embeddings and lm_head frozen (asserted).", "",
              "## Supervised text of the first example in the batch", "", "```", mask["supervised_text"], "```", "",
              "## Token / label pairs of that example", "", "Label -100 = masked; otherwise the token id.", "",
              "<details><summary>all positions</summary>", "", "```", *mask["table"], "```", "", "</details>", ""]
    (out / DOC.name).write_text("\n".join(lines), encoding="utf-8", newline="\n")  # copied to docs/ after sync_down
    print("\n".join(lines[:16]))
    sys.exit(0 if mask_ok and resume_ok and vram_ok else 1)


if __name__ == "__main__":
    main()
