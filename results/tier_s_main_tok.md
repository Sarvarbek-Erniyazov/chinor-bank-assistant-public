# Tier-S main (fixed): 1.7B SFT rsLoRA + trainable special-token rows

`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the diagnostic cut column is never the official score.

| Arm | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | diagnostic: Assistant if cut at intended end | McNemar vs base (run-only / base-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base-1.7B-0shot-A` (base) | 36 | 0 | 0 | 1 | 4 | 16 | 15 | 2 | 5 | 0 | 22 | 4 | 0.0 | 36 | — |
| `tier_s_main_rslora_tok-s0` | 133 | 86 | 2 | 0 | 13 | 17 | 15 | 18 | 0 | 0 | 0 | 0 | 100.0 | 133 | 104 / 7, p = 2.8e-23 |
| `tier_s_main_rslora_tok-s1` | 136 | 88 | 2 | 0 | 12 | 19 | 15 | 19 | 0 | 0 | 0 | 0 | 100.0 | 136 | 104 / 4, p = 3.4e-26 |
| `tier_s_main_rslora_tok-s2` | 130 | 86 | 2 | 0 | 10 | 17 | 15 | 19 | 0 | 0 | 0 | 0 | 100.0 | 130 | 100 / 6, p = 4.5e-23 |
| **mean ± std (n = 3)** | 133.0 ± 3.0 | 86.7 ± 1.2 | 2.0 ± 0.0 | 0.0 ± 0.0 | 11.7 ± 1.5 | 17.7 ± 1.2 | 15.0 ± 0.0 | 18.7 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 133.0 ± 3.0 | |

Stop reasons (220 answers): `tier_s_main_rslora_tok-s0` im_end 220; `tier_s_main_rslora_tok-s1` im_end 220; `tier_s_main_rslora_tok-s2` im_end 220.
Acceptance (>= 95 % of answers stop on <|im_end|>, every run): **pass**.
