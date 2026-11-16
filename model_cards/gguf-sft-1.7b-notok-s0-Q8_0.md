---
license: apache-2.0
base_model: Qwen/Qwen3-1.7B-Base
library_name: gguf
tags: [gguf, llama.cpp, customer-support, fictional-bank]
---

# Chinor demo model (b) SFT rsLoRA without token rows, data v1, seed 0, GGUF Q8_0

> **Fiction notice.** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank.

**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet. The file is not in git (kept outside the repository); its SHA-256 is below.

**GGUF Q8_0 on CPU, not the evaluation protocol.** The live demo (`space/`) serves this file (ADR-036).

## Identity

| Field | Value |
|---|---|
| File | `sft-1.7b-notok-s0-Q8_0.gguf`, 1,834,422,688 bytes, SHA-256 `d882b096b31d0a35c45eea1acd2a2ba0a51747c195787f6f275275a74caf726d` (`results/gguf_demo_models.md`) |
| Base model | `Qwen/Qwen3-1.7B-Base`, revision `ea980cb0a6c2ae4b936e82123acc929f1cec04c1` (`docs/base_revisions.md`) |
| Training data | `data/sft/v1` (train.jsonl SHA-256 `0e72aebe94967b1b4a465f467cacd532326e3bfbab2f1484613f4e580844cf44`, `data/sft/v1/manifest.sha256`) |
| Training run | `tier_s_main_rslora-s0`: `train/configs/tier_s_main_rslora.yaml`, seed 0: rsLoRA r 16, α 32; lr 0.0002, 3 epochs, max length 1024 |
| Adapter `adapter_model.safetensors` SHA-256 | `74906c07f289034cb008132b6ab314a7986cf1719f7a922cc0f0ca25f6c5ca3d` (`results/adapter_sha256.tsv`) |
| Merge | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00254 (limit 0.01); same top-5: True; token rows: not trained (rows equal the base); adapter `74906c07f289034c…`, merged manifest `9e5317012142d023…` (`results/gguf_demo_models.md`) |
| Conversion | GGUF Q8_0, CPU, not Protocol A; llama-cpp-python 0.3.36; template `train/chat_template.jinja` embedded; details in `results/gguf_demo_models.md` and `docs/compute.md` |

## Scores

Eval-v1 on a laptop CPU with llama-cpp-python (`eval/run_gguf.py`), greedy, the Protocol-A prompt ids; scored with rubric v1.3. The recorded column is the bf16 Protocol-A run `tier_s_main_rslora-s0`: runtime, precision and machine all differ. Red-team: not run on this file.

| Measure | GGUF (recorded bf16) | Source |
|---|---|---|
| Assistant /200 | 149 (147) | `results/gguf_demo_models.md` |
| Turn-cut Assistant /200, diagnostic, not the official score | 134 (132) | `results/gguf_demo_models.md` |
| Retention /20 | 18 (19) | `results/gguf_demo_models.md` |
| Stop reasons (im_end / endoftext / length) | 0 / 0 / 220 (0 / 0 / 220) | `results/gguf_demo_models.md` |
| Same pass/fail as the recorded run | 207 | `results/gguf_demo_models.md` |
| Δ Assistant vs the recorded run [95 % CI] | +2.0 [-5.0, 9.0] | `results/method_table.md` |

## Intended use

Research and demonstration of this closed pilot study only: reading the recorded answers, reproducing the tables, and the live side-by-side demo. Not for answering questions about any real bank, not for real customers, and not as evidence of general banking competence. Served in the live demo next to another model to show what training changed, including the end-of-turn behaviour.

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

