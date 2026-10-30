# Changelog

Stages of the project, one line each, from the decision log ([docs/decisions.md](docs/decisions.md), ADR numbers in
brackets). Chinor Bank is fictional.

## v1.0.1 — 2026-10-30

- **Site.** "Do not claim" bullets no longer cut at wrapped lines; per-block heatmap (F2) added and every figure
  captioned with its takeaway; demo links to the full saved-answer page, live command kept.
- **Claims.** GRPO marked dropped; RFT marked exploratory, 1 seed, not recommended.
- **Tools.** `scripts/verify_adapters.py` checks an adapter backup against `results/adapter_sha256.tsv`.

## v1.0 — 2026-10-30

- **2026-10-27 — Foundations.** Fictional bank with non-default numbers, handbook, minimal ChatML template, stop on
  151645 / 151643, 10 held-out intents, one frozen 220-item eval set, 450-token system prompt (ADR-001–009).
- **2026-10-28 — Scorer and plan.** Rubric v1.1–v1.3 after hand audits; plan v3 with two tiers (1.7B on T4, 14B on
  H200), two frozen eval protocols, Qwen3-32B generator and Gemma 4 judge, red-team set planned as a second frozen
  set, shared-GPU lock with GTD (ADR-010–019, 021).
- **2026-10-29 — SFT.** Trainer stack, entailment filter, trainable special-token rows to fix `<|im_end|>`, canonical
  answers instead of drifting rewrites, Tier-S config, learning rates per size, checkpoint retention (ADR-020,
  022–027).
- **2026-10-29 — Data versions and full FT.** SFT v1.1 (more asking turns), v1.2 (60 handoff examples), full FT at
  lr 2e-5, v1.2 chosen for the next stages by a pre-set rule (ADR-028–031).
- **2026-10-29 — Red-team freeze.** redteam-v1 (60 items) frozen and tagged; every base, reference and trained arm
  evaluated (ADR-016 amendment).
- **2026-10-29 — Preference stage.** sft-merged, K = 8 on-policy sampling, 348 rule-labelled pairs, DPO and SimPO
  (3 seeds each); DPO v2 not triggered; RFT exploratory; every arm evaluated at its last checkpoint (ADR-032–034).
- **2026-10-29/30 — Validation and release.** Hand checks of the 14B scorer (51/60), the red-team scorer (28/30) and
  the pair labels (κ 0.97); claims table, figures F0–F15, static demo, canary, licences.
