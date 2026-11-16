# Data card: sft-v1.2_rft

> **Fiction notice.** Chinor Bank does not exist. Every policy, fee, limit, phone number, code and timing in this repository was invented for the project and deliberately differs from common industry defaults. Nothing here describes, imitates or is affiliated with any real bank.

**Upload pending.** Not on the Hugging Face Hub: no Hub repository exists yet.

RFT data: v1.2 plus verified on-policy samples of the SFT model (exploratory, ADR-033).

| Field | Value |
|---|---|
| Folder | `data/sft/v1.2_rft/` |
| Built by | `data/sft/build_rft.py` |
| Detailed card | `data/sft/v1.2_rft/DATA_CARD.md` (written by the builder, hashed in `manifest.sha256`, unchanged) |
| Runs trained on it | `l14b_sft_rslora_tok-s0-v1.2_rft` |

| File | Records | SHA-256 |
|---|---|---|
| `DATA_CARD.md` | — | `c11ddd6c5510b52daff1db91f9eb7da769b739c239118d8f5673e1ab9890be1d` |
| `train.jsonl` | 3299 | `028fd1c10ab526d9b002b4d65555e4d8ebdc443f198b0d8162b149cf07e00f4d` |
| `val.jsonl` | 147 | `22fdb4d2f54539a9507c6bf15619149dc53c6096336d27da2f6e531fff80364d` |

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

