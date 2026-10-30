# Contamination report

Date: 2026-10-27. Eval items: 220. Normalisation: lower-case, punctuation removed, whitespace collapsed.

## banking77_train

- corpus size: 10003 texts
- exact matches: **0** (must be 0)
- fuzzy matches (ratio ≥ 90): 23
- word 8-gram overlap rate: 3.02 % of 995 eval 8-grams

Fuzzy (eval → corpus, ratio):
- `T-seen-002`: "Could I open an account for my children?" → "Could I open an account for children?" (96.0)
- `T-seen-004`: "Can I use this card at an ATM?" → "Can I use this card at any ATM?" (98.3)
- `T-seen-009`: "Why isn't my transfer not going through? I keep getting an error message." → "Why will my transfer not go through?!  Keep getting an error message." (91.9)
- `T-seen-013`: "What places can I use my card?" → "In what places can I use my card?" (95.1)
- `T-seen-015`: "When can I expect to receive my new card?" → "When can I expect to receive my card?" (94.7)
- `T-seen-017`: "My actual card isn't working." → "My virtual card isn't working." (90.9)
- `T-seen-025`: "The app is showing an ATM withdrawl that I didn't make." → "The app is showing a cash withdrawal that I didn't make." (93.5)
- `T-seen-029`: "I'm not in the UK, can I get a card?" → "I am not in the UK can i get a card?" (97.1)
- `T-seen-033`: "My cash withdrawl was declined why?" → "My cash withdrawal was declined.  Why?" (98.6)
- `T-seen-046`: "What fiat currencies are supported for holding and exchange?" → "Which flat currencies are supported for holding and exchange?" (94.1)
- `T-seen-059`: "my atm cash out is still pending" → "my cash out is still pending" (93.3)
- `T-seen-066`: "What do I do if it says my card payment has been cancelled?" → "What does it mean if it says my card payment has been cancelled?" (92.6)
- `T-seen-068`: "How can I use American Express to add money to my account?" → "How can I use my American Express to add money into my account?" (95.8)
- `T-seen-075`: "Why did the app deny my top up?" → "Why did the app deny my top-up?" (98.3)
- `T-seen-079`: "Why don't I see my top up in my wallet?" → "I don't see my top up in my wallet." (91.4)
- `T-seen-080`: "How do my friends top up my account" → "How can my friends top up my account?" (93.0)
- `T-seen-081`: "Why have I been charged twice for the same transaction?" → "I have been charged twice for the same transaction." (94.2)
- `T-seen-086`: "how long do money transfers take?" → "How long does transfers take?" (90.0)
- `T-seen-089`: "How can I verify my indentity?" → "How can I verify my identity?" (98.2)
- `T-seen-090`: "What do I do for the identity check?" → "What do I need for the identity check?" (94.4)
- `T-seen-091`: "How can I see my source of funds?" → "How do I see my source of funds?" (92.1)
- `B1-001`: "How much does it cost to send money?" → "how much does it cost to add money" (92.8)
- `B1-008`: "Can I cancel my transfer?" → "How can I cancel my transfer?" (92.3)

## Verdict

**PASS: no exact matches.** Fuzzy matches are near-duplicates that Banking77 itself contains across its splits; they are listed so that the SFT data builder (Stage 1) can drop them from the training side.
