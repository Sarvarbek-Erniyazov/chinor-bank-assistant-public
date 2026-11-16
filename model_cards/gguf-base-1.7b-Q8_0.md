---
license: apache-2.0
base_model: Qwen/Qwen3-1.7B-Base
library_name: gguf
tags: [gguf, llama.cpp, customer-support, fictional-bank]
---

# Chinor demo model (a) Qwen3-1.7B-Base, no fine-tuning, GGUF Q8_0

> **Fiction notice.** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank.

**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet. The file is not in git (kept outside the repository); its SHA-256 is below.

**GGUF Q8_0 on CPU, not the evaluation protocol.** The live demo (`space/`) serves this file (ADR-036).

## Identity

| Field | Value |
|---|---|
| File | `base-1.7b-Q8_0.gguf`, 1,834,422,624 bytes, SHA-256 `719afec0026f74229022da4cbc0bae665b3f2194c6d480190f2024ac8c31127b` (`results/gguf_demo_models.md`) |
| Base model | `Qwen/Qwen3-1.7B-Base`, revision `ea980cb0a6c2ae4b936e82123acc929f1cec04c1` (`docs/base_revisions.md`) |
| Training data | none: the base weights, no fine-tuning |
| Conversion | GGUF Q8_0, CPU, not Protocol A; llama-cpp-python 0.3.36; template `train/chat_template.jinja` embedded; details in `results/gguf_demo_models.md` and `docs/compute.md` |

## Scores

Eval-v1 on a laptop CPU with llama-cpp-python (`eval/run_gguf.py`), greedy, the Protocol-A prompt ids; scored with rubric v1.3. The recorded column is the bf16 Protocol-A run `base-1.7B-0shot-A`: runtime, precision and machine all differ. Red-team: not run on this file.

| Measure | GGUF (recorded bf16) | Source |
|---|---|---|
| Assistant /200 | 36 (36) | `results/gguf_demo_models.md` |
| Turn-cut Assistant /200, diagnostic, not the official score | 36 (36) | `results/gguf_demo_models.md` |
| Retention /20 | 2 (2) | `results/gguf_demo_models.md` |
| Stop reasons (im_end / endoftext / length) | 0 / 187 / 33 (0 / 198 / 22) | `results/gguf_demo_models.md` |
| Same pass/fail as the recorded run | 218 | `results/gguf_demo_models.md` |
| Δ Assistant vs the recorded run [95 % CI] | +0.0 [-3.0, 3.0] | `results/method_table.md` |

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

