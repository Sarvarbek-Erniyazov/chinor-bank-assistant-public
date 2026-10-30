# Ablation: LoRA without trainable special-token rows

`eval/results_tables.py`. Runs trained before the ADR-023 amendment: `<|im_start|>` / `<|im_end|>` rows frozen, so the models never emit `<|im_end|>` and run on to the 200-token limit (`docs/limitations.md`). Official score = rubric v1.3 on the whole answer; the diagnostic cut column (`eval/turn_cut.py`) is never official. The 0.6B pilot matrix is not rerun: all its arms share the flaw, and the rsLoRA decision (ADR-025) holds after the cut. Fixed counterpart = same config + trainable rows, where it exists.

| Arm | n | Official Assistant /200 | Diagnostic: cut at intended end | <|im_end|> stops % | Fixed counterpart: official Assistant /200 | Fixed: <|im_end|> stops % |
|---|---|---|---|---|---|---|
| 0.6B plain LoRA (pilot) | 3 | 124.7 ± 4.7 | 122.0 ± 5.3 | 0.0 ± 0.0 | — | — |
| 0.6B rsLoRA (pilot) | 3 | 136.0 ± 6.6 | 135.3 ± 5.0 | 0.0 ± 0.0 | — | — |
| 0.6B DoRA (pilot) | 3 | 116.3 ± 4.7 | 118.7 ± 2.5 | 0.0 ± 0.0 | — | — |
| 0.6B LoRA paged 8-bit (pilot) | 3 | 119.3 ± 8.1 | 119.0 ± 4.6 | 0.0 ± 0.0 | — | — |
| 0.6B LoRA group_by_length false (pilot) | 1 | 121.0 | 120.0 | 0.0 | — | — |
| 1.7B rsLoRA (Tier-S main) | 3 | 140.3 ± 7.0 | 134.7 ± 5.5 | 0.0 ± 0.0 | 133.0 ± 3.0 | 100.0 ± 0.0 |
| 14B rsLoRA lr 1e-4 | 3 | 152.3 ± 7.5 | 147.0 ± 0.0 | 0.0 ± 0.0 | 143.7 ± 2.9 | 100.0 ± 0.0 |
