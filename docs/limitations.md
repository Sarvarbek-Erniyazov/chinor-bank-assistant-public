# Limitations

Known limits of the evaluation and the data, with the measurement behind each.

## Protocol A vs B (sensitivity check)

One arm, `base-1.7B-0shot`, decoded under both frozen protocols (plan v3 §2): Protocol A = H200 bf16, Protocol B = T4 fp16, both greedy, max_new_tokens 200, same template, system prompt and eval set; scored with rubric v1.3.

| Measure | Value |
|---|---|
| Answers identical after stop-token cut (220 items) | 102 / 220 = 46.4 % |
| Assistant /200, A vs B | 36 vs 35 (delta +1) |
| Retention /20, A vs B | 2 vs 2 |
| Discordant items (A pass / B fail, A fail / B pass) | 2 / 1 |
| Exact McNemar p (200 assistant items) | 1.000 |

Changing hardware and precision (H200 bf16 vs T4 fp16) changed the text of 118/220 greedy answers of base-1.7B but not its score (36 vs 35 /200; exact McNemar p = 1.00). This supports protocol robustness for the base model; the effect on trained models is tested separately (T4 vs H200 training check after Tier S).

## Eval batch size (Protocol A, base-14B 0-shot)

Protocol A pads left and generates in batches of 32. The same arm was re-run with batch size 1 (run
`robust-evalbatch-14B`, arm `base-14B-0shot-A-bs1`, H200 bf16, greedy, 200 tokens).

| | Batch 32 (`base-14B-0shot-A`) vs batch 1 |
|---|---|
| Answers identical (220 items) | 111 / 220 = 50.5 % |
| Assistant /200, batch 32 vs batch 1 | 45 vs 47 (delta −2) |
| Retention /20 | 20 vs 20 |
| Discordant items (batch 1 pass / batch 32 fail, batch 32 pass / batch 1 fail) | 4 / 2 |
| Exact McNemar p (200 assistant items) | 0.688 |

Batch size (padding and kernel choice in bf16) changes the text of about half of the greedy answers and moves the
score by 2 items, within noise. Arm comparisons therefore use the same batch size (32) throughout; differences of a
few items between arms are not read as effects without the paired test.

## LoRA arms never emit `<|im_end|>` (found 2026-10-29)

In Qwen3 Base checkpoints the output rows of `<|im_end|>` and `<|im_start|>` are not trained: they are identical to
each other and sit in a cluster of ~2,250 near-identical under-trained rows (cosine > 0.99 to the `<|im_end|>` row;
47–291 rows exactly identical, depending on size). LoRA and QLoRA never train `lm_head` / embeddings (ADR-023), so
the trained models end their turn with a neighbouring token instead (`魔龙令牌` at 14B, `𫟦` at 1.7B), then invent
`user` / `assistant` turns until the 200-token limit: stop reason `length` on 219–220 of 220 answers in every LoRA
arm. Official scores (rubric v1.3) score the whole 200 tokens. Cutting each answer at the first non-Latin character
or invented turn changes Assistant /200 by −0.7 (0.6B rsLoRA) to −5.7 (1.7B rsLoRA); the pilot decision
(ADR-025) holds after the cut (rsLoRA +13.3 over LoRA). Full fine-tuning trains `lm_head` and is not affected by
construction (14B full FT seed 0: 92.3 % stop on `<|im_end|>`).

**Decision and fix (ADR-023 amendment).** LoRA / QLoRA now also train exactly the two rows 151644 and 151645 (one
tied matrix at 0.6B–4B; `embed_tokens` and `lm_head` at 8B / 14B). Every rerun stops on `<|im_end|>` on 220/220
answers (acceptance ≥ 95 %; F8). Fixed scores: 1.7B 133.0 ± 3.0, 14B LoRA 143.7 ± 2.9, 14B QLoRA 143.0 ± 0.0
(Assistant /200, 3 seeds). They equal the cut diagnostic of the old runs, which overstated the official score by up
to 13 points through text in the invented turns. The old runs are kept as the ablation row "LoRA without trainable
special-token rows" (`results/lora_no_token_rows.md`); the eval-side cut stays a diagnostic column only. The 0.6B
pilot matrix is not rerun.

## Held-out intents (T-held)

Trained models pass 0–2 of the 20 T-held items. 78–90 % of their T-held answers are a near-verbatim canonical
answer of a different, trained intent (character similarity ≥ 0.80; `results/t_held_analysis.md`, F7). SFT v1
teaches one fixed answer per intent, so the eval measures recall on T-seen, not generalisation from the handbook.

## Asking for a missing detail (B1)

All fixed arms pass 0–1 of 20 B1 items. The 11–16 / 20 of the earlier LoRA runs came from invented later turns
(57 of 59 passes at 14B, 16 of 16 at 1.7B; `results/negative_results.md`). Only 2.5 % of SFT v1 assistant turns ask
a question (69 of 2,724), so the data gives the model little reason to ask. Full FT (0 / 20) agrees.


## Not done in this project (moved to a later session, 2026-10-29)

The closing plan of 2026-10-29 kept the preference stage to rule-labelled DPO and SimPO (3 seeds each). Not done:
GRPO; judge labelling of the preference pairs and the rules ∩ judge DPO arm (code exists: `data/pref/judge_pairs.py`,
`train/configs/pref_dpo_rules_judge.yaml`); SFT v2 by rejection sampling; extra seeds beyond 3; Colab/T4 Protocol-B
runs of the trained arms; Hugging Face uploads of the adapters (model cards say "upload pending"); a live demo
(`demo/index.html` is static, built from saved eval answers). The κ(rules, author) check on 60 blind pairs is computed
after training, so it validates the pair labels but did not gate the runs.

## Preference stage

348 rule pairs from 2,188 prompts (81 % of samples were the verbatim canonical answer; 1,667 prompts had no failing
sample), 67 % of them "wrong topic", so the preference signal is small and mostly about topic recall. The labels come
from rules only; their agreement with the author (κ on 60 blind pairs) is computed after training. All six runs passed
acceptance (100 % `<|im_end|>`, 0 hard violations). Comparisons are against SFT seed 0 alone, the one parent of every
run; seeds 1–2 vary only the preference stage.

## Checkpoint choice (ADR-034)

Every arm is evaluated at its last checkpoint: no early stopping and no selection by validation loss or eval score.
This avoids tuning on the eval set but means an arm that overfits late is reported as it ended.

## Exploratory arms

DPO v2 (ADR-032) was pre-registered after the six preference runs had ended; its trigger was not met, so it did not
run. RFT (ADR-033) is one seed and is reported as exploratory only.

## Scorer leniency (14B audit) and the red-team rates

The 14B audit (`eval/audit/scorer_accuracy_14b.md`) met the 0.85 accuracy threshold (51/60), but 8 of its 9 errors
were lenient: automatic Assistant scores are upper bounds (audit-corrected 14B v1.2: about 121–126 /200 vs 142–148
auto, exploratory, one 60-item audit). Red-team scoring was checked by the author on 30 blind answers (15 SFT, 15 base): 28/30 agreement [0.79, 0.98], one disagreement in each direction (RT-SP-02 scorer-success/manual-no; RT-IT-01 scorer-no/manual-success), so no detectable bias; single annotator; marked before the marking guideline existed, not re-marked.

RFT (seed 0) raised Assistant to 149/200 (not significant) but lost retention (R 7/20 vs 20/20; 12 answers without
`<|im_end|>`, all in R) and fails the 95 % stop criterion; it is not a recommended arm.
