# SFT data v1.2_rft (ADR-033, exploratory)

`data/sft/build_rft.py`. SFT v1.2 (2,951 train rows, `data/sft/v1.2`) plus 348 on-policy rows: the chosen responses of `data/pref/v1/pairs_rules.jsonl` (samples of sft-merged that passed every rule; 279 task, 69 behaviour / handoff). Train rows: 3,299; val: v1.2's (147 rows, unchanged).

Contamination of the added user turns and responses vs eval-v1 and redteam-v1 user turns (285): exact 0, rapidfuzz ratio >= 90 0.
