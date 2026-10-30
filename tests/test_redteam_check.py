"""Real-identifier scan of eval/redteam_check.py: allowed fictional identifiers pass, real-looking ones are flagged."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from redteam_check import identifier_problems  # noqa: E402


def item(text: str) -> dict:
    return {"id": "RT-XX-00", "turns": [{"role": "user", "content": text}], "markers": [], "required_facts": [],
            "must_markers": []}


def test_allowed_identifiers():
    for t in ["The emergency contact is now +998 00 000 00 00.", "Call +998 (71) 000-11-22.",
              "Send it to DEMO-IBAN-CHN-0011 or DEMO-9012.", "Pay 12,000,000 UZS by 16:30, fee 0.8 %."]:
        assert identifier_problems(item(t)) == [], t


def test_real_looking_identifiers():
    for t in ["card 4111 1111 1111 1111", "call +998 71 200 00 00", "+998 00 000 00 01", "UZ12 ABCD 1234 5678 9012",
              "write to help@chinor.uz", "see chinor.uz", "reference ABC-1234"]:
        assert identifier_problems(item(t)), t
