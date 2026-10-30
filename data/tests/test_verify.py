"""Unit tests for data/verify.py on 8 hand-made cases (one per rule, plus two accepts)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))
import verify  # noqa: E402

ACT = "activate_my_card"
AGE = "age_limit"

CASES = [
    # (name, text, intent, user, rules, expected accept, expected failing rule letters)
    ("accept_ascii_arrow",
     "Open the app and go to Cards -> Activate, then tap the card against your phone or scan it with the camera. "
     "The app never asks you to type the full card number or PIN to activate the card.",
     ACT, "How do I activate my card?", verify.ALL_RULES, True, set()),
    ("a_missing_fact",
     "Open the app and go to Cards → Activate, then follow the steps on the screen to finish activating your new card. "
     "It only takes a minute and there is nothing else you need to do.",
     ACT, "How do I activate my card?", verify.ALL_RULES, False, {"a"}),
    ("b_invented_number",
     "You can activate your card under Cards → Activate by tapping it against your phone or scanning it with the camera. "
     "Activation usually completes within 37 minutes.",
     ACT, "How do I activate my card?", verify.ALL_RULES, False, {"b"}),
    ("c_requests_pin",
     "You can activate your card under Cards → Activate by tapping it against your phone or scanning it. "
     "If that fails, please confirm your PIN here and I will check the card for you.",
     ACT, "How do I activate my card?", verify.ALL_RULES, False, {"c"}),
    ("d_forbidden_keyword",
     "You can open a Chinor account from age 16 if you live in one of our 12 supported countries; younger customers "
     "can join with parental consent. Have your passport or national ID ready for the selfie video check.",
     AGE, "How old do I have to be?", verify.ALL_RULES, False, {"d"}),
    ("e_too_short",
     "Use Cards → Activate: tap or scan the card.",
     ACT, "How do I activate my card?", verify.ALL_RULES, False, {"e"}),
    ("f_role_tag",
     "You can activate your card under Cards → Activate by tapping it against your phone or scanning it with the camera.\n"
     "User: thanks, and how long does delivery take?",
     ACT, "How do I activate my card?", verify.ALL_RULES, False, {"f"}),
    ("accept_number_echoed_from_user",
     "You can activate the card you received 37 minutes ago under Cards → Activate, by tapping it against your phone "
     "or scanning it with the camera. The app never asks for the full card number or PIN.",
     ACT, "I got my card 37 minutes ago, how do I activate it?", verify.ALL_RULES, True, set()),
    ("accept_behaviour_rules_skip_facts",
     "I can't help with investment advice, so I can't say which stocks to buy. For advice on your savings, please speak "
     "to a qualified financial adviser; I'm happy to help with anything about your Chinor account or card.",
     None, "Which stocks should I buy?", verify.BEHAVIOUR_RULES, True, set()),
]


@pytest.mark.parametrize("name,text,intent,user,rules,accept,failing", CASES, ids=[c[0] for c in CASES])
def test_verify_case(name, text, intent, user, rules, accept, failing):
    # the 8 hand-made cases isolate rules (a)-(f) as defined in v1; the accepts must also pass v2
    ok, reasons = verify.verify(text, intent, user, rules, version=1)
    assert ok is accept, reasons
    assert {r[0] for r in reasons} == failing, reasons
    if accept:
        assert verify.verify(text, intent, user, rules, version=2)[0]


def test_every_canonical_answer_passes():
    for intent, entry in verify.intents().items():
        ok, reasons = verify.verify(entry["canonical_answer"], intent)
        assert ok, (intent, reasons)


# ---------------- verifier v2: rules (b), (f), (g) ----------------

TOPUP = "topping_up_by_card"
FRIENDS_Q = "Can my friends top up my account?"


def test_v2_b_number_must_be_in_canonical_answer():
    text = ("Activate the card under Cards → Activate by tapping it against your phone or scanning it with the camera. "
            "A replacement card costs 35,000 UZS if you lose it.")
    assert verify.verify(text, ACT, "How do I activate my card?", version=1)[0]  # 35,000 is in the handbook
    ok, reasons = verify.verify(text, ACT, "How do I activate my card?", version=2)
    assert not ok and [r[0] for r in reasons] == ["b"], reasons


@pytest.mark.parametrize("text", [
    "Go to **Cards → Activate** and tap the card against your phone or scan it with the camera; the app never asks for your PIN.",
    "To activate your card:\n- open Cards → Activate\n- tap the card against your phone or scan it with the camera",
    "To activate your card:\n1. open Cards → Activate\n2. tap the card against your phone or scan it with the camera",
    "## Activation\nOpen Cards → Activate and tap the card against your phone or scan it with the camera, then you are done.",
], ids=["bold", "bullets", "numbered", "heading"])
def test_v2_f_rejects_markdown(text):
    assert verify.verify(text, ACT, "How do I activate my card?", version=1)[0]
    ok, reasons = verify.verify(text, ACT, "How do I activate my card?", version=2)
    assert not ok and "f" in [r[0] for r in reasons], reasons


def test_v2_f_keeps_arrows_and_plain_sentences():
    ok, reasons = verify.verify(verify.intents()[ACT]["canonical_answer"], ACT, "How do I activate my card?", version=2)
    assert ok, reasons


def test_v2_g_rejects_mostly_unsupported_content():
    text = ("Cards → Activate works when you tap or scan, but honestly autumn weather in Samarkand makes picnics "
            "delightful, so pack apricots, melons, bread and tea before travelling there by train.")
    ok, reasons = verify.verify(text, ACT, "How do I activate my card?", version=2)
    assert not ok and [r[0] for r in reasons] == ["g"], reasons
    assert verify.verify(text, ACT, "How do I activate my card?", version=1)[0]


def test_v2_friends_case_from_the_smoke_run():
    # GPU smoke run, task-2172: contradicts the handbook ("a card in your own name"), with markdown.
    smoke = ("Yes, your friends can top up your account by going to **Account → Top up** in the app and adding a Visa, "
             "Mastercard, UzCard, or Humo card in their own name. Credit-card top-ups carry a **1.1 %** fee, and the "
             "daily limit is **30,000,000 UZS**.")
    assert verify.verify(smoke, TOPUP, FRIENDS_Q, version=1)[0]
    ok, reasons = verify.verify(smoke, TOPUP, FRIENDS_Q, version=2)
    assert not ok and [r[0] for r in reasons] == ["f"], reasons
    # Without markdown the contradiction ("their" for "your") uses only supported words and numbers, so v2
    # accepts it: a known limit of lexical rules, left to the manual audit / an entailment check.
    plain = smoke.replace("**", "")
    assert verify.verify(plain, TOPUP, FRIENDS_Q, version=2)[0]
