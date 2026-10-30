# Tier-S main without trainable special-token rows: 1.7B SFT rsLoRA (ADR-025)

`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the diagnostic cut column is never the official score.

| Arm | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | diagnostic: Assistant if cut at intended end | McNemar vs base (run-only / base-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base-1.7B-0shot-A` (base) | 36 | 0 | 0 | 1 | 4 | 16 | 15 | 2 | 5 | 0 | 22 | 4 | 0.0 | 36 | — |
| `tier_s_main_rslora-s0` | 147 | 84 | 0 | 15 | 14 | 19 | 15 | 19 | 0 | 9 | 4 | 0 | 0.0 | 132 | 118 / 7, p = 4.0e-27 |
| `tier_s_main_rslora-s1` | 141 | 91 | 2 | 0 | 16 | 17 | 15 | 20 | 0 | 1 | 1 | 0 | 0.0 | 141 | 112 / 7, p = 1.8e-25 |
| `tier_s_main_rslora-s2` | 133 | 86 | 2 | 1 | 11 | 18 | 15 | 20 | 0 | 0 | 1 | 1 | 0.0 | 131 | 102 / 5, p = 1.4e-24 |
| **mean ± std (n = 3)** | 140.3 ± 7.0 | 87.0 ± 3.6 | 1.3 ± 1.2 | 5.3 ± 8.4 | 13.7 ± 2.5 | 18.0 ± 1.0 | 15.0 ± 0.0 | 19.7 ± 0.6 | 0.0 ± 0.0 | 3.3 ± 4.9 | 2.0 ± 1.7 | 0.3 ± 0.6 | 0.0 ± 0.0 | 134.7 ± 5.5 | |

Stop reasons (220 answers): `tier_s_main_rslora-s0` length 220; `tier_s_main_rslora-s1` length 220; `tier_s_main_rslora-s2` length 220.
