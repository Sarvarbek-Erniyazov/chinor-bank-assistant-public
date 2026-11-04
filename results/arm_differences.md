# Arm differences: Δ Assistant /200 with 95 % CI

`eval/arm_differences.py`. Protocol A, rubric v1.3. Δ = A − B in assistant items passed (of 200); paired bootstrap over items stratified by seed (10,000 resamples, seed 20261029; strata matched by seed index), exact McNemar on seed 0. **Holm family:** the 8 Assistant-level comparisons in this table (m = 8). Preference arms (DPO / SimPO − SFT seed 0) are in `results/preference.md` (their own family). A row without a significant difference is worded "no significant difference detected; Δ = x [95 % CI]"; it is not evidence of equivalence.

| Comparison | Seeds | A /200 | B /200 | Δ [95 % CI] | Bootstrap p | McNemar seed 0 (A only / B only, p) | Holm p (m = 8) |
|---|---|---|---|---|---|---|---|
| 14B QLoRA − 14B LoRA (SFT v1) | 3 | 143.0 | 143.7 | -0.7 [-5.3, 4.0] | 0.835 | 5 / 9, 0.42 | 1.000 |
| 14B full FT lr 2e-5 − 14B LoRA (SFT v1, seeds 0–1) | 2 | 142.0 | 144.5 | -2.5 [-8.0, 3.0] | 0.435 | 4 / 10, 0.18 | 1.000 |
| 4B − 14B (SFT rsLoRA v1) | 3 | 142.7 | 143.7 | -1.0 [-5.3, 3.3] | 0.727 | 6 / 6, 1.00 | 1.000 |
| 8B − 14B (SFT rsLoRA v1) | 3 | 141.0 | 143.7 | -2.7 [-7.7, 2.3] | 0.311 | 7 / 11, 0.48 | 1.000 |
| 4B − 8B (SFT rsLoRA v1) | 3 | 142.7 | 141.0 | +1.7 [-2.3, 5.7] | 0.471 | 7 / 3, 0.34 | 1.000 |
| data v1.1 − v1 (14B rsLoRA, seeds 0–2) | 3 | 141.7 | 143.7 | -2.0 [-6.7, 2.7] | 0.439 | 4 / 11, 0.12 | 0.948 |
| data v1.2 − v1 (14B rsLoRA, seeds 0–2) | 3 | 144.7 | 143.7 | +1.0 [-4.0, 6.0] | 0.733 | 6 / 8, 0.79 | 1.000 |
| data v1.2 − v1.1 (14B rsLoRA, seeds 0–2) | 3 | 144.7 | 141.7 | +3.0 [-1.0, 7.3] | 0.194 | 11 / 6, 0.33 | 1.000 |
