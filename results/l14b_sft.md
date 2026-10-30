# Tier-L without trainable special-token rows: 14B SFT rsLoRA, lr 1e-4

`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the diagnostic cut column is never the official score.

| Arm | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | diagnostic: Assistant if cut at intended end | McNemar vs base (run-only / base-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base-14B-0shot-A` (base) | 45 | 0 | 0 | 1 | 10 | 20 | 14 | 20 | 0 | 0 | 10 | 2 | 0.0 | 45 | — |
| `l14b_sft_rslora-s0` | 160 | 86 | 2 | 16 | 19 | 22 | 15 | 20 | 0 | 5 | 1 | 0 | 0.0 | 147 | 117 / 2, p = 2.1e-32 |
| `l14b_sft_rslora-s1` | 145 | 80 | 2 | 14 | 16 | 20 | 13 | 20 | 0 | 13 | 0 | 2 | 0.0 | 147 | 106 / 6, p = 9.8e-25 |
| `l14b_sft_rslora-s2` | 152 | 88 | 2 | 11 | 18 | 20 | 13 | 20 | 0 | 5 | 0 | 3 | 0.0 | 147 | 111 / 4, p = 3.5e-28 |
| **mean ± std (n = 3)** | 152.3 ± 7.5 | 84.7 ± 4.2 | 2.0 ± 0.0 | 13.7 ± 2.5 | 17.7 ± 1.5 | 20.7 ± 1.2 | 13.7 ± 1.2 | 20.0 ± 0.0 | 0.0 ± 0.0 | 7.7 ± 4.6 | 0.3 ± 0.6 | 1.7 ± 1.5 | 0.0 ± 0.0 | 147.0 ± 0.0 | |

Stop reasons (220 answers): `l14b_sft_rslora-s0` length 219, endoftext 1; `l14b_sft_rslora-s1` length 220; `l14b_sft_rslora-s2` length 220.
