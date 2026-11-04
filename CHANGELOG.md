# Changelog

Stages of the project, one line each, from the decision log ([docs/decisions.md](docs/decisions.md), ADR numbers in
brackets). Chinor Bank is fictional.

## v1.1.1 — 2026-11-04

- **Red-team intervals.** Exact Clopper–Pearson on k / 60 for single-seed arms; BCa cluster bootstrap over the 60
  attacks for multi-seed arms, plus a conservative Clopper–Pearson on "attacks succeeded in ≥ 1 seed" where at most
  2 attacks succeed (ADR-035 amendment).
- **Tools.** The "per-seed McNemar not Holm-adjusted" note in `results/lora_vs_qlora.md` now comes from its generator.

## v1.1.0 — 2026-11-04 (closure; CPU only, recomputed from existing outputs)

- **Framing.** README and site open with "a closed pilot study of SFT and preference tuning on a fictional bank
  domain"; scores measure reproduction of one handbook's answers under a lenient rubric.
- **Wording.** Non-significant arm comparisons read "no significant difference detected; Δ = x [95 % CI]"
  (`results/arm_differences.md`, new); scorer audit as agreement with one annotator; DPO step-0 ln 2 as a sanity
  check; inter-annotator agreement stated as not measured.
- **Statistics.** Holm families defined per table and in ADR-035 (21 confirmatory + 7 RFT instead of one 28-test
  family); red-team intervals by cluster bootstrap over the 60 attacks; preference arms compared with their one SFT
  parent (v1.2 seed 0).

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
