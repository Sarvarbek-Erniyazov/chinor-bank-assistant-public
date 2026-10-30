# SFT v1.1

SFT v1 (`data/sft/v1/DATA_CARD.md`, canonical answers, ADR-024) with the approved B1 and B1-dialogue training
examples repeated; no new text. Built by `data/build_v1_1.py` (ADR-028).

## Why: asking for a missing detail (B1)

Every trained arm passes 0–1 of the 20 B1 eval items. Only 69 of 2724 SFT v1 train
assistant turns (2.5 %) ask a question (`results/negative_results.md`). v1.1 raises
that share by repetition to test whether data balance, not capacity, is the cause.

## Construction

- Repeated: the 66 train examples of categories B1 (38) and B1-dialogue
  (28); each appears **4×** in train (ids `<id>-rep2` … `-rep4`).
  Factor rule: the integer that brings asking-type turns closest to 10 % of all train examples.
- Val: SFT v1 val unchanged (its 2 B1 and 2 B1-dialogue examples are not repeated); no example in both splits.
- Train shuffled with seed 20261029.

| | v1 train | v1.1 train |
|---|---|---|
| Examples | 2,696 | 2,894 |
| Assistant turns | 2,724 | 3,006 |
| Asking-type turns (contain "?") | 69 | 267 |
| … share of examples | 2.6 % | 9.2 % |
| … share of assistant turns | 2.5 % | 8.9 % |

Risk watched: more asking turns may make the model ask instead of answer on clear requests (over-asking /
over-refusal on the T blocks).
