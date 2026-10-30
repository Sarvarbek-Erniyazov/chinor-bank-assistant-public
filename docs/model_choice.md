# Model choice

Decision: **Qwen/Qwen3-1.7B-Base** for the full pipeline, **Qwen/Qwen3-0.6B-Base**
for pilots. Recorded as ADR-001 in [decisions.md](decisions.md).

## Constraints

- Training and evaluation run on a free Colab T4 (16 GB, fp16, no bf16) or
  Kaggle; the model must fit for LoRA in fp16 and for QLoRA in 4-bit.
- Plain text-only decoder, supported by stock `transformers`, `peft`, `trl`
  and `bitsandbytes` without custom kernels.
- A *base* (not instruction-tuned) checkpoint, so that the effect of SFT and
  preference optimisation is measurable from a clean starting point.
- Permissive licence.
- Tokenizer with ChatML control tokens already in the vocabulary, so the chat
  format needs no new embeddings.

## Comparison

Numbers are the ones reported by the model authors on the linked model cards
or technical reports; they are not directly comparable across families
(different shot counts and harnesses) and were used only as a sanity check on
capability per parameter.

| Model | Params | Pretrain tokens | Context | Licence | MMLU | GSM8K | Other | Verdict |
|---|---|---|---|---|---|---|---|---|
| [Qwen/Qwen3-1.7B-Base](https://huggingface.co/Qwen/Qwen3-1.7B-Base) | 1.7 B (1.4 B non-emb.) | 36 T, 119 languages | 32 k | Apache-2.0 | 62.6 | 75.4 | MATH 43.5, EvalPlus 52.7, BBH 54.5 ([Qwen3 report](https://arxiv.org/abs/2505.09388), Table 4) | **Chosen.** Best capability per parameter in the range; ChatML tokens in vocab; plain dense decoder; fp16-safe on T4. |
| [Qwen/Qwen3-0.6B-Base](https://huggingface.co/Qwen/Qwen3-0.6B-Base) | 0.6 B | 36 T | 32 k | Apache-2.0 | 52.8 | 59.6 | MATH 32.4, BBH 41.4 (same report) | **Pilot model.** Same tokenizer and template as 1.7B, trains in minutes. |
| [Qwen/Qwen3.5-2B-Base](https://huggingface.co/Qwen/Qwen3.5-2B-Base) | 2 B | n/a on card | 262 k | Apache-2.0 | not reported | not reported | hybrid Gated DeltaNet + gated attention, vision encoder, MTP head | **Rejected.** Vision-language checkpoint loaded through a multimodal class; hybrid linear-attention layers need recent kernels and had unverified fp16 behaviour on T4; no published base-model benchmark numbers at decision time. Too much tooling risk for the gain. |
| [HuggingFaceTB/SmolLM3-3B-Base](https://huggingface.co/HuggingFaceTB/SmolLM3-3B-Base) | 3 B | 11.2 T | 64 k | Apache-2.0 | 44.1 (MMLU-CF) | 67.6 | MATH 46.1, HumanEval+ 30.5 | Rejected: 3 B in fp16 leaves little T4 headroom for LoRA on a full-handbook system prompt; NoPE layers and a custom template add friction. |
| [Qwen/Qwen2.5-1.5B](https://huggingface.co/Qwen/Qwen2.5-1.5B) | 1.54 B | 18 T | 32 k | Apache-2.0 | 60.9 | 62.4 | MATH 35.0, MMLU-Pro 32.1 ([Qwen2.5 report](https://arxiv.org/abs/2412.15115)) | Rejected: previous generation; Qwen3-1.7B-Base is better on every reported benchmark with the same tooling. |
| [meta-llama/Llama-3.2-1B](https://huggingface.co/meta-llama/Llama-3.2-1B) | 1.23 B | up to 9 T | 128 k | Llama 3.2 Community (custom) | 32.2 | not reported for base (44.4 for Instruct) | ARC-C 32.8 | Rejected: much lower knowledge benchmarks; gated weights and a non-permissive licence; no ChatML tokens. |
| [google/gemma-3-1b-pt](https://huggingface.co/google/gemma-3-1b-pt) | 1.0 B | 2 T | 32 k | Gemma terms (custom) | not reported (Global-MMLU-Lite 24.9) | not reported | HellaSwag 62.3, BBH 28.4, ARC-C 38.4 | Rejected: weakest reported numbers; gated weights and custom terms; 1 B is likely too small to hold the handbook. |

## What the choice costs

- 1.7 B parameters in fp16 are about 3.4 GB of weights; LoRA training with a
  ~450-token system prompt and 2 k context fits a T4 with gradient
  checkpointing. The QLoRA arm exists to measure the quality cost of 4-bit.
- The shipped Qwen3 chat template inserts `<think>` blocks; the project uses
  its own minimal ChatML template (see [tokenizer_notes.md](tokenizer_notes.md)
  and ADR-003).

## Tier L (plan v3)

Plan v3 ([plan_v3.md](plan_v3.md), ADR-011/012) adds a large tier trained and
evaluated on one H200 (141 GB, bf16). The 1.7B choice above stays as Tier S.
Constraints for Tier L: same tokenizer, template and control tokens as Tier S
(so one pipeline serves both and the size curve is a single family); full
fine-tuning in bf16 with 8-bit Adam must fit one H200; a Tier-S-sized member of
the same family must exist for the T4 path; plain text-only dense decoder.

Benchmark numbers are from the [Qwen3 report](https://arxiv.org/abs/2505.09388)
(base models, Table 4) and are used only as a sanity check on the size curve.

| Model | Params | MMLU | GSM8K | Weights (bf16) | Verdict |
|---|---|---|---|---|---|
| [Qwen/Qwen3-14B-Base](https://huggingface.co/Qwen/Qwen3-14B-Base) | 14.8 B | 81.1 | 92.5 | 29.5 GB | **Chosen.** Largest dense Qwen3 base; full FT (weights + grads + 8-bit Adam ≈ 85 GB before activations) fits one H200; same tokenizer as 0.6B–8B, so the size curve is one family. |
| [Qwen/Qwen3-8B-Base](https://huggingface.co/Qwen/Qwen3-8B-Base) | 8.2 B | 76.9 | 89.8 | 16.4 GB | **Fallback.** Same family; used for every Tier-L row if 14B full FT does not fit or overruns its budget. Also a size-curve point. |
| [Qwen/Qwen3-4B-Base](https://huggingface.co/Qwen/Qwen3-4B-Base) | 4.0 B | 73.0 | 87.8 | 8.0 GB | Size-curve point only. |
| [google/gemma-4-31B](https://huggingface.co/google/gemma-4-31B) | 31 B | — | — | — | Rejected: no full-FT path on one H200 and no T4-sized demo in the same pipeline; loaded through a multimodal (image-text-to-text) class; a different tokenizer breaks the single-family size curve. Used instead as the judge (`google/gemma-4-31B-it`). |
| [Qwen/Qwen3.5-9B-Base](https://huggingface.co/Qwen/Qwen3.5-9B-Base) (Qwen3.5 dense) | 9 B | — | — | — | Rejected: vision-language checkpoint and a Gated DeltaNet linear-attention hybrid (same reasons as Qwen3.5-2B for Tier S). |
| [Qwen/Qwen3-30B-A3B-Base](https://huggingface.co/Qwen/Qwen3-30B-A3B-Base), [Qwen/Qwen3.5-35B-A3B-Base](https://huggingface.co/Qwen/Qwen3.5-35B-A3B-Base) (MoE families) | 30–35 B total, 3 B active | — | — | — | Rejected: MoE routing adds load-balancing losses and router instability to every SFT/DPO/GRPO comparison, LoRA on experts is non-standard, and there is no dense point on the size curve. |
| [mistralai/Mistral-Small-24B-Base-2501](https://huggingface.co/mistralai/Mistral-Small-24B-Base-2501) | 24 B | — | — | — | Rejected: different tokenizer and control tokens (no shared pipeline or size curve); 24 B full FT is tight on one H200; no small sibling for the T4 path. |
| [allenai/Olmo-3-1025-7B](https://huggingface.co/allenai/Olmo-3-1025-7B), [allenai/Olmo-3-1125-32B](https://huggingface.co/allenai/Olmo-3-1125-32B) (OLMo 3) | 7 / 32 B | — | — | — | Rejected: separate family and tokenizer, only 7 B and 32 B (32 B full FT does not fit, 7 B is below the 14B main size); no T4-sized sibling. |

"—" means not compared: those families were rejected on tooling or pipeline
grounds before benchmark numbers mattered.
