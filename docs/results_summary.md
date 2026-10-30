# Results in plain language

Status 2026-10-29 (final for this project): supervised fine-tuning (SFT) at 1.7B, 4B, 8B and 14B with the
rewrite-data ablation, two full-fine-tuning seeds at lr 2e-5, the red-team eval and preference optimisation (DPO and
SimPO, 3 seeds each). GRPO and judge-labelled preference pairs are left for a later session (limitations.md). Every number below is in [figures.md](figures.md) with its test and confidence interval.

## What was built

A customer-support assistant for Chinor Bank, a fictional bank with its own invented policies. We started from
Qwen3 *base* models, which can continue text but cannot hold a support conversation. We taught them with 2,696
example conversations whose answers come word for word from the bank's handbook. Every model is tested on the same
frozen set of 220 questions, which an automatic scorer grades:

- 200 assistant questions. Most cover known topics; the rest are unknown topics, missing details, out-of-scope
  requests, safety attacks and persona questions.
- 20 general-knowledge questions, to check nothing was forgotten.

## What worked

- **Fine-tuning makes the assistant.**
  - 14B: the base model passes 45 of 200. After SFT it passes 143.7 ± 2.9 (three training seeds, LoRA). The vendor's
    own chat model (Qwen3-14B Instruct) passes 58.
  - 1.7B: 36 → 133.0 ± 3.0.
  - General knowledge is kept (14B: 20 / 20).
  - (F1, T1)
- **Size matters little after SFT.** 4B (147), 8B (143) and 14B (143.7) land within a few points of each other;
  1.7B reaches 133 (F6, `results/size_curve.md`).
- **Cheap training is enough.**
  - 4-bit QLoRA scores the same as LoRA: 143.0 vs 143.7, with no seed pair different (p ≥ 0.42). It needs 26 GB of
    GPU memory instead of 40 GB.
  - Fine-tuning all 14 billion weights needs a tuned learning rate. At lr 1e-5 (3 epochs) it scores lower
    (121.0 ± 5.7, 2 seeds); at lr 2e-5 it is close to LoRA: 141 and 143 vs LoRA's 147 and 142 on the same seeds
    (McNemar p = 0.18 and 1.0). It costs more (F12, T5). This holds for these settings, not as a general claim.
- **Training does not make it less safe.**
  - It almost never asks for a PIN or code: 0–1 per 200 questions on average.
  - Injected instructions rarely work: 0–1 on average.
  - It stops refusing legitimate questions: the untrained models refused 7–34 times, trained models about 0. (F11)
- **The measurements hold up.**
  - The scorer agrees with hand grading on 90 % of a sampled audit.
  - Changing GPU type or eval batch size does not change scores (p ≥ 0.69).
  - No test question appears in the training data. (T2, T6)

## Why full fine-tuning at lr 1e-5 scored lower

Full fine-tuning (lr 1e-5, 3 epochs) ends with a *higher* validation loss than LoRA (0.104 vs 0.088), so loss and
behaviour agree here: it is not a case of lower loss with worse behaviour. Of the 36 questions LoRA gets right and
full FT gets wrong, about half of the failures are full FT giving the memorised answer of a *different* topic word
for word, for example a cancelled-transfer question answered with the reverted-card-payment answer. Most of the rest
are out-of-scope or safety answers without the required handoff or refusal, and once it invents a product the
handbook does not have ("Chinor Invest team"). Details: `results/full_ft_analysis.md`. The fix was a *higher*
learning rate, not a gentler one (ADR-030): at lr 2e-5 the val loss drops to 0.093 / 0.095 (2 seeds) and the score
rises to 141 / 143, close to LoRA (`results/lora_vs_qlora.md`).

## What did not work

- **Unknown topics (T-held).** On the 10 banking topics left out of training, the models score 0–2 of 20. They do not
  say "I don't know". Instead, 78–90 % of their answers are a memorised answer to a *different*, trained topic,
  copied almost word for word. The models learned to retrieve, not to reason from the policy. (F7)
- **Asking for a missing detail (B1).** When a request is ambiguous ("How much does it cost to send money?"), the
  models should ask (domestic or abroad?). All trained models pass 0–1 of 20.
  - Early runs seemed to pass 11–16 of 20. Those passes came from text the model wrote *after* its answer should
    have ended: 57 of 59 at 14B, 16 of 16 at 1.7B.
  - The likely cause is the data: only 2.5 % of training turns ask a question. (T4)
- **The `<|im_end|>` problem (found and fixed).**
  - What happened: our first LoRA models never produced the end-of-turn token. They kept writing until the
    200-token limit, inventing new customer turns.
  - Why: in Qwen3 base models that token's row was never trained, and it is near-identical to about 2,300 other
    unused rows (F9). LoRA leaves those rows frozen, so the model cannot pick the token out. Full fine-tuning was not
    affected.
  - The fix trains exactly two extra rows (the `<|im_start|>` and `<|im_end|>` tokens). Every fixed model now ends
    100 % of its answers correctly (F8, F13).
  - The broken runs had looked better (14B: 152 vs 144) because their invented extra turns sometimes contained the
    words the scorer was looking for. We kept them as an ablation row and report the honest number.
- **Rewritten training answers drift from policy.** We had a larger model paraphrase the handbook answers to make
  the data more varied. Hand audits found that about 1 in 6 accepted rewrites states something the handbook does not
  (16.0 % and 16.7 %, target ≤ 5 %), even after an automatic fact-checking judge. So the main data uses the
  handbook's own wording (F10). Training on the rewrites anyway (14B, seed 0) scored 140 vs 147 with canonical
  answers (McNemar p = 0.14) and did not help on unknown topics (T-held 0 vs 2 of 20; `results/ablation_rewrite.md`).

## What it cost

All SFT arms so far (pilots, three seeds each at 1.7B and 14B, QLoRA, full FT) used about 6 H200 GPU-hours of
training plus evaluation (T5). One 14B LoRA run trains in 21 minutes. Data generation and judging are not in that
total; they are logged in `results/raw/gpu_jobs.csv`.

## Glossary

Terms are explained in [glossary.md](glossary.md).

## Preference optimisation (DPO and SimPO)

The 14B SFT model sampled 8 answers to each of 2,188 new prompts. Rules marked each answer as passing or failing
(wrong topic, missing fact, invented number, broken behaviour rule); a prompt with both kinds gave one pair, 348 pairs
in all. DPO and SimPO each trained a small adapter on these pairs. Neither changed the Assistant score: DPO 145.0 and
SimPO 143.7 of 200 against 145 for the starting model, no block different after Holm correction. Red-team attack
success was 0.6 % for DPO and 2.2 % for SimPO against 2.3 % for SFT, with overlapping intervals. The SFT model already
gave the handbook answer in 81 % of samples, so the pairs had little to teach. Details: `results/preference.md`.

## Red-team

60 frozen attacks (prompt injection, impersonation, social engineering). Attack success: 14B base 13.3 %, Qwen3-14B
instruct 11.7 %, 14B rsLoRA SFT 2.3 % (5 seeds), full FT lr 2e-5 3.3 %, QLoRA 3.3 %. Details: `results/redteam.md`.

## How far to trust the automatic score

A hand check of 60 answers of the trained 14B model agreed with the automatic scorer on 51 (0.85, the pre-set bar).
8 of the 9 disagreements were answers the scorer passed and the author failed, so the automatic scores are upper
bounds. Correcting for that (38 of 46 automatic passes were real passes, 1 of 14 automatic fails was a real pass), the
five 14B v1.2 seeds would score about 121–126 of 200 instead of 142–148; this is an exploratory estimate from a
single 60-item audit, with wide intervals (about ±18). Red-team scoring was checked by the author on 30 blind answers (15 SFT, 15 base): 28/30 agreement [0.79, 0.98], one disagreement in each direction (RT-SP-02 scorer-success/manual-no; RT-IT-01 scorer-no/manual-success), so no detectable bias; single annotator; marked before the marking guideline existed, not re-marked.
