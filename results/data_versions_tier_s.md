# SFT data versions: v1 vs v1.1 vs v1.2 (`tier_s_main_rslora_tok`, SFT rsLoRA + trainable token rows)

`eval/data_versions.py`. Protocol A, rubric v1.3. v1 canonical answers (ADR-024); v1.1 = v1 + B1 / B1-dialogue repeated 4× (ADR-028); v1.2 = v1.1 + 60 handoff examples (ADR-029). Mean ± std over seeds. T over-refusal = over-refusal flags on T-seen + T-held.

| Version | n | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | T over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 | 3 | 133.0 ± 3.0 | 86.7 ± 1.2 | 2.0 ± 0.0 | 0.0 ± 0.0 | 11.7 ± 1.5 | 17.7 ± 1.2 | 15.0 ± 0.0 | 18.7 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| v1.2 | 3 | 138.0 ± 2.0 | 87.0 ± 1.7 | 1.7 ± 0.6 | 1.3 ± 0.6 | 15.0 ± 1.0 | 18.3 ± 0.6 | 14.7 ± 0.6 | 19.0 ± 0.0 | 0.0 ± 0.0 | 0.3 ± 0.6 | 1.0 ± 1.0 | 0.0 ± 0.0 | 1.0 ± 1.0 |

## Paired comparisons

Δ = first − second, in items passed. Bootstrap: 95 % CI and p over 10,000 resamples. McNemar per seed: first-only / second-only passes, exact p.

| Comparison | Block (items) | Δ mean [95 % CI] | bootstrap p | McNemar seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|---|---|
| v1.2 − v1 | Assistant (200) | +5.0 [0.0, 10.3] | 0.062 | 13 / 10, p = 0.68 | 9 / 7, p = 0.80 | 16 / 6, p = 0.05 |
| v1.2 − v1 | T-seen (100) | +0.3 [-3.0, 3.7] | 0.932 | 5 / 5, p = 1.00 | 2 / 4, p = 0.69 | 6 / 3, p = 0.51 |
| v1.2 − v1 | T-held (20) | -0.3 [-1.0, 0.0] | 0.719 | 0 / 0, p = 1.00 | 0 / 0, p = 1.00 | 0 / 1, p = 1.00 |
| v1.2 − v1 | B1 (20) | +1.3 [0.3, 2.7] | 0.033 | 2 / 0, p = 0.50 | 1 / 0, p = 1.00 | 1 / 0, p = 1.00 |
| v1.2 − v1 | B2 (20) | +3.3 [0.3, 6.3] | 0.029 | 4 / 3, p = 1.00 | 5 / 1, p = 0.22 | 7 / 2, p = 0.18 |
| v1.2 − v1 | B3 (25) | +0.7 [-1.0, 2.3] | 0.601 | 2 / 1, p = 1.00 | 1 / 2, p = 1.00 | 2 / 0, p = 0.50 |
| v1.2 − v1 | B4 (15) | -0.3 [-1.0, 0.0] | 0.715 | 0 / 1, p = 1.00 | 0 / 0, p = 1.00 | 0 / 0, p = 1.00 |
| v1.2 − v1 | R (20) | +0.3 [0.0, 1.0] | 0.713 | 1 / 0, p = 1.00 | 0 / 0, p = 1.00 | 0 / 0, p = 1.00 |

## T-held (the block the v1.2 handoff examples target)

Per seed: T-held passes /20 and the class of the 20 answers (eval/t_held_analysis.py: (a) a training intent's canonical answer, (b) handoff / don't know, (c) other). Paired bootstrap rows for T-held are in the table above.

| Version | Seed 0 | Seed 1 | Seed 2 | Mean passes | Mean (a) / (b) / (c) |
|---|---|---|---|---|---|
| v1 | 2 pass; 17 / 0 / 3 | 2 pass; 18 / 1 / 1 | 2 pass; 19 / 0 / 1 | 2.0 | 18.0 / 0.3 / 1.7 |
| v1.2 | 2 pass; 14 / 0 / 6 | 2 pass; 17 / 0 / 3 | 1 pass; 19 / 0 / 1 | 1.7 | 16.7 / 0.0 / 3.3 |

## Decision rule

- v1.2: Assistant 138.0; T over-refusal 1.0; B2 15.0, B3 18.3 → eligible
- v1: Assistant 133.0; T over-refusal 0.0; B2 11.7, B3 17.7 → eligible

Pending: v1.1 incomplete; current leader among complete versions: v1.2.
