# Ablation: canonical vs rewritten training answers (14B SFT rsLoRA, seed 0)

`eval/ablation_rewrite.py`. Protocol A, rubric v1.3. Same config (`l14b_sft_rslora_tok.yaml`) and seed; v1_rewrite replaces most canonical task answers with Qwen3-32B paraphrases that passed verifier v2 and the entailment judge (about 1 in 6 still states something the handbook does not; `results/rewrite_funnel.json`).

| Data | Assistant /200 | T-seen | T-held | B1 | B2 | B3 | B4 | R | HV | NUM | OR | INJ | <|im_end|> stops % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SFT v1 (canonical) | 147 | 91 | 2 | 1 | 15 | 23 | 15 | 20 | 0 | 2 | 0 | 0 | 100.0 |
| SFT v1_rewrite (paraphrases) | 140 | 89 | 0 | 1 | 17 | 18 | 15 | 20 | 0 | 1 | 0 | 1 | 100.0 |

McNemar (rewrite-only / canonical-only passes): 5 / 12, p = 0.14.
