# Tier-L (fixed): 14B SFT rsLoRA lr 1e-4 + trainable special-token rows

`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the diagnostic cut column is never the official score.

| Arm | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | diagnostic: Assistant if cut at intended end | McNemar vs base (run-only / base-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base-14B-0shot-A` (base) | 45 | 0 | 0 | 1 | 10 | 20 | 14 | 20 | 0 | 0 | 10 | 2 | 0.0 | 45 | — |
| `l14b_sft_rslora_tok-s0` | 147 | 91 | 2 | 1 | 15 | 23 | 15 | 20 | 0 | 2 | 0 | 0 | 100.0 | 147 | 106 / 4, p = 9.2e-27 |
| `l14b_sft_rslora_tok-s1` | 142 | 90 | 0 | 1 | 14 | 22 | 15 | 20 | 0 | 0 | 0 | 1 | 100.0 | 142 | 103 / 6, p = 6.6e-24 |
| `l14b_sft_rslora_tok-s2` | 142 | 91 | 2 | 1 | 15 | 18 | 15 | 20 | 1 | 0 | 0 | 2 | 100.0 | 142 | 105 / 8, p = 1.1e-22 |
| **mean ± std (n = 3)** | 143.7 ± 2.9 | 90.7 ± 0.6 | 1.3 ± 1.2 | 1.0 ± 0.0 | 14.7 ± 0.6 | 21.0 ± 2.6 | 15.0 ± 0.0 | 20.0 ± 0.0 | 0.3 ± 0.6 | 0.7 ± 1.2 | 0.0 ± 0.0 | 1.0 ± 1.0 | 100.0 ± 0.0 | 143.7 ± 2.9 | |

Stop reasons (220 answers): `l14b_sft_rslora_tok-s0` im_end 220; `l14b_sft_rslora_tok-s1` im_end 220; `l14b_sft_rslora_tok-s2` im_end 220.
Acceptance (>= 95 % of answers stop on <|im_end|>, every run): **pass**.
