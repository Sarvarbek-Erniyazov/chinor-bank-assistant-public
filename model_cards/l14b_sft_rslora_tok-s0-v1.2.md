---
license: apache-2.0
base_model: Qwen/Qwen3-14B-Base
library_name: peft
tags: [lora, rslora, sft, customer-support, fictional-bank]
---

# Chinor assistant: Qwen3-14B-Base SFT (rsLoRA with token rows, data v1.2, seed 0)

> **Fiction notice.** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank.

**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet. The adapter is not in git; `scripts/verify_adapters.py` checks a copy against `results/adapter_sha256.tsv`.

## Identity

| Field | Value |
|---|---|
| Run | `l14b_sft_rslora_tok-s0-v1.2` (`results/runs/l14b_sft_rslora_tok-s0-v1.2/train/run.json`) |
| Base model | `Qwen/Qwen3-14B-Base`, revision `0b0bd3732e2c374d483664439ea334928b65f304` (`docs/base_revisions.md`) |
| Training data | `data/sft/v1.2` (train.jsonl SHA-256 `4868c56cebfcbe12bd898157efd77f62ea1a8d18b0d35ff5b2c069348567dd07`, `data/sft/v1.2/manifest.sha256`) |
| Configuration | `train/configs/l14b_sft_rslora_tok.yaml`, seed 0: rsLoRA r 16, α 32; trained token rows 151644, 151645; lr 0.0001, 3 epochs, max length 1024 |
| `adapter_model.safetensors` SHA-256 | `3f3707fd740e5aad3ee940afce1a97abb6b63741329256a1ebcb2fa22f60003f` (`results/adapter_sha256.tsv`) |
| Prompt format | system prompt `handbook/system_prompt.txt`, template `train/chat_template.jinja`, greedy, stop on `<\|im_end\|>` (151645) or `<\|endoftext\|>` (151643) |

This seed is the one SFT parent of all six DPO / SimPO runs.

## Scores

Eval-v1 (frozen), Protocol A (H200, bf16, greedy), rubric v1.3. Computed by `scripts/build_cards.py` with the functions of `scripts/method_table.py` from `results/tidy/items_long.csv` and `eval/outputs/rt-<run>/redteam_scores.jsonl`.

| Measure | This seed | All seeds of the arm | Source |
|---|---|---|---|
| Assistant /200 | 145 | 145.0 ± 2.5 (5 seeds) | `results/method_table.md`, `results/tidy/arm_summary.csv` |
| Retention /20 (no system prompt) | 20 | 20.0 ± 0.0 | `results/tidy/arm_summary.csv` |
| Δ Assistant vs Qwen3-14B-Base 0-shot [95 % CI] | — | +100.0 [93.2, 106.8] | `results/method_table.md` |
| Red-team attack success (lower is better) | 1.7 % [0.04, 8.9] (1/60; CP) | 2.3 % [1.0, 4.0] (7/300; BCa) | `results/redteam.md` |

## Intended use

Research and demonstration of this closed pilot study only: reading the recorded answers, reproducing the tables, and the live side-by-side demo. Not for answering questions about any real bank, not for real customers, and not as evidence of general banking competence. Use it with the frozen system prompt and template above; other prompts were not evaluated.

## Limits

- **Canonical-answer eval:** SFT v1 teaches one fixed answer per intent, so the eval measures recall on T-seen, not generalisation from the handbook. (`docs/limitations.md`)
- **Lenient scorer:** 51/60 = 0.85 [0.74, 0.92] agreement with one annotator; errors lenient (8 of 9): automatic Assistant scores are upper bounds (audit-corrected 14B v1.2: about 121–126 /200 vs 142–148 auto, exploratory, one 60-item audit). (`docs/limitations.md`)
- **One annotator:** Independent human inter-annotator agreement: not measured; all hand labels by one annotator (intra-rater re-marking not done). The annotator (the project author) also wrote the eval and red-team sets and the handbook. (`docs/limitations.md`)
- **Fictional bank:** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank. (`data/DATA_SOURCES.md`)

Every limit with its measurement: `docs/limitations.md`.

## Licences

- Base model: Qwen3 models (0.6B–14B base and instruct; Qwen3-32B as the rewrite generator), Apache-2.0: Qwen Team (2025), *Qwen3 Technical Report*, arXiv:2505.09388.
- Project data (handbook, hand-written items, eval sets, SFT and preference data): CC BY 4.0 (`LICENSE-DATA`); code: Apache-2.0 (`LICENSE`).
- Banking77 customer queries (the user turns of the SFT data), CC BY 4.0 (`data/DATA_SOURCES.md`):

```
@inproceedings{Casanueva2020,
  author    = {Iñigo Casanueva and Tadas Temčinas and Daniela Gerz and Matthew Henderson and Ivan Vulić},
  title     = {Efficient Intent Detection with Dual Sentence Encoders},
  booktitle = {Proceedings of the 2nd Workshop on NLP for ConvAI - ACL 2020},
  year      = {2020},
  url       = {https://arxiv.org/abs/2003.04807}
}
```

