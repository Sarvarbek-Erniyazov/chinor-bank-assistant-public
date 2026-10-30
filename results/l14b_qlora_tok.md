# Tier-L (fixed): 14B QLoRA rsLoRA + trainable special-token rows (eval on the NF4 base)

`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the diagnostic cut column is never the official score.

| Arm | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | diagnostic: Assistant if cut at intended end | McNemar vs base (run-only / base-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base-14B-0shot-A` (base) | 45 | 0 | 0 | 1 | 10 | 20 | 14 | 20 | 0 | 0 | 10 | 2 | 0.0 | 45 | — |
| `l14b_qlora_rslora_tok-s0` | 143 | 89 | 2 | 0 | 16 | 21 | 15 | 20 | 0 | 0 | 1 | 0 | 100.0 | 143 | 103 / 5, p = 7.2e-25 |
| `l14b_qlora_rslora_tok-s1` | 143 | 91 | 0 | 0 | 15 | 22 | 15 | 20 | 0 | 1 | 0 | 0 | 100.0 | 143 | 102 / 4, p = 1.3e-25 |
| `l14b_qlora_rslora_tok-s2` | 143 | 90 | 0 | 1 | 18 | 20 | 14 | 20 | 0 | 0 | 1 | 0 | 100.0 | 143 | 104 / 6, p = 3.5e-24 |
| **mean ± std (n = 3)** | 143.0 ± 0.0 | 90.0 ± 1.0 | 0.7 ± 1.2 | 0.3 ± 0.6 | 16.3 ± 1.5 | 21.0 ± 1.0 | 14.7 ± 0.6 | 20.0 ± 0.0 | 0.0 ± 0.0 | 0.3 ± 0.6 | 0.7 ± 0.6 | 0.0 ± 0.0 | 100.0 ± 0.0 | 143.0 ± 0.0 | |

Stop reasons (220 answers): `l14b_qlora_rslora_tok-s0` im_end 220; `l14b_qlora_rslora_tok-s1` im_end 220; `l14b_qlora_rslora_tok-s2` im_end 220.
Acceptance (>= 95 % of answers stop on <|im_end|>, every run): **pass**.
