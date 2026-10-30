# B1 diagnosis: what the 14B models answer when a detail is missing

`eval/b1_analysis.py` (CPU). The frozen B1 rule is unchanged: pass = the answer asks a question that names the missing slot. Classes, checked in order: *asks (pass)*; **(a)** covers every branch of the missing slot (all of each branch's handbook facts present); **(c)** asks a question but fails the rule; **(b)** covers some branches but not all, no question; **(d)** other. Branch facts are regexes from the handbook (`BRANCHES` in the script) — a hand-made mapping, listed below for checking.

| Arm | Answers | asks the right question (passes the rule) | (a) covers all branches | (b) some branches, not all | (c) asks but fails the rule | (d) other |
|---|---|---|---|---|---|---|
| 14B rsLoRA v1 | 60 | 3 (5 %) | 29 (48 %) | 18 (30 %) | 1 (2 %) | 9 (15 %) |
| 14B rsLoRA v1.1 | 60 | 4 (7 %) | 25 (42 %) | 17 (28 %) | 2 (3 %) | 12 (20 %) |
| 14B full FT (lr 1e-5) | 40 | 0 (0 %) | 16 (40 %) | 17 (42 %) | 0 (0 %) | 7 (18 %) |

## Can an answer cover every branch? (per item)

| Item | Question | Slot keyword (rule) | Branches (handbook facts) | Covering all branches |
|---|---|---|---|---|
| B1-001 | How much does it cost to send money? | within Uzbekistan / domestic / abroad / international / another country / which country / where | domestic: `2,500\b\|20 (free )?(domestic )?transfers\|free up to 20`; international / SWIFT: `0\.8 ?% & 60,000` | possible |
| B1-002 | How long will my card take to arrive? | standard / express | standard: `7 business days`; express: `2 business days & 45,000` | possible |
| B1-003 | How many virtual cards can I have? | Standard / Plus / plan | Standard: `standard & \b(1\|one) virtual`; Plus: `plus & \b(5\|five)\b` | possible |
| B1-004 | Is there a fee for ATM withdrawals? | Standard / Plus / plan / how much / withdrawn this month | Standard: `2,500,000`; Plus: `6,000,000` | possible |
| B1-005 | My transfer hasn't arrived yet. What's wrong? | Scheduled / Sent / status / domestic / international / SWIFT / when / another bank / Chinor account | Chinor to Chinor: `instant`; other Uzbek bank: `16:30`; international: `2.4 business days` | partly |
| B1-006 | Will I be charged for a replacement card? | first / this year / already / replaced before / calendar year | first this year: `first & free`; already replaced: `35,000` | possible |
| B1-007 | How long does a pending transaction take to clear? | card payment / ATM / withdrawal / top-up / top up / what kind / which type / type of transaction | card payment: `9 business days`; ATM withdrawal: `4 business days`; top-up: `top-?up` | possible |
| B1-008 | Can I cancel my transfer? | Scheduled / Sent / status / domestic / international / SWIFT / within Uzbekistan / abroad | domestic: `scheduled`; SWIFT: `24 hours & 90,000` | possible |
| B1-009 | My card was just declined and I don't know why. Can you help? | where / online / ATM / shop / contactless / in store / in-store / reason / message / frozen / what kind of payment | payment context: `balance\|frozen\|limit\|3-?d secure\|fraud` | not possible |
| B1-010 | Is exchanging currency free? | Standard / Plus / plan / how much / amount / weekend / which day | Standard: `15,000,000 & 0\.6 ?%`; Plus: `unlimited`; weekend: `0\.9 ?%` | possible |
| B1-011 | I was charged a fee on my card payment. Why? | weekend / currency / merchant / which / what kind / where / when / what type | weekend: `0\.9 ?%`; above allowance: `0\.6 ?%`; merchant category: `0\.5 ?%` | possible |
| B1-012 | Is there a fee for topping up? | debit / credit / card / bank transfer / cash / how / which method / what method | debit card / bank transfer / cash: `free`; credit card: `1\.1 ?%` | possible |
| B1-013 | My top-up hasn't arrived. | card / bank transfer / cash / how / which method / when / how long ago | card: `instant\|2 business days`; bank transfer: `1 business day`; cash: `immediately\|same business day` | partly |
| B1-014 | Can I get a second card? | physical / virtual / Standard / Plus / plan | physical: `35,000\|spare\|2 physical\|two physical`; virtual: `virtual` | possible |
| B1-015 | What's the limit on my card? | daily / spending / contactless / ATM / disposable / which limit / what kind of limit / which type | daily spending: `25,000,000`; contactless: `900,000`; ATM: `6,000,000`; disposable: `3,000,000` | possible |
| B1-016 | Can my sister open an account? | age / old / country / resident / live / where | age: `\b16\b`; country: `\b12\b\|supported countr` | possible |
| B1-017 | How long does verification take? | identity / source of funds / which / what kind / top-up / top up / document | identity: `2 hours\|1 business day`; source of funds: `10 days` | possible |
| B1-018 | I need to dispute a transaction. | which / when / merchant / card payment / ATM / withdrawal / date / amount / what kind / recognise | card payment / ATM: `60 days`; wrong cash at ATM: `48 hours`; merchant refund: `15 days\|merchant first` | partly |
| B1-019 | Can I still stop a direct debit before it's taken? | when / date / collection / which / due / how soon | collection date: `1 business day` | possible |
| B1-020 | How much can I withdraw? | per day / daily / month / Standard / Plus / plan / which plan | daily: `6,000,000`; monthly free (Standard): `2,500,000` | possible |

*possible*: general handbook rules answer every branch. *partly*: the rules for each branch can be stated, but the customer's own case (why it has not arrived, which transaction) cannot be resolved without the detail. *not possible*: the answer depends on facts the assistant cannot see (the decline reason).

## Examples (up to 3 per class, different items)

### asks the right question (passes the rule)

- **B1-018** (`l14b_sft_rslora_tok-s0`). User: “I need to dispute a transaction.” Answer: “Every transaction you dispute goes through the same steps. The first step is to raise the dispute in the app within the transaction screen, so I need a few details about the transaction you want to dispute. Which card was it charged to?”
- **B1-020** (`l14b_sft_rslora_tok-s2`). User: “How much can I withdraw?” Answer: “Are you using a Chinor ATM or a regular ATM? Chinor ATMs are free, and withdrawals from other ATMs are free up to 2,500,000 UZS per month on Standard and 6,000,000 UZS on Plus; above the allowance a 1.3 % fee applies.”
- **B1-013** (`l14b_sft_rslora_tok-s1-v1.1`). User: “My top-up hasn't arrived.” Answer: “How long a top-up takes depends on the method you used. Did you top up by card, by bank transfer, or with cash?”

### (a) covers all branches

- **B1-002** (`l14b_sft_rslora_tok-s0`). User: “How long will my card take to arrive?” Answer: “Standard delivery takes 7 business days. Express delivery takes 2 business days and costs 45,000 UZS. The first physical card has no delivery fee on either plan.”
- **B1-003** (`l14b_sft_rslora_tok-s0`). User: “How many virtual cards can I have?” Answer: “Virtual cards are free and created instantly in the app under Cards → New virtual card. Standard customers can have 1 virtual card at a time and Plus customers up to 5; virtual cards work online and in Apple Pay and Google Pay.”
- **B1-004** (`l14b_sft_rslora_tok-s0`). User: “Is there a fee for ATM withdrawals?” Answer: “ATM withdrawals are free up to 2,500,000 UZS per month on Standard and 6,000,000 UZS on Plus; above the allowance a 1.3 % fee applies. Some ATM operators add their own surcharge, which the ATM shows before you confirm; Chinor does not control or refund operator surcharges.”

### (b) some branches, not all

- **B1-005** (`l14b_sft_rslora_tok-s0`): covers: other Uzbek bank, international. User: “My transfer hasn't arrived yet. What's wrong?” Answer: “If the transfer shows Sent and the normal time has passed — same business day for domestic transfers sent before 16:30, 2–4 business days for international ones — a human agent can trace it. Please have the 16-character reference starting with CB from the transfer screen ready and open in-app chat (daily 08:00–22:00).”
- **B1-007** (`l14b_sft_rslora_tok-s0`): covers: card payment. User: “How long does a pending transaction take to clear?” Answer: “A card payment can stay pending for up to 9 business days until the merchant settles it; a pre-authorisation that is never settled (hotels, fuel pumps, car rental) is released automatically after the same 9 business days. The amount is reserved from your balance in the meantime.”
- **B1-013** (`l14b_sft_rslora_tok-s0`): covers: card, bank transfer. User: “My top-up hasn't arrived.” Answer: “Card top-ups are normally instant but can take up to 2 business days when the card issuer holds them; bank-transfer top-ups are credited within 1 business day. If the time has passed, ask your card issuer or bank whether the payment left, and a human agent can trace it with the reference.”

### (c) asks but fails the rule

- **B1-015** (`l14b_sft_rslora_tok-s2`): slot keyword absent. User: “What's the limit on my card?” Answer: “The limit depends on the type of card you have. Which card is this, a regular Chinor card or a Plus card?”
- **B1-011** (`l14b_sft_rslora_tok-s0-v1.1`): slot keyword absent. User: “I was charged a fee on my card payment. Why?” Answer: “The reason depends on the kind of payment you made. Was it a purchase, a cash withdrawal, or a top-up?”
- **B1-020** (`l14b_sft_rslora_tok-s1-v1.1`): slot keyword absent. User: “How much can I withdraw?” Answer: “Are you using a regular ATM or a Chinor ATM? The withdrawal limit is different for each type, so I need that detail first.”

### (d) other

- **B1-001** (`l14b_sft_rslora_tok-s0`): no question asked; slot keyword absent. User: “How much does it cost to send money?” Answer: “Topping up by bank transfer is free and the money is credited within 1 business day. Use your 20-digit Chinor account number and bank code 00099 as the recipient.”
- **B1-015** (`l14b_sft_rslora_tok-s0`): no question asked; slot keyword absent. User: “What's the limit on my card?” Answer: “Chinor cards work in more than 180 countries wherever the Visa or Mastercard network is accepted, except in countries under international sanctions. If a merchant declines the card, the app shows the decline reason under the transaction.”
- **B1-019** (`l14b_sft_rslora_tok-s0`): no question asked; slot keyword absent. User: “Can I still stop a direct debit before it's taken?” Answer: “A domestic transfer can be cancelled in the app only while its status is Scheduled; once it shows Sent it cannot be cancelled. An international (SWIFT) transfer can be recalled within 24 hours of sending for a 90,000 UZS recall fee, but recall is not guaranteed because the receiving bank must agree.”

## Ambiguous cases for the author to confirm

10 answers: a branch's facts match only in part, or class (a) on an item where full coverage is only partly possible.

| Item | Run | Class given | Why ambiguous | Answer |
|---|---|---|---|---|
| B1-009 | `l14b_sft_rslora_tok-s0` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-009 | `l14b_sft_rslora_tok-s1` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-009 | `l14b_sft_rslora_tok-s2` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-006 | `l14b_sft_rslora_tok-s0-v1.1` | d | partial facts for: first this year | A replacement card is sent automatically, free of charge, 45 days before your card expires, to the address in your profile. Your current card keeps working until the last day of its expiry month. When the new card arrive… |
| B1-009 | `l14b_sft_rslora_tok-s0-v1.1` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-009 | `l14b_sft_rslora_tok-s1-v1.1` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-003 | `l14b_sft_rslora_tok-s2-v1.1` | asks (pass) | partial facts for: Standard, Plus | The number of virtual cards you can have depends on your plan. Which plan are you on, Chinor Standard or Chinor Plus? |
| B1-009 | `l14b_sft_rslora_tok-s2-v1.1` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-009 | `l14b_full-s0` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
| B1-009 | `l14b_full-s1` | a | class (a) on a 'not possible' item | The decline reason is shown under the transaction in the app. Common causes are insufficient balance in the payment currency, a frozen card, a blocked merchant category or toggle under Cards → Security, the daily limit, … |
