# Judge calibration: rules and judge vs the author (C4 §5)

`data/pref/calibration.py kappa`. 60 blind pairs (`eval/audit/pairs_human.csv`), A/B order random per row. Cohen's κ on A / B / tie; 95 % bootstrap CI over rows (10,000 resamples, seed 20261029). Pre-registered: the rules ∩ judge DPO arm is trained only if κ(judge, author) ≥ 0.6.

Author's marks: {'B': 36, 'A': 24}.

| Rater vs author | κ [95 % CI] | κ without the author's ties | Raw agreement |
|---|---|---|---|
| rules | 0.97 [0.88, 1.00] | 0.97 (n = 60) | 59/60 |

| Failure type | Rows | Author agrees with rules |
|---|---|---|
| fabricated_number | 8 | 8 |
| hard_violation | 1 | 1 |
| missing_fact | 8 | 8 |
| other | 3 | 2 |
| wrong_topic | 40 | 40 |

Author's ties: 0/60. Raw agreement counts a tie as disagreement (the rules always pick A or B).

No judge labels (§4 dropped this session): κ(rules, author) validates the rule labels of the pairs the DPO / SimPO runs used; it was computed after training and did not gate it.
