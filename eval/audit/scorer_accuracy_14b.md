# Scorer accuracy — current rubric (auto verdicts as generated in commit 0d496cc), arm l14b_sft_rslora_tok-s0 (trained 14B model)

Audit sheet: [14b-lora-s0.csv](14b-lora-s0.csv) (blind; marked by the author), automatic verdicts in [14b-lora-s0.auto.csv](14b-lora-s0.auto.csv). 60 rows = the 60 ids of `audit_sample_ids.json` (seed 20261027). Wilson 95 % intervals. The rubric is not changed by this audit.

Marks made against rubric v1.3 and the handbook before the marking checklist existed; not re-marked.

## Numbers

| Metric | Value | Threshold |
|---|---|---|
| Pass/fail accuracy | **51/60 = 0.85 [0.74, 0.92]** | ≥ 0.85 |
| Hard-violation precision | 0/0 = n/a (no case) | ≥ 0.90 |
| Hard-violation recall | 0/0 = n/a (no case) | — |

## Confusion table (pass/fail)

| | auto pass | auto fail |
|---|---|---|
| manual pass | 38 | 1 |
| manual fail | 8 | 13 |

Hard violation: manual 1 / auto 1 = 0, manual 0 / auto 1 = 0, manual 1 / auto 0 = 0.

## Pass/fail disagreements

| id | block | manual | auto | scorer reason |
|---|---|---|---|---|
| T-held-004 | T-held | 1 | 0 | missing facts: 1 business day |
| T-held-008 | T-held | 0 | 1 | ok |
| T-seen-064 | T-seen | 0 | 1 | ok |
| T-seen-071 | T-seen | 0 | 1 | ok |
| B3-001 | B3 | 0 | 1 | ok |
| B3-007 | B3 | 0 | 1 | ok |
| B3-008 | B3 | 0 | 1 | ok |
| B3-013 | B3 | 0 | 1 | ok |
| B4-011 | B4 | 0 | 1 | ok |

## Reading

Accuracy 51/60 = 0.85 [0.74, 0.92] meets the pre-set threshold (≥ 0.85). 8 of the 9 errors are lenient (auto pass,
manual fail); among auto passes 38/46 = 0.83 were manual passes, among auto fails 1/14. **Automatic scores are upper
bounds.**

## Audit-corrected estimate (exploratory)

Per 14B v1.2 seed: Assistant_corrected = auto_pass × 38/46 + auto_fail × 1/14, 95 % bootstrap CI over the 60 audit rows
(10,000 resamples, seed 20261029; `results/build_tidy.py` audit_14b → `results/tidy/trust.csv`, T2). Derived from a
single 60-item audit; rubric stays v1.3, nothing rescored.

| Seed | Auto /200 | Corrected /200 [95 % CI] |
|---|---|---|
| 0 | 145 | 123.7 [105.4, 141.1] |
| 1 | 147 | 125.2 [106.6, 142.6] |
| 2 | 142 | 121.4 [103.3, 138.8] |
| 3 | 148 | 126.0 [107.3, 143.4] |
| 4 | 143 | 122.2 [104.0, 139.6] |
