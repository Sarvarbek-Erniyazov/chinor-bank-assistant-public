# Handoff draft checks

`data/check_handoff.py` on 60 items. Contamination: exact (normalised) and fuzzy (rapidfuzz ratio ≥ 90) against 220 eval-v1 user turns and 2868 distinct training user turns. Nearest intent: most similar Banking77 train query; flag = held-out intent with similarity ≥ 0.60.

- Exact matches: eval-v1 0, training 0.
- Fuzzy ≥ 90: eval-v1 0, training 0 (max 65.8 / 73.2).
- Held-out nearest-intent flags (sim ≥ 0.60): ho-001, ho-036, ho-045.
- Items failing a hard check: none.

| Id | Topic | Max fuzzy eval | Max fuzzy train | Nearest intent | Sim. | Held out | Reply ok |
|---|---|---|---|---|---|---|---|
| ho-001 | safe_deposit_box | 51.5 | 58.6 | `request_refund` | 0.62 | **yes** | yes |
| ho-002 | safe_deposit_box | 48.2 | 53.5 | `supported_cards_and_currencies` | 0.54 |  | yes |
| ho-003 | safe_deposit_box | 53.2 | 56.1 | `card_about_to_expire` | 0.57 |  | yes |
| ho-004 | safe_deposit_box | 49.6 | 55.7 | `top_up_reverted` | 0.61 |  | yes |
| ho-005 | joint_account | 65.8 | 66.7 | `age_limit` | 0.67 |  | yes |
| ho-006 | joint_account | 50.0 | 54.7 | `cash_withdrawal_charge` | 0.57 |  | yes |
| ho-007 | joint_account | 63.6 | 61.0 | `transfer_into_account` | 0.65 |  | yes |
| ho-008 | joint_account | 52.9 | 55.9 | `edit_personal_details` | 0.57 |  | yes |
| ho-009 | standing_order | 53.4 | 57.1 | `automatic_top_up` | 0.59 |  | yes |
| ho-010 | standing_order | 49.6 | 58.2 | `transfer_into_account` | 0.56 |  | yes |
| ho-011 | standing_order | 54.2 | 56.7 | `order_physical_card` | 0.59 |  | yes |
| ho-012 | standing_order | 46.2 | 52.4 | `getting_spare_card` | 0.54 |  | yes |
| ho-013 | business_account | 51.9 | 55.0 | `age_limit` | 0.61 |  | yes |
| ho-014 | business_account | 57.1 | 68.7 | `age_limit` | 0.77 |  | yes |
| ho-015 | business_account | 56.6 | 60.2 | `supported_cards_and_currencies` | 0.60 |  | yes |
| ho-016 | business_account | 58.7 | 64.4 | `top_up_by_card_charge` | 0.65 |  | yes |
| ho-017 | payroll | 50.3 | 53.1 | `topping_up_by_card` | 0.56 |  | yes |
| ho-018 | payroll | 50.0 | 53.7 | `terminate_account` | 0.56 |  | yes |
| ho-019 | payroll | 47.5 | 60.9 | `receiving_money` | 0.52 |  | yes |
| ho-020 | payroll | 46.3 | 54.2 | `exchange_charge` | 0.56 |  | yes |
| ho-021 | insurance | 55.7 | 57.8 | `reverted_card_payment` | 0.58 |  | yes |
| ho-022 | insurance | 52.8 | 73.2 | `change_pin` | 0.74 |  | yes |
| ho-023 | insurance | 49.5 | 51.4 | `declined_cash_withdrawal` | 0.51 |  | yes |
| ho-024 | insurance | 55.2 | 57.8 | `pending_card_payment` | 0.58 |  | yes |
| ho-025 | gift_card | 57.8 | 57.7 | `supported_cards_and_currencies` | 0.60 |  | yes |
| ho-026 | gift_card | 53.1 | 54.5 | `pin_blocked` | 0.56 |  | yes |
| ho-027 | gift_card | 56.6 | 65.3 | `card_linking` | 0.65 |  | yes |
| ho-028 | gift_card | 54.2 | 59.3 | `card_about_to_expire` | 0.64 |  | yes |
| ho-029 | power_of_attorney | 47.5 | 53.5 | `getting_spare_card` | 0.56 |  | yes |
| ho-030 | power_of_attorney | 62.1 | 57.8 | `request_refund` | 0.59 | **yes** | yes |
| ho-031 | power_of_attorney | 51.1 | 55.4 | `card_linking` | 0.56 |  | yes |
| ho-032 | power_of_attorney | 49.6 | 52.5 | `transfer_into_account` | 0.56 |  | yes |
| ho-033 | bereavement | 56.2 | 57.1 | `transfer_into_account` | 0.59 |  | yes |
| ho-034 | bereavement | 54.9 | 66.7 | `terminate_account` | 0.70 |  | yes |
| ho-035 | bereavement | 48.8 | 53.8 | `verify_my_identity` | 0.60 |  | yes |
| ho-036 | bereavement | 58.3 | 62.4 | `visa_or_mastercard` | 0.66 | **yes** | yes |
| ho-037 | reference_letter | 51.9 | 53.6 | `transfer_into_account` | 0.56 |  | yes |
| ho-038 | reference_letter | 47.9 | 53.1 | `order_physical_card` | 0.58 |  | yes |
| ho-039 | reference_letter | 48.0 | 52.8 | `visa_or_mastercard` | 0.57 | **yes** | yes |
| ho-040 | reference_letter | 50.4 | 52.7 | `top_up_by_card_charge` | 0.56 |  | yes |
| ho-041 | merchant_terminal | 56.9 | 59.5 | `supported_cards_and_currencies` | 0.60 |  | yes |
| ho-042 | merchant_terminal | 52.0 | 55.4 | `direct_debit_payment_not_recognised` | 0.59 | **yes** | yes |
| ho-043 | merchant_terminal | 56.2 | 56.2 | `declined_card_payment` | 0.61 |  | yes |
| ho-044 | merchant_terminal | 57.4 | 60.2 | `top_up_by_bank_transfer_charge` | 0.60 |  | yes |
| ho-045 | rewards | 50.9 | 57.5 | `card_payment_fee_charged` | 0.60 | **yes** | yes |
| ho-046 | rewards | 54.1 | 59.1 | `verify_top_up` | 0.60 |  | yes |
| ho-047 | rewards | 61.3 | 63.2 | `edit_personal_details` | 0.67 |  | yes |
| ho-048 | rewards | 52.5 | 61.4 | `top_up_by_card_charge` | 0.60 |  | yes |
| ho-049 | pension | 59.5 | 65.3 | `supported_cards_and_currencies` | 0.65 |  | yes |
| ho-050 | pension | 47.6 | 53.8 | `card_about_to_expire` | 0.54 |  | yes |
| ho-051 | pension | 56.1 | 61.5 | `refund_not_showing_up` | 0.62 |  | yes |
| ho-052 | pension | 52.6 | 57.0 | `lost_or_stolen_phone` | 0.53 |  | yes |
| ho-053 | escrow | 48.8 | 51.6 | `cash_withdrawal_not_recognised` | 0.54 |  | yes |
| ho-054 | escrow | 46.7 | 53.4 | `age_limit` | 0.61 |  | yes |
| ho-055 | escrow | 51.8 | 53.8 | `balance_not_updated_after_bank_transfer` | 0.55 | **yes** | yes |
| ho-056 | escrow | 53.9 | 55.9 | `declined_card_payment` | 0.60 |  | yes |
| ho-057 | damaged_banknotes | 50.5 | 56.8 | `card_acceptance` | 0.57 |  | yes |
| ho-058 | damaged_banknotes | 53.0 | 54.7 | `request_refund` | 0.57 | **yes** | yes |
| ho-059 | damaged_banknotes | 53.2 | 50.9 | `transfer_into_account` | 0.54 |  | yes |
| ho-060 | damaged_banknotes | 47.2 | 53.9 | `receiving_money` | 0.54 |  | yes |
