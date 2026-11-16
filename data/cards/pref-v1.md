# Data card: pref-v1

> **Fiction notice.** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank.

**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet.

Preference data v1: rule-labelled pairs of on-policy samples of sft-merged (14B SFT v1.2 seed 0).

| Field | Value |
|---|---|
| Folder | `data/pref/v1/` |
| Built by | `data/pref/label_rules.py` |
| Detailed card | `data/pref/v1/DATA_CARD.md` (written by the builder, unchanged) |
| Runs trained on it | `pref_dpo_rules-s0`, `pref_dpo_rules-s1`, `pref_dpo_rules-s2`, `pref_simpo_rules-s0`, `pref_simpo_rules-s1`, `pref_simpo_rules-s2` |

| File | Records | SHA-256 |
|---|---|---|
| `prompts.jsonl` | 2188 | `e8dcd5f6def3a92e4ef0885202189fec8a1d82319591453c1a1908ec96ee2ef0` |
| `pairs_rules.jsonl` | 348 | `9634cdb61a3111b89ecf736dc8d0d84226cab2636639ddf371760ab26d4d39b8` |
| `pairs_v2.jsonl` | 299 | `e3604a22a4b008a9a6ae3e3b9f84d6976dc0a78d2180ccd64461b2f4c15081e0` |

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

