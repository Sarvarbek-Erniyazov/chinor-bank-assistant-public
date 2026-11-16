# Data card: sft-v1

> **Fiction notice.** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank.

**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet.

SFT data v1: Banking77 customer queries with canonical answers from the fictional handbook, plus hand-written behaviour examples (ADR-024).

| Field | Value |
|---|---|
| Folder | `data/sft/v1/` |
| Built by | `data/build_sft.py` |
| Detailed card | `data/sft/v1/DATA_CARD.md` (written by the builder, hashed in `manifest.sha256`, unchanged) |
| Runs trained on it | `gate-tok-1.7b`, `l14b_full-s0`, `l14b_full-s1`, `l14b_full_lr2e5-s0`, `l14b_full_lr2e5-s1`, `l14b_qlora_rslora_tok-s0`, `l14b_qlora_rslora_tok-s1`, `l14b_qlora_rslora_tok-s2`, `l14b_sft_rslora-s0`, `l14b_sft_rslora-s1`, `l14b_sft_rslora-s2`, `l14b_sft_rslora_tok-s0`, `l14b_sft_rslora_tok-s1`, `l14b_sft_rslora_tok-s2`, `size_4b_rslora_tok-s0`, `size_4b_rslora_tok-s1`, `size_4b_rslora_tok-s2`, `size_8b_rslora_tok-s0`, `size_8b_rslora_tok-s1`, `size_8b_rslora_tok-s2`, `tier_s_main_rslora-s0`, `tier_s_main_rslora-s1`, `tier_s_main_rslora-s2`, `tier_s_main_rslora_tok-s0`, `tier_s_main_rslora_tok-s1`, `tier_s_main_rslora_tok-s2`, `tier_s_pilot_dora-s0`, `tier_s_pilot_dora-s1`, `tier_s_pilot_dora-s2`, `tier_s_pilot_lora-s0`, `tier_s_pilot_lora-s1`, `tier_s_pilot_lora-s2`, `tier_s_pilot_lora_nogroup-s0`, `tier_s_pilot_lora_paged8-s0`, `tier_s_pilot_lora_paged8-s1`, `tier_s_pilot_lora_paged8-s2`, `tier_s_pilot_rslora-s0`, `tier_s_pilot_rslora-s1`, `tier_s_pilot_rslora-s2` |

| File | Records | SHA-256 |
|---|---|---|
| `DATA_CARD.md` | — | `641819c3dcafa973e7f4cc92667fb193704b7e44f9b9a8879fa143fe954e15d3` |
| `assemble_stats.json` | — | `12fc79b203e38fea034b45581782b395fcee894eb298a7472a78396342749cf0` |
| `behaviour_examples.jsonl` | 160 | `37ac3897ec3eb1c78e2626a4ee8ec0168f6cda6cde7d4e7a1be39d6e563c8205` |
| `task_examples.jsonl` | 2680 | `5d2857f12aa1172dc11fbd1d08207dbea6fbf1f4546c6a34f4134b2558e90672` |
| `task_prompts.jsonl` | 2680 | `423e99b7b06a3242aca10d17b9f1160fa44a7b0a1c044fa3709a58d78234b1e5` |
| `task_stats.json` | — | `762bc268830cf914ca5fb8e85476e537f04cd9e70638df96b0e091724f678c81` |
| `train.jsonl` | 2696 | `0e72aebe94967b1b4a465f467cacd532326e3bfbab2f1484613f4e580844cf44` |
| `val.jsonl` | 144 | `2df6e448857313ccf196d706a7a1d02673130de052d6358d3b2bf9b8bfca486d` |

SHA-256 from `manifest.sha256` where the folder has one, else computed from the file.

## Intended use

Research and demonstration of this closed pilot study only: reading the recorded answers, reproducing the tables, and the live side-by-side demo. Not for answering questions about any real bank, not for real customers, and not as evidence of general banking competence. Training data for the study's adapters; do not use it to train or test anything about a real bank. The eval sets are separate and carry a canary (`eval/FROZEN.md`): do not train on them.

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

