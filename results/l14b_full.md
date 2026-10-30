# Tier-L: Qwen3-14B-Base full fine-tuning

`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the diagnostic cut column is never the official score.

| Arm | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % | diagnostic: Assistant if cut at intended end | McNemar vs base (run-only / base-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base-14B-0shot-A` (base) | 45 | 0 | 0 | 1 | 10 | 20 | 14 | 20 | 0 | 0 | 10 | 2 | 0.0 | 45 | — |
| `l14b_full-s0` | 125 | 83 | 0 | 0 | 12 | 16 | 14 | 20 | 0 | 1 | 0 | 1 | 92.3 | 125 | 91 / 11, p = 8.0e-17 |
| `l14b_full-s1` | 117 | 80 | 0 | 0 | 6 | 17 | 14 | 20 | 0 | 0 | 0 | 2 | 93.2 | 117 | 83 / 11, p = 8.0e-15 |
| **mean ± std (n = 2)** | 121.0 ± 5.7 | 81.5 ± 2.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 4.2 | 16.5 ± 0.7 | 14.0 ± 0.0 | 20.0 ± 0.0 | 0.0 ± 0.0 | 0.5 ± 0.7 | 0.0 ± 0.0 | 1.5 ± 0.7 | 92.8 ± 0.6 | 121.0 ± 5.7 | |

Stop reasons (220 answers): `l14b_full-s0` im_end 203, length 12, endoftext 5; `l14b_full-s1` im_end 205, length 12, endoftext 3.
