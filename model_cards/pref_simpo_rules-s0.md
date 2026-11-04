---
license: apache-2.0
base_model: Qwen/Qwen3-14B-Base + the SFT adapter above, merged (sft-merged, manifest e4d24cc5…)
library_name: peft
tags: [lora, rslora, simpo, customer-support, fictional-bank]
---

# Chinor assistant — SimPO on 14B SFT (rule pairs, seed 0)

**Upload pending** — this adapter is not on the Hugging Face Hub yet (deferred; docs/limitations.md). It is kept on the
training server; sha256 of `adapter_model.safetensors`: `7a0b887794a94b3de19cee3131acb580fc3800cc33cdae7667b0b966dbb942b8` (run `pref_simpo_rules-s0`).

An rsLoRA adapter that turns Qwen/Qwen3-14B-Base + the SFT adapter above, merged (sft-merged, manifest e4d24cc5…) into the support assistant of **Chinor Bank, a fictional bank**. Every policy,
fee and number it knows was invented for this project; it must not be used to answer questions about any real bank.

- **Training:** SimPO (β 2.0, γ 1.0) on 348 rule-labelled on-policy pairs (data/pref/v1, DATA_CARD), fresh rsLoRA r 16 α 32, lr 1e-5, 2 epochs. Load on top of sft-merged, not on the raw base.
- **Prompt format:** the frozen system prompt `handbook/system_prompt.txt` and template `train/chat_template.jinja`;
  stop on `<|im_end|>` (151645).
- **Evaluation (eval-v1, 220 frozen items, Protocol A, greedy):** Assistant 145 / 200 for this seed (3-seed mean 143.7 ± 2.3; results/preference.md). Red-team (redteam-v1): 1/60 for this seed; 3-seed 2.2 % [0.0, 10.2] vs SFT seed 0 1.7 % [0.04, 8.9] (BCa cluster bootstrap over attacks for 3 seeds, exact Clopper–Pearson for seed 0; intervals overlap). All six preference runs start from SFT v1.2 seed 0; their seeds vary the preference stage only. Vs SFT seed 0: no significant difference detected; Δ = −1.3 [−4.0, 1.3] /200 (Holm p = 1.0, family m = 21).
- **Limits:** recalls a memorised answer of a different topic on most held-out banking topics (0–2 of 20 right);
  rarely asks for a missing detail (B1); English only; fictional facts only.
- **What the scores mean:** reproduction of one handbook's answers under a lenient rubric (scorer: 51/60 = 0.85 [0.74, 0.92] agreement with one annotator; errors lenient, 8 of 9), so automatic scores are upper bounds. Independent human inter-annotator agreement: not measured; all hand labels by one annotator (intra-rater re-marking not done).
