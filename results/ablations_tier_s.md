# Tier-S pilot ablations (Qwen3-0.6B-Base, SFT v1, Protocol A, rubric v1.3)

`eval/ablation_report.py`. Mean ± std over seeds (n per row). Assistant /200 = T-seen + T-held + B1–B4; retention /20 is reported separately. Flags (HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success) are counted on the 200 assistant items; per-seed rows in results/seeds.md.

| Config | n | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | Peak VRAM (GB) | Tokens/s | Train wall-clock (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain LoRA (reference) | 3 | 124.7 ± 4.7 | 73.0 ± 2.6 | 0.0 ± 0.0 | 10.3 ± 0.6 | 13.0 ± 1.7 | 13.7 ± 2.1 | 14.7 ± 0.6 | 15.7 ± 2.3 | 0.3 ± 0.6 | 13.3 ± 4.2 | 1.7 ± 0.6 | 1.0 ± 0.0 | 18.88 ± 0.00 | 20260 ± 55 | 215 ± 1 |
| rsLoRA | 3 | 136.0 ± 6.6 | 81.0 ± 6.6 | 0.3 ± 0.6 | 7.0 ± 4.6 | 15.3 ± 2.3 | 17.7 ± 1.5 | 14.7 ± 0.6 | 11.3 ± 2.1 | 0.7 ± 1.2 | 8.3 ± 8.5 | 3.7 ± 2.5 | 0.7 ± 0.6 | 18.88 ± 0.00 | 20277 ± 64 | 215 ± 1 |
| DoRA | 3 | 116.3 ± 4.7 | 66.7 ± 6.1 | 0.3 ± 0.6 | 10.3 ± 1.5 | 10.7 ± 1.5 | 14.3 ± 1.5 | 14.0 ± 0.0 | 16.7 ± 0.6 | 0.0 ± 0.0 | 22.0 ± 7.8 | 0.7 ± 0.6 | 1.7 ± 0.6 | 18.89 ± 0.00 | 11784 ± 8 | 370 ± 0 |
| LoRA + paged 8-bit AdamW | 3 | 119.3 ± 8.1 | 70.3 ± 4.6 | 0.3 ± 0.6 | 7.7 ± 1.5 | 12.0 ± 1.0 | 14.3 ± 1.2 | 14.7 ± 0.6 | 15.7 ± 1.5 | 0.0 ± 0.0 | 16.7 ± 4.6 | 3.0 ± 2.0 | 1.0 ± 0.0 | 18.82 ± 0.00 | 19743 ± 34 | 221 ± 0 |
| LoRA, group_by_length false | 1 | 121.0 | 68.0 | 0.0 | 9.0 | 13.0 | 16.0 | 15.0 | 20.0 | 0.0 | 23.0 | 0.0 | 1.0 | 18.87 | 19309 | 226 |

## Variants vs plain LoRA

SE of the difference = sqrt(s_variant²/n_variant + s_LoRA²/n_LoRA); for a single-seed variant the LoRA seed spread is used for both. McNemar: exact, seed-0 pair, 200 assistant items.

| Variant | Δ mean Assistant /200 | SE of Δ | Δ > 2 SE | McNemar seed 0 (variant-only / LoRA-only, p) |
|---|---|---|---|---|
| rsLoRA | +11.3 | 4.7 | yes | 30 / 11, p = 0.004 |
| DoRA | -8.3 | 3.9 | no | 16 / 21, p = 0.511 |
| LoRA + paged 8-bit AdamW | -5.3 | 5.4 | no | 18 / 17, p = 1.000 |
| LoRA, group_by_length false | -3.7 | 5.5 | no | 21 / 23, p = 0.880 |

## Decision rule

A variant is adopted for Tier S main only if its mean Assistant /200 exceeds plain LoRA by more than twice the SE of the difference; the optimizer on the same rule, VRAM saving noted either way; group_by_length is kept if tokens/s improves with no score change beyond the seed spread. Otherwise plain LoRA, adamw_torch, group_by_length true.

- Adapter: **rsLoRA**.
- Optimizer: **adamw_torch**; peak VRAM 18.88 GB (adamw_torch) vs 18.82 GB (paged 8-bit), saving +0.06 GB.
- group_by_length: **true**; tokens/s 20,260 (true) vs 19,309 (false); Assistant /200 with false (seed 0) = 121, LoRA seed range 121–130.
