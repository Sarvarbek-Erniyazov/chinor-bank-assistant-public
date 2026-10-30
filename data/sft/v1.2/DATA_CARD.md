# SFT v1.2

SFT v1.1 (`data/sft/v1.1/DATA_CARD.md`: v1 with B1 / B1-dialogue repeated 4×) plus 60 hand-written handoff examples
(`data/drafts/handoff_candidates.md`, approved by the author 2026-10-29). Built by `data/build_v1_2.py` (ADR-029).

## Why: unknown topics (T-held)

On the 10 held-out intents trained models answer with a memorised answer of a different, trained intent (78–90 %
of T-held answers; `results/t_held_analysis.md`) instead of saying they do not know. SFT v1 has no example of the
assistant declining a banking question it has no information on. v1.2 adds such examples.

## Handoff examples

- 60 customer questions on 15 banking topics that are neither Banking77 labels nor covered by the handbook (safe-deposit
  boxes, joint accounts, standing orders, business accounts, payroll, insurance, gift cards, power of attorney,
  bereavement, reference letters, merchant terminals, rewards, pensions, escrow, damaged banknotes), 4 each.
- Each reply says the assistant cannot answer from what it knows and hands off to a human agent in the in-app chat
  (daily 08:00–22:00); no facts, no other numbers, no claim that the product does or does not exist.
- Checks (`data/check_handoff.py`, `data/drafts/handoff_check.md`): 0 exact and 0 fuzzy (ratio ≥ 0.90) matches
  against eval-v1 and all training user turns; every reply passes the number / length / handoff checks.
- **Nearest-intent flags (lexical overlap only).** Three questions have a held-out Banking77 intent as their nearest
  intent at character similarity ≥ 0.60. The overlap is in wording only, not topic; the author kept them as written:
  - ho-001 (safe-deposit box): `request_refund`, 0.62 ("can i have a refund for one of your products");
  - ho-036 (bereavement / inheriting an account): `visa_or_mastercard`, 0.66 ("can i get a visa or does it have to be
    something else");
  - ho-045 (rewards / cashback): `card_payment_fee_charged`, 0.60 ("i noticed an extra fee when i paid with my card").

## Split

v1 rule (5 % per stratum, at least 1): 3 handoff items in val, one each from bereavement, business_account, pension;
57 in train. Topics are not split across train / val beyond those 3 items; no text is in both
splits. v1.1 train / val are carried over unchanged. Train shuffled with seed 20261029.

| | v1.1 | v1.2 |
|---|---|---|
| Train examples | 2,894 | 2,951 |
| Val examples | 144 | 147 |
| Handoff examples in train | 0 | 57 (1.9 %) |

Risks watched: over-refusal on clear in-scope questions (T-seen) and on B2; handoffs replacing correct answers.
