# 14B: LoRA vs QLoRA vs full fine-tuning

`eval/lora_vs_qlora.py`. Protocol A, rubric v1.3, SFT v1. Mean ± std over seeds. QLoRA is evaluated on the NF4 base it was trained on. LoRA / QLoRA: rsLoRA r 16, lr 1e-4, trainable special-token rows; full FT: lr 1e-5. Flags on the 200 assistant items. Wall-clock = training only. Artifact = adapter file (fp32) or full bf16 weights. Full-FT rows hold only for their settings; with one seed at lr 2e-5 they are not a general claim about LoRA vs full fine-tuning.

| Arm | n | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | Peak train VRAM (GB) | Tokens/s | Train wall-clock (min) | Artifact (GB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LoRA (bf16 base, adamw_torch) | 3 | 143.7 ± 2.9 | 90.7 ± 0.6 | 1.3 ± 1.2 | 1.0 ± 0.0 | 14.7 ± 0.6 | 21.0 ± 2.6 | 15.0 ± 0.0 | 20.0 ± 0.0 | 0.3 ± 0.6 | 0.7 ± 1.2 | 0.0 ± 0.0 | 1.0 ± 1.0 | 100.0 ± 0.0 | 40.3 | 3,422 | 21.3 | 0.26 |
| QLoRA (NF4 base, paged_adamw_8bit) | 3 | 143.0 ± 0.0 | 90.0 ± 1.0 | 0.7 ± 1.2 | 0.3 ± 0.6 | 16.3 ± 1.5 | 21.0 ± 1.0 | 14.7 ± 0.6 | 20.0 ± 0.0 | 0.0 ± 0.0 | 0.3 ± 0.6 | 0.7 ± 0.6 | 0.0 ± 0.0 | 100.0 ± 0.0 | 26.5 | 2,790 | 26.1 | 0.26 |
| full FT lr 1e-5, 3 epochs (bf16, adamw_bnb_8bit) | 2 | 121.0 ± 5.7 | 81.5 ± 2.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 4.2 | 16.5 ± 0.7 | 14.0 ± 0.0 | 20.0 ± 0.0 | 0.0 ± 0.0 | 0.5 ± 0.7 | 0.0 ± 0.0 | 1.5 ± 0.7 | 92.8 ± 0.6 | 92.7 | 2,462 | 29.6 | 29.54 |
| full FT lr 2e-5, 3 epochs (diagnosis run, ADR-030) | 2 | 142.0 ± 1.4 | 91.0 ± 0.0 | 0.5 ± 0.7 | 0.0 ± 0.0 | 15.5 ± 0.7 | 20.5 ± 0.7 | 14.5 ± 0.7 | 20.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 99.8 ± 0.4 | 92.7 | 2,460 | 29.6 | 29.54 |

QLoRA: seeds verified distinct (adapter hashes, 87–101/220 answers differ between seed pairs, pass/fail differs on 12–14 items); identical totals are coincidental.

| Seed | LoRA | QLoRA | McNemar (QLoRA-only / LoRA-only, p) |
|---|---|---|---|
| 0 | 147 | 143 | 5 / 9, p = 0.42 |
| 1 | 142 | 143 | 7 / 6, p = 1.00 |
| 2 | 142 | 143 | 11 / 10, p = 1.00 |

## Full FT: lr 1e-5 vs lr 2e-5 (same seed = same data order)

| Seed | Full FT lr 1e-5 | Full FT lr 2e-5 | LoRA | McNemar lr 2e-5 vs lr 1e-5 (2e-5-only / 1e-5-only, p) | McNemar lr 2e-5 vs LoRA (full-only / LoRA-only, p) |
|---|---|---|---|---|---|
| 0 | 125 | 141 | 147 | 20 / 4, p = 0.002 | 4 / 10, p = 0.180 |
| 1 | 117 | 143 | 142 | 30 / 4, p < 0.001 | 10 / 9, p = 1.000 |

With tuned learning rate, full fine-tuning (141, 143) is close to LoRA (147, 142, same seeds). Neither per-seed McNemar test separates them; this holds for these settings (3 epochs, lr 2e-5), not as a general claim.
