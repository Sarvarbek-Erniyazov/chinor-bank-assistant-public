# Demo models: Qwen3-1.7B as GGUF on CPU

`results/gguf_report.py`. **GGUF, CPU, not Protocol A.** 1.7B models converted to GGUF with llama.cpp, quantised and run with llama-cpp-python on a laptop CPU (`eval/run_gguf.py`): greedy, at most 200 new tokens, stop on `<|im_end|>` (151645) or `<|endoftext|>` (151643), batch 1, the same eval-v1 prompt ids as Protocol A (`eval/gguf_prompts.py`). Scored with `eval/score.py` (rubric v1.3). The recorded columns are the bf16 Protocol-A runs on the H200 (`eval/outputs/`); runtime, precision and hardware all differ, so the two columns are not a controlled comparison. Assistant /200 = passes on the 200 non-R items; retention /20 = the R items. Stop reasons: im_end / endoftext / length over 220. Same pass/fail = items (of 220) on which the GGUF answer and the recorded answer get the same verdict. (b) and (c1) differ only in the two trained special-token rows (same data v1, seed 0, configuration); (c) is the data-v1.2 model.

## Served files (Q8_0, ADR-036)

| Model | Label | Recorded arm | File | Bytes | SHA-256 | Assistant /200 Q8_0 (recorded bf16) | Turn-cut Assistant /200 Q8_0 (recorded bf16), diagnostic, not the official score | Retention /20 Q8_0 (recorded bf16) | Stop reasons Q8_0 | Stop reasons recorded | Same pass/fail /220 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) Qwen3-1.7B-Base, no fine-tuning | GGUF Q8_0, CPU, not Protocol A | `base-1.7B-0shot-A` | `base-1.7b-Q8_0.gguf` | 1,834,422,624 | `719afec0026f74229022da4cbc0bae665b3f2194c6d480190f2024ac8c31127b` | 36 (36) | 36 (36) | 2 (2) | 0 / 187 / 33 | 0 / 198 / 22 | 218 |
| (b) SFT rsLoRA without token rows, data v1, seed 0, merged | GGUF Q8_0, CPU, not Protocol A | `tier_s_main_rslora-s0` | `sft-1.7b-notok-s0-Q8_0.gguf` | 1,834,422,688 | `d882b096b31d0a35c45eea1acd2a2ba0a51747c195787f6f275275a74caf726d` | 149 (147) | 134 (132) | 18 (19) | 0 / 0 / 220 | 0 / 0 / 220 | 207 |
| (c1) SFT rsLoRA with token rows, data v1, seed 0, merged | GGUF Q8_0, CPU, not Protocol A | `tier_s_main_rslora_tok-s0` | `sft-1.7b-tok-s0-Q8_0.gguf` | 1,834,422,656 | `a5de99ef556fc872442618c6bd252d241fdf0738f3dc632a805d6235b5f1567a` | 135 (133) | 135 (133) | 20 (18) | 220 / 0 / 0 | 220 / 0 / 0 | 214 |
| (c) SFT rsLoRA with token rows, data v1.2, seed 0, merged | GGUF Q8_0, CPU, not Protocol A | `tier_s_main_rslora_tok-s0-v1.2` | `sft-1.7b-tok-v1.2-s0-Q8_0.gguf` | 1,834,422,688 | `70537c37c6c0493d95dfb3781455200dfb58a34da3195b274a39443839c43291` | 138 (136) | 138 (136) | 19 (19) | 220 / 0 / 0 | 220 / 0 / 0 | 218 |

The turn-cut column cuts each answer where the model's turn was meant to end (`eval/turn_cut.py`, as in `results/lora_no_token_rows.md`) and is never the official score. A model without trained special-token rows never emits `<|im_end|>`: it ends its turn with a neighbouring under-trained token, then invents `user` / `assistant` turns until the 200-token limit, and official scores (rubric v1.3) score the whole 200 tokens. Text in the invented turns can pass rubric checks, so such a model's official score overstates it (by up to 13 points in the recorded LoRA runs, `docs/limitations.md`), and it can score higher on the official metric than a model that stops at the end of its turn.

## Other levels

| Model | Quantisation | Label | File size (bytes) | Assistant /200 (recorded bf16) | Turn-cut Assistant /200 (recorded bf16), diagnostic, not the official score | Retention /20 (recorded bf16) | Stop reasons | Same pass/fail /220 vs recorded bf16 |
|---|---|---|---|---|---|---|---|---|
| (a) | Q4_K_M | GGUF Q4_K_M, CPU, not Protocol A | 1,107,405,152 | 33 (36) | 33 (36) | 0 (2) | 0 / 181 / 39 | 201 |
| (b) | Q4_K_M | GGUF Q4_K_M, CPU, not Protocol A | 1,107,405,216 | 148 (147) | 132 (132) | 18 (19) | 0 / 0 / 220 | 188 |
| (b) | Q5_K_M | GGUF Q5_K_M, CPU, not Protocol A | 1,257,875,872 | 143 (147) | 131 (132) | 18 (19) | 0 / 0 / 220 | 195 |
| (b) | Q6_K | GGUF Q6_K, CPU, not Protocol A | 1,417,750,944 | 153 (147) | 131 (132) | 19 (19) | 0 / 0 / 220 | 200 |
| (c1) | Q4_K_M | GGUF Q4_K_M, CPU, not Protocol A | 1,107,405,184 | 126 (133) | 126 (133) | 18 (18) | 220 / 0 / 0 | 205 |
| (c1) | Q5_K_M | GGUF Q5_K_M, CPU, not Protocol A | 1,257,875,840 | 132 (133) | 132 (133) | 19 (18) | 220 / 0 / 0 | 208 |
| (c1) | Q6_K | GGUF Q6_K, CPU, not Protocol A | 1,417,750,912 | 132 (133) | 132 (133) | 19 (18) | 220 / 0 / 0 | 214 |
| (c) | Q4_K_M | GGUF Q4_K_M, CPU, not Protocol A | 1,107,405,216 | 128 (136) | 128 (136) | 19 (19) | 220 / 0 / 0 | 206 |
| (c) | Q5_K_M | GGUF Q5_K_M, CPU, not Protocol A | 1,257,875,872 | 135 (136) | 135 (136) | 19 (19) | 220 / 0 / 0 | 205 |
| (c) | Q6_K | GGUF Q6_K, CPU, not Protocol A | 1,417,750,944 | 135 (136) | 135 (136) | 19 (19) | 220 / 0 / 0 | 213 |

Q4_K_M counts as clearly worse when its Assistant /200 is at least 6 below the best of Q5_K_M / Q6_K / Q8_0 of the same model (6 = twice the seed standard deviation 3.0 of the recorded 1.7B SFT rsLoRA arm with token rows, 133.0 ± 3.0, `docs/limitations.md`). Criterion: met for (c1), (c); levels run for the other models: (a) Q4_K_M / Q8_0; (b) Q4_K_M / Q5_K_M / Q6_K / Q8_0 (the base at Q8_0 only, ADR-036).

## Serving rule (ADR-036)

Rule, set before these tables were read: serve the smallest level whose Assistant /200 is within 3 points of the recorded bf16 Assistant /200 for every live fine-tuned model ((b), (c1), (c)). |GGUF − recorded| per level:

| Level | (b) | (c1) | (c) | Meets the rule |
|---|---|---|---|---|
| Q4_K_M | 1 | 7 | 8 | no |
| Q5_K_M | 4 | 1 | 1 | no |
| Q6_K | 6 | 1 | 1 | no |
| Q8_0 | 2 | 2 | 2 | yes |

Smallest level that meets the rule: Q8_0 (served). The base (a) is not part of the rule; at Q8_0 it scores 36 against its recorded 36 (difference 0, within 3 points), which does not change the decision.

## Speed with 2 threads

**2 threads on i7-13700; an estimate for a 2-vCPU machine, not a measurement of a hosted service.** `eval/gguf_speed.py`: the first 40 eval-v1 prompts, one after another with one model object (the KV cache of the shared system-prompt prefix is reused, as in a single-process demo; prompt 1 starts cold). TTFT = time to first token. Decode tokens/s excludes the first token of each answer; end-to-end tokens/s includes prompt processing. Same ids = answers whose generated token ids equal the 16-thread eval run.

| Model | Quantisation | File size (bytes) | Load (s) | TTFT cold (s) | TTFT median / p90 / max, warm (s) | Decode tokens/s | End-to-end tokens/s | Peak RAM (GB) | Same ids as 16 threads |
|---|---|---|---|---|---|---|---|---|---|
| (a) | Q4_K_M | 1,107,405,152 | 0.94 | 4.777 | 0.218 / 0.329 / 0.377 | 24.64 | 21.33 | 2.5 | 40/40 |
| (a) | Q8_0 | 1,834,422,624 | 0.41 | 8.24 | 0.304 / 0.517 / 0.569 | 17.32 | 14.78 | 2.55 | 40/40 |
| (b) | Q4_K_M | 1,107,405,216 | 0.97 | 4.764 | 0.214 / 0.338 / 0.376 | 24.43 | 23.56 | 2.5 | 40/40 |
| (b) | Q5_K_M | 1,257,875,872 | 0.37 | 5.903 | 0.264 / 0.43 / 0.443 | 22.32 | 21.32 | 1.97 | 40/40 |
| (b) | Q6_K | 1,417,750,944 | 0.34 | 5.967 | 0.296 / 0.461 / 0.473 | 21.74 | 20.72 | 2.13 | 40/40 |
| (b) | Q8_0 | 1,834,422,688 | 0.37 | 8.058 | 0.297 / 0.496 / 0.567 | 17.94 | 17.24 | 2.55 | 40/40 |
| (c1) | Q4_K_M | 1,107,405,184 | 0.93 | 4.708 | 0.214 / 0.336 / 0.386 | 24.8 | 22.27 | 2.5 | 40/40 |
| (c1) | Q5_K_M | 1,257,875,840 | 0.57 | 5.86 | 0.265 / 0.422 / 0.443 | 22.31 | 19.53 | 1.97 | 40/40 |
| (c1) | Q6_K | 1,417,750,912 | 0.55 | 5.863 | 0.295 / 0.454 / 0.484 | 21.6 | 18.79 | 2.13 | 40/40 |
| (c1) | Q8_0 | 1,834,422,656 | 0.61 | 7.951 | 0.296 / 0.496 / 0.533 | 17.7 | 15.77 | 2.55 | 40/40 |
| (c) | Q4_K_M | 1,107,405,216 | 0.96 | 4.656 | 0.216 / 0.326 / 0.368 | 24.56 | 22.13 | 2.5 | 40/40 |
| (c) | Q5_K_M | 1,257,875,872 | 0.53 | 5.806 | 0.253 / 0.42 / 0.437 | 22.43 | 19.71 | 1.97 | 40/40 |
| (c) | Q6_K | 1,417,750,944 | 0.56 | 5.859 | 0.29 / 0.467 / 0.478 | 21.8 | 18.95 | 2.13 | 40/40 |
| (c) | Q8_0 | 1,834,422,688 | 0.62 | 7.849 | 0.291 / 0.491 / 0.531 | 17.92 | 15.98 | 2.55 | 40/40 |

## Runs (16 threads)

| Run | GGUF (demo file) | Merge | Load (s) | Tokens/s | Peak RAM (GB) | CPU, threads | Checks |
|---|---|---|---|---|---|---|---|
| `base-1.7b` | `base-1.7b-Q4_K_M.gguf` (1,107,405,152 B) | none (base weights) | 0.91 | 33.87 | 2.54 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `base-1.7b-Q8_0` | `base-1.7b-Q8_0.gguf` (1,834,422,624 B) | none (base weights) | 0.38 | 24.39 | 2.59 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-notok-s0` | `sft-1.7b-notok-s0-Q4_K_M.gguf` (1,107,405,216 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00254 (limit 0.01); same top-5: True; token rows: not trained (rows equal the base); adapter `74906c07f289034c…`, merged manifest `9e5317012142d023…` | 0.78 | 34.88 | 2.54 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-notok-s0-Q5_K_M` | `sft-1.7b-notok-s0-Q5_K_M.gguf` (1,257,875,872 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00254 (limit 0.01); same top-5: True; token rows: not trained (rows equal the base); adapter `74906c07f289034c…`, merged manifest `9e5317012142d023…` | 0.35 | 32.37 | 2.02 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-notok-s0-Q6_K` | `sft-1.7b-notok-s0-Q6_K.gguf` (1,417,750,944 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00254 (limit 0.01); same top-5: True; token rows: not trained (rows equal the base); adapter `74906c07f289034c…`, merged manifest `9e5317012142d023…` | 0.37 | 29.06 | 2.18 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-notok-s0-Q8_0` | `sft-1.7b-notok-s0-Q8_0.gguf` (1,834,422,688 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00254 (limit 0.01); same top-5: True; token rows: not trained (rows equal the base); adapter `74906c07f289034c…`, merged manifest `9e5317012142d023…` | 0.39 | 27.07 | 2.59 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-s0` | `sft-1.7b-tok-s0-Q4_K_M.gguf` (1,107,405,184 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00728 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `fde014943c242419…`, merged manifest `9cb8cb41ed2a950c…` | 0.96 | 33.84 | 2.54 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-s0-Q5_K_M` | `sft-1.7b-tok-s0-Q5_K_M.gguf` (1,257,875,840 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00728 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `fde014943c242419…`, merged manifest `9cb8cb41ed2a950c…` | 0.36 | 31.17 | 2.02 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-s0-Q6_K` | `sft-1.7b-tok-s0-Q6_K.gguf` (1,417,750,912 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00728 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `fde014943c242419…`, merged manifest `9cb8cb41ed2a950c…` | 0.36 | 29.17 | 2.18 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-s0-Q8_0` | `sft-1.7b-tok-s0-Q8_0.gguf` (1,834,422,656 B) | fp32 merge, saved bf16; max next-token probability difference merged vs adapter 0.00728 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `fde014943c242419…`, merged manifest `9cb8cb41ed2a950c…` | 0.38 | 25.3 | 2.59 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-v1.2-s0` | `sft-1.7b-tok-v1.2-s0-Q4_K_M.gguf` (1,107,405,216 B) | bf16 merge, saved bf16; max next-token probability difference merged vs adapter 0.00309 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `64911a9a1c0963a4…`, merged manifest `26f10db983448c78…` | 0.75 | 34.38 | 2.54 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-v1.2-s0-Q5_K_M` | `sft-1.7b-tok-v1.2-s0-Q5_K_M.gguf` (1,257,875,872 B) | bf16 merge, saved bf16; max next-token probability difference merged vs adapter 0.00309 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `64911a9a1c0963a4…`, merged manifest `26f10db983448c78…` | 0.55 | 29.09 | 2.02 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-v1.2-s0-Q6_K` | `sft-1.7b-tok-v1.2-s0-Q6_K.gguf` (1,417,750,944 B) | bf16 merge, saved bf16; max next-token probability difference merged vs adapter 0.00309 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `64911a9a1c0963a4…`, merged manifest `26f10db983448c78…` | 0.54 | 28.31 | 2.18 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |
| `sft-1.7b-tok-v1.2-s0-Q8_0` | `sft-1.7b-tok-v1.2-s0-Q8_0.gguf` (1,834,422,688 B) | bf16 merge, saved bf16; max next-token probability difference merged vs adapter 0.00309 (limit 0.01); same top-5: True; token rows: trained (rows differ from the base); adapter `64911a9a1c0963a4…`, merged manifest `26f10db983448c78…` | 0.45 | 24.29 | 2.59 | 13th Gen Intel(R) Core(TM) i7-13700, 16 | build checks passed; special tokens round-trip True; llama.cpp tokenisation = HF ids on 220/220 prompts |

Models (b) and (c1): a first merge of their adapters in bf16 (the recorded procedure) failed `train/merge_sft.py`'s 0.01 next-token probability check and was not used; each was merged again with `--merge-dtype fp32` (float32 merge, saved in bf16) under the same, unchanged checks. Model (c) uses the recorded bf16 procedure. (b) also uses `--no-token-rows`, since its adapter has no trained special-token rows. For the merged models the converter already embeds `train/chat_template.jinja` (it is in the merged folder), so a quantised file is written directly when the f16 file carries it ((c1) and the Q5_K_M / Q6_K / Q8_0 files; (a), (b) and (c) at Q4_K_M went through the template step). The Q5_K_M / Q6_K / Q8_0 files are quantised from the f16 file of the model's Q4_K_M build (`scripts/gguf_build.py --reuse-f16`, f16 SHA-256 checked). Every demo file passes the same checks.

llama.cpp `0c1e57098bba43ac29e6e3b677cdceebdd22334f` (converter, `convert_hf_to_gguf.py`), llama-cpp-python 0.3.36 (quantisation and inference, the same llama.cpp commit vendored), project chat template `train/chat_template.jinja` embedded (SHA-256 `8a128a2973d31cc5…`); environment in `docs/compute.md`. The model files are not in the repository (kept outside git); their SHA-256:

| File | Bytes | SHA-256 |
|---|---|---|
| `base-1.7b-Q4_K_M-notemplate.gguf` | 1,107,408,576 | `21e9bdd23f63665519a921abf1cbb20c7ea3a458f81a0c6da0921893dbd1a3a7` |
| `base-1.7b-Q4_K_M.gguf` | 1,107,405,152 | `183d2f093d08de1155dcd104cca92990ceb614a8d2c1ba0547e9dcb65483f4ee` |
| `base-1.7b-Q8_0-notemplate.gguf` | 1,834,426,048 | `bab8fe902ad2da03c26353ef37b491c9a1b4ee791c3568d9cf93bdd239edeba0` |
| `base-1.7b-Q8_0.gguf` | 1,834,422,624 | `719afec0026f74229022da4cbc0bae665b3f2194c6d480190f2024ac8c31127b` |
| `base-1.7b-f16.gguf` | 3,447,348,928 | `13ad8b99ce913b209bb306c5ff2ced0eb52c1a7e2f24ee7254be1361b2f8c756` |
| `sft-1.7b-notok-s0-Q4_K_M-notemplate.gguf` | 1,107,405,216 | `7d91a62fd77dc24943e452de9fb7090ff47635d2cd4cd1208fb57d822e44dc32` |
| `sft-1.7b-notok-s0-Q4_K_M.gguf` | 1,107,405,216 | `960b09821e674790a1029c25e32d389971f4a858ecc762167c097b6a732afb2d` |
| `sft-1.7b-notok-s0-Q5_K_M.gguf` | 1,257,875,872 | `550b0b5136905e9c53124f2b0b067ca91a02cd254d352ca21a1992f4ee89142a` |
| `sft-1.7b-notok-s0-Q6_K.gguf` | 1,417,750,944 | `246d2de5196b9a587132fa988d38a2302e15e588ef84553b9a587c924cd16ded` |
| `sft-1.7b-notok-s0-Q8_0.gguf` | 1,834,422,688 | `d882b096b31d0a35c45eea1acd2a2ba0a51747c195787f6f275275a74caf726d` |
| `sft-1.7b-notok-s0-f16.gguf` | 3,447,345,568 | `6f70f037203b1fbeff2a300d52b8f1a4da6eefcab30505876f89e0273627dc6e` |
| `sft-1.7b-tok-s0-Q4_K_M.gguf` | 1,107,405,184 | `b52c4de299f8f5c2229b35b333f3fed80d808ab4f56c446e52d6545ebabfc387` |
| `sft-1.7b-tok-s0-Q5_K_M.gguf` | 1,257,875,840 | `14895e5b255ab7950195926148a11cf9a2bcec6dae75a19eac9e1dd33c4dd9f1` |
| `sft-1.7b-tok-s0-Q6_K.gguf` | 1,417,750,912 | `4745b565e38577398c1dd07eb558068eb01ad4f1a36ca76fa58608e4481f9ae4` |
| `sft-1.7b-tok-s0-Q8_0.gguf` | 1,834,422,656 | `a5de99ef556fc872442618c6bd252d241fdf0738f3dc632a805d6235b5f1567a` |
| `sft-1.7b-tok-s0-f16.gguf` | 3,447,345,536 | `b51d7c8f1dc386f075723c2b93be63e0f084e2b35a4f7e0eec6218e4ee4ddd0a` |
| `sft-1.7b-tok-v1.2-s0-Q4_K_M-notemplate.gguf` | 1,107,405,216 | `e47d2438f20d9f3aff027ba55a5028d373874e2b0f8c00a8e78ccffddae35898` |
| `sft-1.7b-tok-v1.2-s0-Q4_K_M.gguf` | 1,107,405,216 | `8f791283737ea88f10cfc92b0f8480cbf9f1b1b6307ad32f03073a45dcf2db0c` |
| `sft-1.7b-tok-v1.2-s0-Q5_K_M.gguf` | 1,257,875,872 | `78b1bc48650459146d6ed19f5004b69ddb80cd2249f44e283886344029c8b75a` |
| `sft-1.7b-tok-v1.2-s0-Q6_K.gguf` | 1,417,750,944 | `a927159714ce3363fa0b78bfcc29cc591777cb4cf3d820c2b5b4163bb90d714b` |
| `sft-1.7b-tok-v1.2-s0-Q8_0.gguf` | 1,834,422,688 | `70537c37c6c0493d95dfb3781455200dfb58a34da3195b274a39443839c43291` |
| `sft-1.7b-tok-v1.2-s0-f16.gguf` | 3,447,345,568 | `114b54269d08d65c922172987f3ceab87c3ca8468446af3c60464e386bc1cf58` |
