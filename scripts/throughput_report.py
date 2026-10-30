"""docs/throughput_h200.md from the throughput probes and the dry run (results/runs/*/run.json).

python scripts/throughput_report.py
Hours per 3-epoch run = 3 x training tokens of the data the probe used / measured tokens per second (training only:
no evaluation, model loading or checkpoint saving). The probes ran 20 optimizer steps on the provisional assembly
(selection v2), whose size is within a few percent of SFT v1.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "Qwen3-0.6B LoRA (dry run, resumed phase)": "c2a-dryrun-tier-s-2/train",
    "Qwen3-1.7B LoRA": "probe-1.7b-lora-2",
    "Qwen3-4B LoRA": "probe-4b-lora",
    "Qwen3-8B LoRA": "probe-8b-lora",
    "Qwen3-14B LoRA": "probe-14b-lora-3",
    "Qwen3-14B QLoRA (NF4)": "probe-14b-qlora",
    "Qwen3-14B full FT (bf16, 8-bit AdamW)": "probe-14b-full-3",
}


def main():
    rows = ["# Throughput on the H200", "",
            "Training throughput measured with 20 optimizer steps (effective batch 16, max_length 1024, bf16, gradient "
            "checkpointing) on the provisional SFT assembly; `scripts/throughput_report.py`. Hours per 3-epoch run = "
            "3 × training tokens / tokens per second, training only (no evaluation, loading or saving).", "",
            "| Config | Batch × accum | Peak VRAM (GB) | Tokens/s | Supervised tokens/s | Trainable | h per 3-epoch run | Run |",
            "|---|---|---|---|---|---|---|---|"]
    for name, rel in RUNS.items():
        p = ROOT / "results" / "runs" / rel / "run.json"
        if not p.exists():
            rows.append(f"| {name} | — | not run | | | | | `{rel.split('/')[0]}` |")
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        c = r["config_values"]
        tok = r["data_stats"]["train"]["tokens"]
        hours = 3 * tok / r["tokens_per_s"] / 3600 if r.get("tokens_per_s") else float("nan")
        tp = r["trainable_parameters"]
        rows.append(f"| {name} | {c['per_device_train_batch_size']} × {c['gradient_accumulation_steps']} | {r['peak_vram_gb']} | "
                    f"{r['tokens_per_s']:,.0f} | {r['supervised_tokens_per_s']:,.0f} | {tp['percent']} % | {hours:.2f} | `{rel.split('/')[0]}` |")
    rows += ["", "Training tokens per epoch (provisional assembly): "
             + (f"{json.loads((ROOT / 'results/runs/probe-1.7b-lora-2/run.json').read_text())['data_stats']['train']['tokens']:,}"
                if (ROOT / "results/runs/probe-1.7b-lora-2/run.json").exists() else "n/a") + ".", ""]
    out = ROOT / "docs" / "throughput_h200.md"
    out.write_text("\n".join(rows), encoding="utf-8", newline="\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
