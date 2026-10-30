# Throughput on the H200

Training throughput measured with 20 optimizer steps (effective batch 16, max_length 1024, bf16, gradient checkpointing) on the provisional SFT assembly; `scripts/throughput_report.py`. Hours per 3-epoch run = 3 × training tokens / tokens per second, training only (no evaluation, loading or saving).

| Config | Batch × accum | Peak VRAM (GB) | Tokens/s | Supervised tokens/s | Trainable | h per 3-epoch run | Run |
|---|---|---|---|---|---|---|---|
| Qwen3-0.6B LoRA (dry run, resumed phase) | 16 × 1 | 16.6 | 11,518 | 1,308 | 1.665 % | 0.10 | `c2a-dryrun-tier-s-2` |
| Qwen3-1.7B LoRA | 16 × 1 | 21.47 | 12,766 | 1,449 | 1.003 % | 0.09 | `probe-1.7b-lora-2` |
| Qwen3-4B LoRA | — | not run | | | | | `probe-4b-lora` |
| Qwen3-8B LoRA | — | not run | | | | | `probe-8b-lora` |
| Qwen3-14B LoRA | 8 × 2 | 38.3 | 3,328 | 378 | 0.433 % | 0.36 | `probe-14b-lora-3` |
| Qwen3-14B QLoRA (NF4) | 8 × 2 | 26.33 | 2,776 | 315 | 0.7807 % | 0.43 | `probe-14b-qlora` |
| Qwen3-14B full FT (bf16, 8-bit AdamW) | 4 × 4 | 92.51 | 802 | 91 | 100.0 % | 1.50 | `probe-14b-full-3` |

Training tokens per epoch (provisional assembly): 1,439,671.
