# Preference optimisation: DPO vs SimPO vs SFT (14B)

`eval/pref_results.py`. All runs start from sft-merged (14B rsLoRA v1.2 seed 0 merged in bf16; manifest e4d24cc5…, docs/compute.md) with a fresh rsLoRA (r 16, α 32), lr 1e-5, 2 epochs, effective batch 16, on the rule-labelled pairs (`data/pref/v1/pairs_rules.jsonl`, DATA_CARD). DPO β 0.1 (reference = sft-merged); SimPO β 2.0, γ 1.0. Eval-v1 under Protocol A; red-team = redteam-v1 (60 items). Labels were not checked by the judge (dropped this session); κ(rules, author) on 60 blind pairs follows in `results/judge_calibration.md`.

**One parent.** All six preference runs (DPO s0–s2, SimPO s0–s2) start from the same SFT checkpoint, 14B rsLoRA v1.2 seed 0; their seeds vary the preference stage only, not SFT. The reference row is therefore SFT seed 0, not the 5-seed SFT mean, and SFT seed-to-seed variation is not part of these comparisons.

## Eval-v1 (pass counts; mean ± SD over seeds)

| Arm | Seeds | Assistant /200 | T-seen /100 | T-held /20 | B1 /20 | B2 /20 | B3 /25 | B4 /15 |
|---|---|---|---|---|---|---|---|---|
| SFT (v1.2 seed 0) | 1 | 145.0 | 92.0 | 1.0 | 1.0 | 16.0 | 20.0 | 15.0 |
| DPO (rules) | 3 | 145.0 ± 1.7 | 92.3 ± 1.2 | 1.0 ± 0.0 | 1.3 ± 0.6 | 15.0 ± 1.0 | 20.3 ± 0.6 | 15.0 ± 0.0 |
| SimPO (rules) | 3 | 143.7 ± 2.3 | 91.3 ± 0.6 | 1.0 ± 0.0 | 1.0 ± 0.0 | 15.3 ± 2.1 | 20.0 ± 0.0 | 15.0 ± 0.0 |
| RFT (exploratory, ADR-033) | 1 | 149.0 | 94.0 | 1.0 | 1.0 | 16.0 | 22.0 | 15.0 |

## Differences (Δ passes)

**Holm families.** Confirmatory: 3 comparisons (DPO (rules) − SFT (v1.2 seed 0); SimPO (rules) − SFT (v1.2 seed 0); DPO (rules) − SimPO (rules)) × 7 rows (Assistant + 6 blocks) = 21 tests, adjusted together. Exploratory: RFT − SFT × 7 rows = 7 tests, adjusted separately (one seed, decided after the main runs, ADR-033). SFT = seed 0, the shared parent of all six preference runs. "No significant difference detected" is not equivalence: read Δ and its CI.

| Comparison | Block | Δ [95 % CI] | Bootstrap p | McNemar seed 0 (A only / B only) | Holm family | Holm p |
|---|---|---|---|---|---|---|
| DPO (rules) − SFT (v1.2 seed 0) | Assistant | +0.0 [-2.7, 2.7] | 1.000 | 3 / 2 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | T-seen | +0.3 [-0.7, 1.3] | 0.783 | 1 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | T-held | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B1 | +0.3 [-1.0, 1.7] | 0.836 | 1 / 1 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B2 | -1.0 [-2.7, 0.7] | 0.336 | 0 / 1 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B3 | +0.3 [0.0, 1.0] | 0.703 | 1 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SFT (v1.2 seed 0) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | Assistant | -1.3 [-4.0, 1.3] | 0.406 | 4 / 4 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | T-seen | -0.7 [-2.0, 0.7] | 0.436 | 1 / 2 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | T-held | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B1 | +0.0 [-1.7, 1.7] | 1.000 | 1 / 1 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B2 | -0.7 [-2.7, 1.0] | 0.576 | 2 / 1 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B3 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| SimPO (rules) − SFT (v1.2 seed 0) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | Assistant | +4.0 [-3.0, 11.0] | 0.313 | 8 / 4 | exploratory (RFT), m = 7 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | T-seen | +2.0 [-2.0, 6.0] | 0.446 | 3 / 1 | exploratory (RFT), m = 7 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | T-held | +0.0 [-3.0, 3.0] | 1.000 | 1 / 1 | exploratory (RFT), m = 7 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B1 | +0.0 [-3.0, 3.0] | 1.000 | 1 / 1 | exploratory (RFT), m = 7 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B2 | +0.0 [-3.0, 3.0] | 1.000 | 1 / 1 | exploratory (RFT), m = 7 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B3 | +2.0 [0.0, 5.0] | 0.251 | 2 / 0 | exploratory (RFT), m = 7 | 1.000 |
| RFT (exploratory, ADR-033) − SFT (v1.2 seed 0) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | exploratory (RFT), m = 7 | 1.000 |
| DPO (rules) − SimPO (rules) | Assistant | +1.3 [-0.7, 3.3] | 0.264 | 3 / 2 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SimPO (rules) | T-seen | +1.0 [0.0, 2.3] | 0.088 | 2 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SimPO (rules) | T-held | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SimPO (rules) | B1 | +0.3 [0.0, 1.0] | 0.717 | 0 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SimPO (rules) | B2 | -0.3 [-1.7, 1.0] | 0.843 | 0 / 2 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SimPO (rules) | B3 | +0.3 [0.0, 1.0] | 0.703 | 1 / 0 | confirmatory, m = 21 | 1.000 |
| DPO (rules) − SimPO (rules) | B4 | +0.0 [0.0, 0.0] | 1.000 | 0 / 0 | confirmatory, m = 21 | 1.000 |

## Red-team, output length, stops

Red-team: the attack is the unit (n = 60); per attack the mean over the arm's seeds. **Intervals (method per row in brackets).** One seed: exact Clopper–Pearson (CP) 95 % interval on k / 60 attacks. Several seeds: point estimate = mean over the 60 attacks of the per-attack seed average; interval = cluster bootstrap over attacks with BCa (10,000 resamples, seed 20261029). Where at most 2 attacks succeed in any seed, the conservative CP interval on "attacks succeeded in ≥ 1 seed" is given as well. SFT = seed 0 only (the parent), not the 5-seed mean in `results/redteam.md`.

| Arm | Seeds | attack_success (lower better) | safe_and_helpful | Mean tokens (assistant items) | p90 tokens |
|---|---|---|---|---|---|
| SFT (v1.2 seed 0) | 1 | 1.7 % [0.04, 8.9] (1/60; CP) | 81.7 % [69.6, 90.5] (49/60; CP) | 60 | 81 |
| DPO (rules) | 3 | 0.6 % [0.0, 3.3] (1/180; BCa; ≥ 1 seed: 1/60 CP [0.04, 8.9]) | 82.2 % [71.7, 90.6] (148/180; BCa) | 60 | 81 |
| SimPO (rules) | 3 | 2.2 % [0.0, 10.2] (4/180; BCa; ≥ 1 seed: 2/60 CP [0.41, 11.5]) | 79.4 % [67.8, 87.8] (143/180; BCa) | 60 | 81 |
| RFT (exploratory, ADR-033) | 1 | 5.0 % [1.0, 13.9] (3/60; CP) | 85.0 % [73.4, 92.9] (51/60; CP) | 61 | 85 |

## Training: reward accuracy and margin

| Run | Pairs | Steps | Final loss | Reward accuracy (last 10 steps) | Margin (last 10 steps) | Chosen / rejected length |
|---|---|---|---|---|---|---|
| `pref_dpo_rules-s0` | 348 | 42 | 0.653 | 0.89 | 0.12 | 67 / 63 |
| `pref_dpo_rules-s1` | 348 | 42 | 0.621 | 0.89 | 0.12 | 66 / 62 |
| `pref_dpo_rules-s2` | 348 | 42 | 0.649 | 0.91 | 0.12 | 68 / 62 |
| `pref_simpo_rules-s0` | 348 | 42 | 1.241 | 0.80 | 0.13 | 67 / 63 |
| `pref_simpo_rules-s1` | 348 | 42 | 1.235 | 0.79 | 0.11 | 66 / 62 |
| `pref_simpo_rules-s2` | 348 | 42 | 1.238 | 0.81 | 0.13 | 68 / 62 |
