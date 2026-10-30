# Seeds — every training run

`eval/results_tables.py`. Official scores (rubric v1.3); flags on the 200 assistant items; diagnostic cut column never official.

| Run | Config | Seed | Assistant /200 | Retention /20 | HV | NUM | OR | INJ | <|im_end|> stops % | diag. cut Assistant | Final train loss | Final val loss | Peak VRAM (GB) | Tokens/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `tier_s_main_rslora_tok-s0` | `train/configs/tier_s_main_rslora_tok.yaml` | 0 | 133 | 18 | 0 | 0 | 0 | 0 | 100.0 | 133 | 0.0096 | 0.1107 | 22.24 | 13,969 |
| `tier_s_main_rslora_tok-s1` | `train/configs/tier_s_main_rslora_tok.yaml` | 1 | 136 | 19 | 0 | 0 | 0 | 0 | 100.0 | 136 | 0.0149 | 0.1162 | 22.24 | 13,992 |
| `tier_s_main_rslora_tok-s2` | `train/configs/tier_s_main_rslora_tok.yaml` | 2 | 130 | 19 | 0 | 0 | 0 | 0 | 100.0 | 130 | 0.0102 | 0.1064 | 22.24 | 14,016 |
| `l14b_sft_rslora_tok-s0` | `train/configs/l14b_sft_rslora_tok.yaml` | 0 | 147 | 20 | 0 | 2 | 0 | 0 | 100.0 | 147 | 0.0079 | 0.0913 | 40.31 | 3,424 |
| `l14b_sft_rslora_tok-s1` | `train/configs/l14b_sft_rslora_tok.yaml` | 1 | 142 | 20 | 0 | 0 | 0 | 1 | 100.0 | 142 | 0.0098 | 0.0903 | 40.31 | 3,420 |
| `l14b_sft_rslora_tok-s2` | `train/configs/l14b_sft_rslora_tok.yaml` | 2 | 142 | 20 | 1 | 0 | 0 | 2 | 100.0 | 142 | 0.0087 | 0.0832 | 40.31 | 3,422 |
| `l14b_qlora_rslora_tok-s0` | `train/configs/l14b_qlora_rslora_tok.yaml` | 0 | 143 | 20 | 0 | 0 | 1 | 0 | 100.0 | 143 | 0.0061 | 0.0957 | 26.47 | 2,791 |
| `l14b_qlora_rslora_tok-s1` | `train/configs/l14b_qlora_rslora_tok.yaml` | 1 | 143 | 20 | 0 | 1 | 0 | 0 | 100.0 | 143 | 0.0102 | 0.0895 | 26.47 | 2,790 |
| `l14b_qlora_rslora_tok-s2` | `train/configs/l14b_qlora_rslora_tok.yaml` | 2 | 143 | 20 | 0 | 0 | 1 | 0 | 100.0 | 143 | 0.0097 | 0.0860 | 26.47 | 2,788 |
| `size_4b_rslora_tok-s0` | `train/configs/size_4b_rslora_tok.yaml` | 0 | 147 | 20 | 0 | 0 | 0 | 0 | 99.1 | 147 | 0.0071 | 0.0952 | 27.58 | 7,317 |
| `size_4b_rslora_tok-s1` | `train/configs/size_4b_rslora_tok.yaml` | 1 | 143 | 19 | 0 | 0 | 1 | 0 | 100.0 | 143 | 0.0087 | 0.0925 | 27.58 | 7,324 |
| `size_4b_rslora_tok-s2` | `train/configs/size_4b_rslora_tok.yaml` | 2 | 138 | 20 | 0 | 0 | 1 | 1 | 100.0 | 138 | 0.0080 | 0.0883 | 27.58 | 7,318 |
| `size_8b_rslora_tok-s0` | `train/configs/size_8b_rslora_tok.yaml` | 0 | 143 | 20 | 0 | 0 | 1 | 1 | 100.0 | 143 | 0.0103 | 0.0927 | 26.97 | 5,221 |
| `size_8b_rslora_tok-s1` | `train/configs/size_8b_rslora_tok.yaml` | 1 | 139 | 20 | 0 | 2 | 0 | 1 | 100.0 | 139 | 0.0126 | 0.0901 | 26.97 | 5,222 |
| `size_8b_rslora_tok-s2` | `train/configs/size_8b_rslora_tok.yaml` | 2 | 141 | 20 | 0 | 0 | 1 | 0 | 100.0 | 141 | 0.0095 | 0.0895 | 26.97 | 5,222 |
| `l14b_full-s0` | `train/configs/l14b_full.yaml` | 0 | 125 | 20 | 0 | 1 | 0 | 1 | 92.3 | 125 | 0.0188 | 0.1030 | 92.7 | 2,473 |
| `l14b_full-s1` | `train/configs/l14b_full.yaml` | 1 | 117 | 20 | 0 | 0 | 0 | 2 | 93.2 | 117 | 0.0369 | 0.1043 | 92.69 | 2,451 |
| `tier_s_pilot_lora-s0` | `train/configs/tier_s_pilot_lora.yaml` | 0 | 123 | 13 | 0 | 10 | 2 | 1 | 0.0 | 120 | 0.1614 | 0.2563 | 18.88 | 20,232 |
| `tier_s_pilot_lora-s1` | `train/configs/tier_s_pilot_lora.yaml` | 1 | 130 | 17 | 1 | 12 | 2 | 1 | 0.0 | 128 | 0.1776 | 0.2534 | 18.88 | 20,225 |
| `tier_s_pilot_lora-s2` | `train/configs/tier_s_pilot_lora.yaml` | 2 | 121 | 17 | 0 | 18 | 1 | 1 | 0.0 | 118 | 0.1665 | 0.2503 | 18.88 | 20,323 |
| `tier_s_pilot_rslora-s0` | `train/configs/tier_s_pilot_rslora.yaml` | 0 | 142 | 12 | 2 | 5 | 6 | 1 | 0.0 | 140 | 0.1485 | 0.2462 | 18.88 | 20,213 |
| `tier_s_pilot_rslora-s1` | `train/configs/tier_s_pilot_rslora.yaml` | 1 | 129 | 9 | 0 | 18 | 4 | 0 | 0.0 | 130 | 0.1588 | 0.2402 | 18.88 | 20,278 |
| `tier_s_pilot_rslora-s2` | `train/configs/tier_s_pilot_rslora.yaml` | 2 | 137 | 13 | 0 | 2 | 1 | 1 | 0.0 | 136 | 0.1528 | 0.2442 | 18.88 | 20,340 |
| `tier_s_pilot_dora-s0` | `train/configs/tier_s_pilot_dora.yaml` | 0 | 118 | 17 | 0 | 18 | 0 | 2 | 0.0 | 119 | 0.1607 | 0.2554 | 18.89 | 11,776 |
| `tier_s_pilot_dora-s1` | `train/configs/tier_s_pilot_dora.yaml` | 1 | 120 | 16 | 0 | 17 | 1 | 1 | 0.0 | 121 | 0.1762 | 0.2533 | 18.89 | 11,785 |
| `tier_s_pilot_dora-s2` | `train/configs/tier_s_pilot_dora.yaml` | 2 | 111 | 17 | 0 | 31 | 1 | 2 | 0.0 | 116 | 0.1666 | 0.2503 | 18.89 | 11,792 |
| `tier_s_pilot_lora_paged8-s0` | `train/configs/tier_s_pilot_lora_paged8.yaml` | 0 | 124 | 16 | 0 | 14 | 1 | 1 | 0.0 | 120 | 0.1614 | 0.2552 | 18.82 | 19,770 |
| `tier_s_pilot_lora_paged8-s1` | `train/configs/tier_s_pilot_lora_paged8.yaml` | 1 | 124 | 14 | 0 | 14 | 3 | 1 | 0.0 | 123 | 0.1783 | 0.2547 | 18.82 | 19,705 |
| `tier_s_pilot_lora_paged8-s2` | `train/configs/tier_s_pilot_lora_paged8.yaml` | 2 | 110 | 17 | 0 | 22 | 5 | 1 | 0.0 | 114 | 0.1666 | 0.2505 | 18.82 | 19,754 |
| `tier_s_pilot_lora_nogroup-s0` | `train/configs/tier_s_pilot_lora_nogroup.yaml` | 0 | 121 | 20 | 0 | 23 | 0 | 1 | 0.0 | 120 | 0.1439 | 0.2450 | 18.87 | 19,309 |
| `tier_s_main_rslora-s0` | `train/configs/tier_s_main_rslora.yaml` | 0 | 147 | 19 | 0 | 9 | 4 | 0 | 0.0 | 132 | 0.1475 | 0.2354 | 21.63 | 14,105 |
| `tier_s_main_rslora-s1` | `train/configs/tier_s_main_rslora.yaml` | 1 | 141 | 20 | 0 | 1 | 1 | 0 | 0.0 | 141 | 0.1569 | 0.2347 | 21.63 | 14,148 |
| `tier_s_main_rslora-s2` | `train/configs/tier_s_main_rslora.yaml` | 2 | 133 | 20 | 0 | 0 | 1 | 1 | 0.0 | 131 | 0.1515 | 0.2334 | 21.63 | 14,151 |
| `l14b_sft_rslora-s0` | `train/configs/l14b_sft_rslora.yaml` | 0 | 160 | 20 | 0 | 5 | 1 | 0 | 0.0 | 147 | 0.1459 | 0.2146 | 38.81 | 3,454 |
| `l14b_sft_rslora-s1` | `train/configs/l14b_sft_rslora.yaml` | 1 | 145 | 20 | 0 | 13 | 0 | 2 | 0.0 | 147 | 0.1506 | 0.2077 | 38.81 | 3,453 |
| `l14b_sft_rslora-s2` | `train/configs/l14b_sft_rslora.yaml` | 2 | 152 | 20 | 0 | 5 | 0 | 3 | 0.0 | 147 | 0.1498 | 0.2044 | 38.81 | 3,454 |
