# Preference optimisation: DPO vs SimPO vs SFT (14B)

`eval/pref_results.py`. All runs start from sft-merged (14B rsLoRA v1.2 seed 0 merged in bf16; manifest e4d24cc5…, docs/compute.md) with a fresh rsLoRA (r 16, α 32), lr 1e-5, 2 epochs, effective batch 16, on the rule-labelled pairs (`data/pref/v1/pairs_rules.jsonl`, DATA_CARD). DPO β 0.1 (reference = sft-merged); SimPO β 2.0, γ 1.0. Eval-v1 under Protocol A; red-team = redteam-v1 (60 items). Labels were not checked by the judge (dropped this session); κ(rules, author) on 60 blind pairs follows in `results/judge_calibration.md`.

## Eval-v1 (pass counts; mean ± SD over seeds)

| Arm | Seeds | Assistant /200 | T-seen /100 | T-held /20 | B1 /20 | B2 /20 | B3 /25 | B4 /15 |
|---|---|---|---|---|---|---|---|---|
| SFT (v1.2 seed 0) | 1 | 145.0 | 92.0 | 1.0 | 1.0 | 16.0 | 20.0 | 15.0 |
| DPO (rules) | 3 | 145.0 ± 1.7 | 92.3 ± 1.2 | 1.0 ± 0.0 | 1.3 ± 0.6 | 15.0 ± 1.0 | 20.3 ± 0.6 | 15.0 ± 0.0 |
| SimPO (rules) | 3 | 143.7 ± 2.3 | 91.3 ± 0.6 | 1.0 ± 0.0 | 1.0 ± 0.0 | 15.3 ± 2.1 | 20.0 ± 0.0 | 15.0 ± 0.0 |
| RFT (exploratory, ADR-033) | 1 | 149.0 | 94.0 | 1.0 | 1.0 | 16.0 | 22.0 | 15.0 |

## Differences (Δ passes; Holm over the 28 comparisons)

| Comparison | Block | Δ [95 % CI] | Bootstrap p | McNemar seed 0 (A only / B only) | Holm p |
|---|---|---|---|---|---|
| DPO (rules) − SFT (v1.2 seed 0) | Assistant | +0.0 [-2.7, 2.7] | 1.000 | 3 / 2 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | T-seen | +0.3 [-0.7, 1.3] | 0.783 | 1 / 0 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | T-held | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B1 | +0.3 [-1.0, 1.7] | 0.836 | 1 / 1 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B2 | -1.0 [-2.7, 0.7] | 0.336 | 0 / 1 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B3 | +0.3 [0.0, 1.0] | 0.703 | 1 / 0 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | Assistant | -1.3 [-4.0, 1.3] | 0.406 | 4 / 4 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | T-seen | -0.7 [-2.0, 0.7] | 0.436 | 1 / 2 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | T-held | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B1 | +0.0 [-1.7, 1.7] | 1.000 | 1 / 1 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B2 | -0.7 [-2.7, 1.0] | 0.576 | 2 / 1 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B3 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | Assistant | +4.0 [-3.0, 11.0] | 0.313 | 8 / 4 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | T-seen | +2.0 [-2.0, 6.0] | 0.446 | 3 / 1 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | T-held | +0.0 [-3.0, 3.0] | 1.000 | 1 / 1 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B1 | +0.0 [-3.0, 3.0] | 1.000 | 1 / 1 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B2 | +0.0 [-3.0, 3.0] | 1.000 | 1 / 1 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B3 | +2.0 [0.0, 5.0] | 0.251 | 2 / 0 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| DPO (rules) − SimPO (rules) | Assistant | +1.3 [-0.7, 3.3] | 0.264 | 3 / 2 | 1.000 |
| DPO (rules) − SimPO (rules) | T-seen | +1.0 [0.0, 2.3] | 0.088 | 2 / 0 | 1.000 |
| DPO (rules) − SimPO (rules) | T-held | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |
| DPO (rules) − SimPO (rules) | B1 | +0.3 [0.0, 1.0] | 0.717 | 0 / 0 | 1.000 |
| DPO (rules) − SimPO (rules) | B2 | -0.3 [-1.7, 1.0] | 0.843 | 0 / 2 | 1.000 |
| DPO (rules) − SimPO (rules) | B3 | +0.3 [0.0, 1.0] | 0.703 | 1 / 0 | 1.000 |
| DPO (rules) − SimPO (rules) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | 1.000 |

## Red-team, output length, stops

| Arm | attack_success (lower better) | safe_and_helpful | Mean tokens (assistant items) | p90 tokens |
|---|---|---|---|---|
| SFT (v1.2 seed 0) | 7/300 = 2.3% [1.1%, 4.7%] | 248/300 = 82.7% | 60 | 81 |
| DPO (rules) | 1/180 = 0.6% [0.1%, 3.1%] | 148/180 = 82.2% | 60 | 81 |
| SimPO (rules) | 4/180 = 2.2% [0.9%, 5.6%] | 143/180 = 79.4% | 60 | 81 |
| RFT (exploratory, ADR-033) | 3/60 = 5.0% [1.7%, 13.7%] | 51/60 = 85.0% | 61 | 85 |

The SFT red-team row pools the 5 seeds of 14B rsLoRA v1.2 (seed 0 alone is in `results/redteam.md` per seed).

## Training: reward accuracy and margin

| Run | Pairs | Steps | Final loss | Reward accuracy (last 10 steps) | Margin (last 10 steps) | Chosen / rejected length |
|---|---|---|---|---|---|---|
| `pref_dpo_rules-s0` | 348 | 42 | 0.653 | 0.89 | 0.12 | 67 / 63 |
| `pref_dpo_rules-s1` | 348 | 42 | 0.621 | 0.89 | 0.12 | 66 / 62 |
| `pref_dpo_rules-s2` | 348 | 42 | 0.649 | 0.91 | 0.12 | 68 / 62 |
| `pref_simpo_rules-s0` | 348 | 42 | 1.241 | 0.80 | 0.13 | 67 / 63 |
| `pref_simpo_rules-s1` | 348 | 42 | 1.235 | 0.79 | 0.11 | 66 / 62 |
| `pref_simpo_rules-s2` | 348 | 42 | 1.238 | 0.81 | 0.13 | 68 / 62 |
