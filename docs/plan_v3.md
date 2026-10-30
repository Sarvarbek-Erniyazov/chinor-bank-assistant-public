# Plan v3 — two tiers on one pipeline

Plan v3 replaces the single-model plan (ADR-001) with two model tiers that
share one tokenizer, one chat template, one set of control tokens, one data
pipeline and the frozen eval set `eval-v1`. Decisions are recorded as
ADR-011 to ADR-016 in [decisions.md](decisions.md); compute and server
mechanics are in [compute.md](compute.md).

## 1. Tiers

| Tier | Model | Hardware | Role |
|---|---|---|---|
| **S** | `Qwen/Qwen3-1.7B-Base` (pilot `Qwen/Qwen3-0.6B-Base`) | free T4 (Colab / Kaggle), fp16 | Free-compute path: everything in the repository can be reproduced without paid hardware. |
| **L** | `Qwen/Qwen3-14B-Base` (fallback `Qwen/Qwen3-8B-Base`) | one H200 (141 GB), bf16 | Main result: every row of the main table. |

All Qwen3 base sizes (0.6B, 1.7B, 4B, 8B, 14B) use the same tokenizer and
ChatML control tokens (`<|im_start|>` 151644, `<|im_end|>` 151645,
`<|endoftext|>` 151643), so the project template `train/chat_template.jinja`,
the masking rule and the stop ids carry over unchanged. The tokenizer hash
is checked per size in [tokenizer_notes.md](tokenizer_notes.md).

The 8B fallback is used only if 14B full fine-tuning does not fit or a
14B stage does not finish within its budget; the switch is recorded as an
ADR and applies to every Tier-L row, never to a subset.

## 2. Evaluation protocols

The eval set, system prompt and chat template stay frozen as `eval-v1`
([eval/FROZEN.md](../eval/FROZEN.md)). Two frozen protocols define how an
arm is decoded:

- **Protocol A** = H200, bf16, transformers generate, greedy,
  max_new_tokens 200, eos [151645,151643] — every main-table row.
- **Protocol B** = T4 fp16 (QLoRA/4-bit arms in 4-bit) — the free-compute
  table.

One sensitivity check links them: `base-1.7B-0shot` is decoded under both
protocols and the answer exact-match rate, score delta and McNemar test are
reported in [limitations.md](limitations.md). Rows from different protocols
are never compared in one test; every results row carries an
"Eval protocol" column.

A second frozen set, the **red-team set** (`eval/redteam_set.jsonl`, tag
`redteam-v1`), is built after SFT v1 and before any preference data exists,
so that no preference pair or reward can be tuned to it (ADR-016).

## 3. Stages

Each stage answers one question. Rows are named `<stage>-<size>[-variant]`.

| # | Stage | Question it answers | Tier | Seeds |
|---|---|---|---|---|
| 0 | Baselines (0-shot, 3-shot) | How far do prior knowledge and the system prompt alone get, and how does that scale with size? | S (Protocol B, done), L + size curve (Protocol A) | 1 (greedy, deterministic) |
| 1 | SFT data v1 | — (data stage): fact-verified rewrites of the canonical answers by `Qwen/Qwen3-32B` (non-thinking), behaviour examples for B1–B4, contamination check | — | — |
| 2 | SFT v1 (LoRA) | How much does supervised fine-tuning on handbook data buy over the base model? | S and L | 3 |
| 3 | SFT v1 QLoRA | What does 4-bit quantisation of the frozen base cost in quality? | S (Protocol B, 4-bit eval), L | 3 |
| 4 | SFT v1 full fine-tuning, 14B | Does updating all weights (bf16, 8-bit Adam) beat LoRA at the main size? | L | 3 |
| 5 | Size curve, SFT-LoRA | How do the SFT gain and the T-seen / T-held gap scale over 0.6 / 1.7 / 4 / 8 / 14B? | A for all five sizes | 3 |
| 6 | Red-team set | Built and frozen here; answers: how robust are SFT v1 arms to attacks the eval set did not anticipate? | eval only | — |
| 7 | SFT v2 (rejection-sampled self-data) | Does training on the model's own verified answers beat SFT v1? Replaces the planned Bitext mixing (ADR-015). | L (and S) | 3 |
| 8 | DPO vs SimPO | Which offline preference objective gives the larger gain on B1–B4 at equal data? | L (and S) | 3 each |
| 9 | DPO(rules) vs DPO(rules ∩ judge) | Does filtering rule-built pairs with an LLM judge (`google/gemma-4-31B-it`) improve preference training? | L | 3 each |
| 10 | GRPO | Does online RL with the rule reward beat offline DPO from the same SFT start? | L | 2 |
| 11 | Data-scale curve (optional) | How does the SFT gain scale with 25 / 50 / 100 % of the SFT data? | L | 3 |

Seeds: 3 per main arm and per ablation; 2 for GRPO. A row reports the
mean over seeds with the per-seed range; significance tests (exact McNemar)
are run per seed pair on Protocol A outputs only.

## 4. Main-table rows

Every row carries **Train GPU/dtype**, **Eval protocol** and **Seeds (n)**.

| Row | Train GPU/dtype | Eval protocol | Seeds (n) |
|---|---|---|---|
| base-{0.6,1.7,4,8,14}B-0shot | — | A | 1 |
| base-{1.7,14}B-3shot | — | A | 1 |
| sft1-14B-lora | H200 / bf16 | A | 3 |
| sft1-14B-qlora | H200 / 4-bit nf4 + bf16 compute | A | 3 |
| sft1-14B-full | H200 / bf16, 8-bit Adam | A | 3 |
| sft1-{0.6,1.7,4,8}B-lora (size curve) | H200 / bf16 | A | 3 |
| sft2-14B-lora | H200 / bf16 | A | 3 |
| dpo-14B, simpo-14B | H200 / bf16 | A | 3 |
| dpo-judge-14B | H200 / bf16 | A | 3 |
| grpo-14B | H200 / bf16 | A | 2 |
| data-scale-14B-{25,50}% (optional) | H200 / bf16 | A | 3 |

Free-compute table (Protocol B): base-0.6B-0shot, base-1.7B-{0,3}shot (done),
sft1-1.7B-lora, sft1-1.7B-qlora, sft2-1.7B-lora, dpo-1.7B, simpo-1.7B.

## 5. Generator and judge

- Generator for rewrites and behaviour examples: `Qwen/Qwen3-32B`,
  non-thinking (`chat_template_kwargs={"enable_thinking": false}`), bf16,
  vLLM; fallback transformers bf16 batched.
- Judge: `google/gemma-4-31B-it`, bf16 — a different model family from
  both the generator and the policy, so the judge does not share their
  biases; fallback `meta-llama/Llama-3.3-70B-Instruct`, fp8 (gated, needs
  access approval).
- Every generated answer is fact-verified against `handbook/intents.yaml`
  and the handbook numbers before it is used; failures fall back to the
  canonical answer.

## 6. Rejected options

Gemma 4 31B as Tier L (no full-FT or T4 path, multimodal loading, breaks
the single-family size curve), Qwen3.5 dense (vision-language checkpoint,
linear-attention hybrid), all MoE models, sequence packing, NEFTune, Liger
kernels, KTO, PPO, RAG. Reasons in [model_choice.md](model_choice.md) and
ADR-011/012.

## 7. H200 hours (estimates)

Estimates for one H200 at bf16; replaced by measured wall-clock from
`runs/*/run.json` as stages finish.
The H200 is shared with the GTD project, which has priority until its queue
finishes; every GPU run waits for the shared GPU lock ([compute.md](compute.md) §5),
so these are GPU hours, not calendar time.

| Item | Runs | h / run | Total h |
|---|---|---|---|
| Weight downloads (0.6B–14B, 32B generator, 31B judge) | — | — | 1.0 |
| Protocol-A baselines (7 arms) | 7 | 0.1 | 0.7 |
| Rewrites, Qwen3-32B vLLM | 1 | 0.5 | 0.5 |
| SFT v1 LoRA 14B | 3 | 1.0 | 3.0 |
| SFT v1 QLoRA 14B | 3 | 1.5 | 4.5 |
| SFT v1 full FT 14B | 3 | 3.0 | 9.0 |
| Size curve LoRA 0.6–8B | 12 | 0.4 | 4.8 |
| Rejection sampling for SFT v2 | 1 | 1.0 | 1.0 |
| SFT v2 LoRA 14B | 3 | 1.0 | 3.0 |
| Judge pass over preference pairs | 1 | 1.0 | 1.0 |
| DPO, SimPO, DPO-judge 14B | 9 | 1.0 | 9.0 |
| GRPO 14B | 2 | 4.0 | 8.0 |
| Protocol-A evals of every trained row | ~40 | 0.1 | 4.0 |
| Data-scale curve (optional) | 6 | 0.7 | 4.2 |
| **Total** (without / with optional) | | | **≈ 50 / 54** |

## 8. Minimum version without the H200

If the H200 is unavailable, the project still completes on Tier S:

- Protocol B only; the free-compute table becomes the main table.
- SFT v1 LoRA and QLoRA on 1.7B (3 seeds each), DPO and SimPO on 1.7B.
- Rewrites are replaced by the canonical answers (the `verify.py` fallback
  path), so SFT data v1 is canonical-only; SFT v2 rejection sampling runs
  on a T4 with the 1.7B SFT model.
- Dropped: 14B rows, full fine-tuning, the size curve above 1.7B, the
  judge-filtered DPO arm, GRPO.
- The red-team set is still built and frozen after SFT v1.

## 9. Later session (moved here 2026-10-29)

1. Judge labelling of the rule pairs (gemma-4-31B-it, both orders) and the rules ∩ judge DPO arm, trained only if κ(judge, author) ≥ 0.6.
2. GRPO with the rule scorer as reward.
3. SFT v2 by rejection sampling from sft-merged.
4. More seeds for the preference arms.
5. Colab/T4 Protocol-B runs of the trained arms.
6. HF uploads of the released adapters; a live demo.
