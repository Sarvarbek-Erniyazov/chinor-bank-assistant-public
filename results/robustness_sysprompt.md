# Robustness: paraphrased system prompt (14B SFT rsLoRA, data v1.2)

`eval/robustness_sysprompt.py`. Same adapters (`l14b_sft_rslora_tok-s<seed>-v1.2`), items and Protocol A; the system prompt is `eval/system_prompt_paraphrase.txt` (every number, hour and channel of the frozen prompt, other wording, 446 tokens; recorded with its SHA-256 in each run.json) instead of `handbook/system_prompt.txt`. Block R is asked without a system prompt.

| Seed | Prompt | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | Identical answers /220 (assistant / R) | Stops on <\|im_end\|> | McNemar (paraphrase-only / original-only, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | original | 145 | 92 | 1 | 1 | 16 | 20 | 15 | 20 | 158 (138 / 20) | 220/220 | — |
| 0 | paraphrase | 144 | 90 | 1 | 1 | 16 | 21 | 15 | 20 | 158 (138 / 20) | 220/220 | 3 / 4, p = 1.00 |
| 1 | original | 147 | 87 | 2 | 5 | 16 | 22 | 15 | 20 | 152 (132 / 20) | 220/220 | — |
| 1 | paraphrase | 142 | 87 | 2 | 4 | 15 | 20 | 14 | 20 | 152 (132 / 20) | 220/220 | 3 / 8, p = 0.23 |
| 2 | original | 142 | 89 | 0 | 1 | 15 | 22 | 15 | 20 | 151 (131 / 20) | 220/220 | — |
| 2 | paraphrase | 139 | 87 | 0 | 2 | 13 | 22 | 15 | 20 | 151 (131 / 20) | 220/220 | 4 / 7, p = 0.55 |

**Pooled (3 seeds):** Assistant /200 original 144.7, paraphrase 141.7; Δ (paraphrase − original) = -3.0 [-6.7, 0.3], paired bootstrap p = 0.112 (10,000 resamples over items, stratified by seed, seed 20261029).
