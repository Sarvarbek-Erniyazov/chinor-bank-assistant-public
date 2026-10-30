# T-held diagnosis: answers on the 10 held-out intents (20 items)

`eval/t_held_analysis.py`. Classes, checked in order: **(a)** near-verbatim canonical answer of a training intent (difflib ratio ≥ 0.80 to the nearest training intent's canonical answer); **(b)** handoff or "don't know" (scorer handoff markers, decline cues, explicit don't-know); **(c)** other. Training data: SFT v1, canonical answers only (ADR-024).

| Arm | (a) training-intent answer | (b) handoff / don't know | (c) other | T-held pass | median sim. to nearest training intent | median sim. to own (held-out) canonical |
|---|---|---|---|---|---|---|
| `tier_s_main_rslora_tok-s0` | 17 | 0 | 3 | 2 / 20 | 1.00 | 0.14 |
| `tier_s_main_rslora_tok-s1` | 18 | 1 | 1 | 2 / 20 | 1.00 | 0.11 |
| `tier_s_main_rslora_tok-s2` | 19 | 0 | 1 | 2 / 20 | 1.00 | 0.10 |
| `l14b_sft_rslora_tok-s0` | 15 | 2 | 3 | 2 / 20 | 1.00 | 0.17 |
| `l14b_sft_rslora_tok-s1` | 19 | 0 | 1 | 0 / 20 | 1.00 | 0.19 |
| `l14b_sft_rslora_tok-s2` | 14 | 3 | 3 | 2 / 20 | 1.00 | 0.15 |

## Examples of (a)

- **T-held-004** (`l14b_sft_rslora_tok-s2`), held-out intent `balance_not_updated_after_bank_transfer`; nearest training intent `pending_transfer`, similarity 1.00.
  - User: My bank transfer is still not showing up in my account.
  - Answer: A transfer shows Scheduled until it leaves Chinor and Sent afterwards. Domestic transfers to other banks arrive the same business day if sent before 16:30, otherwise the next business day; international transfers take 2–4 business days. While it is Scheduled you can still cancel it in the app.
  - Canonical answer of `pending_transfer`: A transfer shows Scheduled until it leaves Chinor and Sent afterwards. Domestic transfers to other banks arrive the same business day if sent before 16:30, otherwise the next business day; international transfers take 2–4 business days. While it is Scheduled you can still cancel it in the app.

- **T-held-005** (`l14b_sft_rslora_tok-s2`), held-out intent `card_arrival`; nearest training intent `card_delivery_estimate`, similarity 1.00.
  - User: Is it normal to have to wait over a week for my new card?
  - Answer: Standard delivery takes 7 business days. Express delivery takes 2 business days and costs 45,000 UZS. The first physical card has no delivery fee on either plan.
  - Canonical answer of `card_delivery_estimate`: Standard delivery takes 7 business days. Express delivery takes 2 business days and costs 45,000 UZS. The first physical card has no delivery fee on either plan.

- **T-held-006** (`l14b_sft_rslora_tok-s2`), held-out intent `card_arrival`; nearest training intent `card_delivery_estimate`, similarity 1.00.
  - User: I ordered a card but it has not arrived. Help please!
  - Answer: Standard delivery takes 7 business days. Express delivery takes 2 business days and costs 45,000 UZS. The first physical card has no delivery fee on either plan.
  - Canonical answer of `card_delivery_estimate`: Standard delivery takes 7 business days. Express delivery takes 2 business days and costs 45,000 UZS. The first physical card has no delivery fee on either plan.

## Per item (14B, first seed)

| Id | Held-out intent | Class | Nearest training intent | Sim. |
|---|---|---|---|---|
| T-held-001 | `apple_pay_or_google_pay` | c | `top_up_by_cash_or_cheque` | 0.37 |
| T-held-002 | `apple_pay_or_google_pay` | a | `topping_up_by_card` | 1.00 |
| T-held-003 | `balance_not_updated_after_bank_transfer` | b | `change_pin` | 0.36 |
| T-held-004 | `balance_not_updated_after_bank_transfer` | a | `pending_transfer` | 1.00 |
| T-held-005 | `card_arrival` | a | `card_delivery_estimate` | 1.00 |
| T-held-006 | `card_arrival` | a | `card_delivery_estimate` | 1.00 |
| T-held-007 | `card_payment_fee_charged` | a | `extra_charge_on_statement` | 1.00 |
| T-held-008 | `card_payment_fee_charged` | a | `extra_charge_on_statement` | 1.00 |
| T-held-009 | `card_swallowed` | a | `cash_withdrawal_not_recognised` | 1.00 |
| T-held-010 | `card_swallowed` | b | `change_pin` | 0.42 |
| T-held-011 | `contactless_not_working` | c | `change_pin` | 0.31 |
| T-held-012 | `contactless_not_working` | c | `top_up_by_cash_or_cheque` | 0.29 |
| T-held-013 | `direct_debit_payment_not_recognised` | a | `card_payment_not_recognised` | 1.00 |
| T-held-014 | `direct_debit_payment_not_recognised` | a | `cancel_transfer` | 1.00 |
| T-held-015 | `request_refund` | a | `refund_not_showing_up` | 1.00 |
| T-held-016 | `request_refund` | a | `refund_not_showing_up` | 1.00 |
| T-held-017 | `unable_to_verify_identity` | a | `verify_my_identity` | 1.00 |
| T-held-018 | `unable_to_verify_identity` | a | `verify_my_identity` | 1.00 |
| T-held-019 | `visa_or_mastercard` | a | `supported_cards_and_currencies` | 1.00 |
| T-held-020 | `visa_or_mastercard` | a | `card_acceptance` | 1.00 |
