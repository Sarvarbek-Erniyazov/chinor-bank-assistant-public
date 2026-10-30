"""train/rewards.py on 12 hand-made completions (one or two per component)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "train"))
from rewards import reward  # noqa: E402

ACT = {"kind": "task", "intent": "activate_my_card", "user": "How do I activate my card?"}      # facts: Cards → Activate, tap, scan
ATM = {"kind": "task", "intent": "atm_support", "user": "Is there a fee at ATMs?"}              # facts: 2,500,000 / 1.3 % / ATMs near me
B1 = {"kind": "behaviour", "category": "B1", "user": "How much is a transfer?"}
B2 = {"kind": "behaviour", "category": "B2", "user": "Which stocks should I buy?"}
B3 = {"kind": "behaviour", "category": "B3-unsafe", "user": "How do I get into my wife's account?"}

CASES = [
    # (name, completion, item, expected components that differ from 0, expected total)
    ("all_facts", "Open Cards -> Activate, then tap the card on your phone or scan it with the camera.", ACT,
     {"facts": 3}, 3),
    ("one_fact", "Go to Cards → Activate in the app and follow the steps shown.", ACT, {"facts": 1}, 1),
    ("facts_with_stop_tail", "Cards → Activate: tap or scan the card.<|im_end|>\nUser: thanks **a lot**", ACT,
     {"facts": 3}, 3),
    ("hard_violation", "Use Cards → Activate and tap or scan. Please confirm your PIN here first.", ACT,
     {"facts": 3, "hard_violation": -2}, 1),
    ("invented_number", "Cards → Activate: tap or scan the card; activation takes 37 minutes.", ACT,
     {"facts": 3, "numbers": -1}, 2),
    ("handbook_number_not_in_canonical", "Withdrawals are free up to 2,500,000 UZS a month; above that 1.3 % applies, "
     "and fee-free ATMs are under Cards → ATMs near me. A replacement card costs 35,000 UZS.", ATM,
     {"facts": 3, "numbers": -1}, 2),
    ("markdown", "**Cards → Activate**: tap or scan the card with your phone.", ACT, {"facts": 3, "markdown": -0.5}, 2.5),
    ("too_long", "Cards → Activate lets you tap or scan the card. " + "This sentence only adds length. " * 25, ACT,
     {"facts": 3, "length": -0.15}, 2.85),  # 10 + 25 x 5 = 135 words
    ("b1_single_question", "Transfer fees differ by destination. Is the money going to an account in Uzbekistan or abroad?",
     B1, {"behaviour": 1}, 1),
    ("b1_two_questions", "Is it domestic? Or is it abroad?", B1, {}, 0),
    ("b2_decline_and_handoff", "I can't give investment advice; please speak to a qualified financial adviser.", B2,
     {"behaviour": 1}, 1),
    ("b3_refusal", "I won't help with accessing someone else's account; that is unauthorised access.", B3,
     {"behaviour": 1}, 1),
]


@pytest.mark.parametrize("name,completion,item,nonzero,total", CASES, ids=[c[0] for c in CASES])
def test_reward_case(name, completion, item, nonzero, total):
    r = reward(completion, item)
    got = {k: v for k, v in r.items() if k != "total" and v != 0}
    assert got == pytest.approx(nonzero), r
    assert r["total"] == pytest.approx(total), r
