---
license: apache-2.0
base_model: Qwen/Qwen3-14B-Base
library_name: peft
tags: [lora, rslora, sft, customer-support, fictional-bank]
---

# Chinor assistant — Qwen3-14B-Base SFT (rsLoRA, v1.2, seed 0)

**Upload pending** — this adapter is not on the Hugging Face Hub yet (deferred; docs/limitations.md). It is kept on the
training server; sha256 of `adapter_model.safetensors`: `3f3707fd740e5aad3ee940afce1a97abb6b63741329256a1ebcb2fa22f60003f` (from sft-merged merge.json) (run `l14b_sft_rslora_tok-s0-v1.2`).

An rsLoRA adapter that turns Qwen/Qwen3-14B-Base into the support assistant of **Chinor Bank, a fictional bank**. Every policy,
fee and number it knows was invented for this project; it must not be used to answer questions about any real bank.

- **Training:** SFT on 2,696 handbook conversations (data v1.2), rsLoRA r 16 with the trained `<|im_start|>` / `<|im_end|>` rows (PEFT trainable_token_indices).
- **Prompt format:** the frozen system prompt `handbook/system_prompt.txt` and template `train/chat_template.jinja`;
  stop on `<|im_end|>` (151645).
- **Evaluation (eval-v1, 220 frozen items, Protocol A, greedy):** Assistant 145 / 200 for this seed (results/preference.md). Red-team (redteam-v1): see `results/redteam.md`.
- **Limits:** recalls a memorised answer of a different topic on most held-out banking topics (0–2 of 20 right);
  rarely asks for a missing detail (B1); English only; fictional facts only.
