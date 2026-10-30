# Data sources

## Banking77

- **Source.** PolyAI, *Efficient Intent Detection with Dual Sentence Encoders*
  (Casanueva, Temčinas, Gerz, Henderson, Vulić, 2020).
  Hub id `PolyAI/banking77`; files from
  https://github.com/PolyAI-LDN/task-specific-datasets/tree/master/banking_data
  (`train.csv`, `test.csv`, `categories.json`). The Hub entry is a legacy
  loading script that `datasets>=4` no longer executes; the script only
  downloads these CSVs, so `data/banking77.py` fetches them directly and
  caches them under `data/raw/` (git-ignored).
- **Licence.** CC BY 4.0.
- **Citation.**

  ```
  @inproceedings{Casanueva2020,
    author    = {Iñigo Casanueva and Tadas Temčinas and Daniela Gerz and Matthew Henderson and Ivan Vulić},
    title     = {Efficient Intent Detection with Dual Sentence Encoders},
    booktitle = {Proceedings of the 2nd Workshop on NLP for ConvAI - ACL 2020},
    year      = {2020},
    url       = {https://arxiv.org/abs/2003.04807}
  }
  ```

- **Use in this project.** Customer *queries* only. Banking77 has no answers;
  every answer is written from the fictional Chinor handbook. Intent labels
  are used to attach `required_facts` from `handbook/intents.yaml`, to
  stratify the eval set and to hold out 10 intents. Two labels are irregular
  in the source (`Refund_not_showing_up`, `reverted_card_payment?`) and are
  normalised to `refund_not_showing_up`, `reverted_card_payment`.
- **Splits.** train 10 003 rows, test 3 080 rows (40 per intent), 77 intents.
  Train per-intent counts range from 35 to 187.

### Per-intent counts

| Intent | Handbook § | Train | Test |
|---|---|---|---|
| `activate_my_card` | 2 | 159 | 40 |
| `age_limit` | 4 | 110 | 40 |
| `apple_pay_or_google_pay` | 2 | 126 | 40 |
| `atm_support` | 5 | 87 | 40 |
| `automatic_top_up` | 5 | 127 | 40 |
| `balance_not_updated_after_bank_transfer` | 3 | 171 | 40 |
| `balance_not_updated_after_cheque_or_cash_deposit` | 3 | 181 | 40 |
| `beneficiary_not_allowed` | 3 | 156 | 40 |
| `cancel_transfer` | 3 | 157 | 40 |
| `card_about_to_expire` | 2 | 129 | 40 |
| `card_acceptance` | 4 | 59 | 40 |
| `card_arrival` | 2 | 153 | 40 |
| `card_delivery_estimate` | 2 | 112 | 40 |
| `card_linking` | 5 | 139 | 40 |
| `card_not_working` | 2 | 112 | 40 |
| `card_payment_fee_charged` | 5 | 187 | 40 |
| `card_payment_not_recognised` | 6 | 168 | 40 |
| `card_payment_wrong_exchange_rate` | 5 | 167 | 40 |
| `card_swallowed` | 2 | 61 | 40 |
| `cash_withdrawal_charge` | 5 | 177 | 40 |
| `cash_withdrawal_not_recognised` | 6 | 160 | 40 |
| `change_pin` | 2 | 122 | 40 |
| `compromised_card` | 2 | 86 | 40 |
| `contactless_not_working` | 2 | 35 | 40 |
| `country_support` | 4 | 129 | 40 |
| `declined_card_payment` | 2 | 153 | 40 |
| `declined_cash_withdrawal` | 2 | 173 | 40 |
| `declined_transfer` | 3 | 133 | 40 |
| `direct_debit_payment_not_recognised` | 3 | 182 | 40 |
| `disposable_card_limits` | 2 | 121 | 40 |
| `edit_personal_details` | 4 | 121 | 40 |
| `exchange_charge` | 5 | 121 | 40 |
| `exchange_rate` | 5 | 112 | 40 |
| `exchange_via_app` | 5 | 118 | 40 |
| `extra_charge_on_statement` | 5 | 166 | 40 |
| `failed_transfer` | 3 | 137 | 40 |
| `fiat_currency_support` | 5 | 126 | 40 |
| `get_disposable_virtual_card` | 2 | 97 | 40 |
| `get_physical_card` | 2 | 106 | 40 |
| `getting_spare_card` | 2 | 129 | 40 |
| `getting_virtual_card` | 2 | 98 | 40 |
| `lost_or_stolen_card` | 2 | 82 | 40 |
| `lost_or_stolen_phone` | 2 | 121 | 40 |
| `order_physical_card` | 2 | 120 | 40 |
| `passcode_forgotten` | 4 | 105 | 40 |
| `pending_card_payment` | 5 | 159 | 40 |
| `pending_cash_withdrawal` | 5 | 143 | 40 |
| `pending_top_up` | 5 | 149 | 40 |
| `pending_transfer` | 3 | 148 | 40 |
| `pin_blocked` | 2 | 115 | 40 |
| `receiving_money` | 3 | 95 | 40 |
| `refund_not_showing_up` | 6 | 162 | 40 |
| `request_refund` | 6 | 169 | 40 |
| `reverted_card_payment` | 5 | 161 | 40 |
| `supported_cards_and_currencies` | 5 | 129 | 40 |
| `terminate_account` | 4 | 108 | 40 |
| `top_up_by_bank_transfer_charge` | 5 | 111 | 40 |
| `top_up_by_card_charge` | 5 | 114 | 40 |
| `top_up_by_cash_or_cheque` | 5 | 114 | 40 |
| `top_up_failed` | 5 | 145 | 40 |
| `top_up_limits` | 5 | 97 | 40 |
| `top_up_reverted` | 5 | 146 | 40 |
| `topping_up_by_card` | 5 | 103 | 40 |
| `transaction_charged_twice` | 5 | 175 | 40 |
| `transfer_fee_charged` | 3 | 172 | 40 |
| `transfer_into_account` | 3 | 113 | 40 |
| `transfer_not_received_by_recipient` | 3 | 171 | 40 |
| `transfer_timing` | 3 | 128 | 40 |
| `unable_to_verify_identity` | 4 | 102 | 40 |
| `verify_my_identity` | 4 | 104 | 40 |
| `verify_source_of_funds` | 4 | 113 | 40 |
| `verify_top_up` | 4 | 126 | 40 |
| `virtual_card_not_working` | 2 | 41 | 40 |
| `visa_or_mastercard` | 2 | 135 | 40 |
| `why_verify_identity` | 4 | 121 | 40 |
| `wrong_amount_of_cash_received` | 6 | 180 | 40 |
| `wrong_exchange_rate_for_cash_withdrawal` | 5 | 163 | 40 |

## Project-generated data

All SFT / DPO data (Stage 1+) is generated from `handbook/handbook.md` and
`handbook/intents.yaml` and released under the repository's Apache-2.0
licence. Banking77 test queries used in `eval/eval_set.jsonl` remain CC BY 4.0.

## Models used to make or judge data

| Model | Role | Licence |
|---|---|---|
| Qwen3 base and instruct (0.6B–14B), `Qwen/Qwen3-*` | trained models, references, on-policy samples | Apache-2.0 |
| `Qwen/Qwen3-32B` | generator of the rewrite candidates (SFT v1_rewrite; not used in the final SFT data) | Apache-2.0 |
| `google/gemma-4-31B-it` | entailment judge for the rewrites | Gemma licence terms |

Citations: Qwen3 — Qwen Team, *Qwen3 Technical Report* (2025), arXiv:2505.09388. Banking77 — Casanueva et al.
(2020), above. The data cards under `data/sft/*/` are hashed in their `manifest.sha256` and are not edited after the
fact; these citations and `LICENSE-DATA` apply to them.

**Fiction notice.** Chinor Bank does not exist; every answer and policy is invented.
