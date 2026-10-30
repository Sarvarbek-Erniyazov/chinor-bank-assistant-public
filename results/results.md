# Results

**Assistant score** = passes over the 200 items of T-seen, T-held and B1–B4 (system prompt `handbook/system_prompt.txt`). **Retention** = passes over the 20 block-R items (no system prompt) and is reported separately; the two are never added. Rates are shown with Wilson 95 % CI. Flags are counts over the 200 assistant items. Decoding: greedy, max_new_tokens 200, stop on `<|im_end|>` / `<|endoftext|>`. Eval protocol A = H200 bf16, B = T4 fp16 (4-bit arms in 4-bit); rows from different protocols are not tested against each other. Eval set `eval-v1` (see `eval/FROZEN.md`); scoring rules `eval/rubric.md` v1.3.

| Arm | Train GPU/dtype | Eval protocol | Seeds (n) | Assistant /200 | T-seen | T-held | B1 ask | B2 scope | B3 safety | B4 persona | Retention /20 | Hard viol. | Over-refusal | Inj. success | VRAM (GB) | Latency (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base-0.6B-0shot | — | B | 1 | **20** · 10 % [7, 15] | 0 % [0, 4] | 0 % [0, 16] | 0 % [0, 16] | 5 % [1, 24] | 24 % [11, 43] | 87 % [62, 96] | **0** · 0 % [0, 16] | 4 | 24 | 6 | 1.9 | 1203 |
| base-0.6B-0shot-A | — | A | 1 | **20** · 10 % [7, 15] | 0 % [0, 4] | 0 % [0, 16] | 0 % [0, 16] | 10 % [3, 30] | 20 % [9, 39] | 87 % [62, 96] | **0** · 0 % [0, 16] | 3 | 23 | 6 | 3.9 | 196 |
| base-1.7B-0shot | — | B | 1 | **35** · 18 % [13, 23] | 0 % [0, 4] | 0 % [0, 16] | 5 % [1, 24] | 25 % [11, 47] | 60 % [41, 77] | 93 % [70, 99] | **2** · 10 % [3, 30] | 6 | 21 | 4 | 4.2 | 997 |
| base-1.7B-0shot-A | — | A | 1 | **36** · 18 % [13, 24] | 0 % [0, 4] | 0 % [0, 16] | 5 % [1, 24] | 20 % [8, 42] | 64 % [45, 80] | 100 % [80, 100] | **2** · 10 % [3, 30] | 5 | 22 | 4 | 6.1 | 178 |
| base-1.7B-3shot | — | B | 1 | **40** · 20 % [15, 26] | 1 % [0, 5] | 0 % [0, 16] | 10 % [3, 30] | 45 % [26, 66] | 56 % [37, 73] | 93 % [70, 99] | **2** · 10 % [3, 30] | 3 | 22 | 3 | 4.4 | 1445 |
| base-1.7B-3shot-A | — | A | 1 | **43** · 22 % [16, 28] | 1 % [0, 5] | 0 % [0, 16] | 25 % [11, 47] | 45 % [26, 66] | 60 % [41, 77] | 87 % [62, 96] | **2** · 10 % [3, 30] | 0 | 18 | 3 | 7.2 | 200 |
| base-14B-0shot-A | — | A | 1 | **45** · 22 % [17, 29] | 0 % [0, 4] | 0 % [0, 16] | 5 % [1, 24] | 50 % [30, 70] | 80 % [61, 91] | 93 % [70, 99] | **20** · 100 % [84, 100] | 0 | 10 | 2 | 34.4 | 225 |
| base-14B-3shot-A | — | A | 1 | **55** · 28 % [22, 34] | 2 % [1, 7] | 5 % [1, 24] | 40 % [22, 61] | 55 % [34, 74] | 76 % [57, 89] | 93 % [70, 99] | **20** · 100 % [84, 100] | 2 | 13 | 3 | 36.4 | 384 |
| base-4B-0shot-A | — | A | 1 | **35** · 18 % [13, 23] | 1 % [0, 5] | 0 % [0, 16] | 10 % [3, 30] | 25 % [11, 47] | 56 % [37, 73] | 87 % [62, 96] | **9** · 45 % [26, 66] | 8 | 28 | 7 | 11.7 | 240 |
| base-8B-0shot-A | — | A | 1 | **43** · 22 % [16, 28] | 0 % [0, 4] | 0 % [0, 16] | 20 % [8, 42] | 25 % [11, 47] | 80 % [61, 91] | 93 % [70, 99] | **20** · 100 % [84, 100] | 4 | 16 | 2 | 20.4 | 230 |

## Stop reasons

| Arm | im_end | endoftext | length | model | commit |
|---|---|---|---|---|---|
| base-0.6B-0shot | 0 (0 %) | 151 (69 %) | 69 (31 %) | Qwen/Qwen3-0.6B-Base | 2c8d0010 |
| base-0.6B-0shot-A | 0 (0 %) | 149 (68 %) | 71 (32 %) | Qwen/Qwen3-0.6B-Base | 72b4891b |
| base-1.7B-0shot | 0 (0 %) | 189 (86 %) | 31 (14 %) | Qwen/Qwen3-1.7B-Base | 2c8d0010 |
| base-1.7B-0shot-A | 0 (0 %) | 198 (90 %) | 22 (10 %) | Qwen/Qwen3-1.7B-Base | 72b4891b |
| base-1.7B-3shot | 0 (0 %) | 36 (16 %) | 184 (84 %) | Qwen/Qwen3-1.7B-Base | 2c8d0010 |
| base-1.7B-3shot-A | 0 (0 %) | 35 (16 %) | 185 (84 %) | Qwen/Qwen3-1.7B-Base | 72b4891b |
| base-14B-0shot-A | 0 (0 %) | 216 (98 %) | 4 (2 %) | Qwen/Qwen3-14B-Base | 72b4891b |
| base-14B-3shot-A | 0 (0 %) | 205 (93 %) | 15 (7 %) | Qwen/Qwen3-14B-Base | 72b4891b |
| base-4B-0shot-A | 0 (0 %) | 201 (91 %) | 19 (9 %) | Qwen/Qwen3-4B-Base | 72b4891b |
| base-8B-0shot-A | 0 (0 %) | 209 (95 %) | 11 (5 %) | Qwen/Qwen3-8B-Base | 72b4891b |

## Assistant score and retention

| Arm | assistant pass / 200 | Wilson 95 % | bootstrap 95 % | retention pass / 20 | Wilson 95 % | fabricated numbers (T) |
|---|---|---|---|---|---|---|
| base-0.6B-0shot | 20 / 200 | [7, 15] | [6, 14] | 0 / 20 | [0, 16] | 0 |
| base-0.6B-0shot-A | 20 / 200 | [7, 15] | [6, 14] | 0 / 20 | [0, 16] | 0 |
| base-1.7B-0shot | 35 / 200 | [13, 23] | [12, 23] | 2 / 20 | [3, 30] | 1 |
| base-1.7B-0shot-A | 36 / 200 | [13, 24] | [13, 24] | 2 / 20 | [3, 30] | 0 |
| base-1.7B-3shot | 40 / 200 | [15, 26] | [14, 26] | 2 / 20 | [3, 30] | 8 |
| base-1.7B-3shot-A | 43 / 200 | [16, 28] | [16, 27] | 2 / 20 | [3, 30] | 9 |
| base-14B-0shot-A | 45 / 200 | [17, 29] | [17, 28] | 20 / 20 | [84, 100] | 0 |
| base-14B-3shot-A | 55 / 200 | [22, 34] | [22, 34] | 20 / 20 | [84, 100] | 10 |
| base-4B-0shot-A | 35 / 200 | [13, 23] | [12, 23] | 9 / 20 | [26, 66] | 0 |
| base-8B-0shot-A | 43 / 200 | [16, 28] | [16, 28] | 20 / 20 | [84, 100] | 1 |
