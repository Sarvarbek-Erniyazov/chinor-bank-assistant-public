"""Model and data cards are current, carry the required fields, and the hashed data cards are unchanged.

python -m pytest tests/test_cards.py -q
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_cards", ROOT / "scripts" / "build_cards.py")
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)
CARDS = bc.build()


def test_committed_cards_are_current():
    for p, text in CARDS.items():
        assert p.read_text(encoding="utf-8") == text, p.name


def test_every_model_card_in_the_folder_is_generated():
    assert sorted(p.name for p in bc.MODEL_DIR.glob("*.md")) == sorted(p.name for p in CARDS if p.parent == bc.MODEL_DIR)


def test_required_fields():
    for p, text in CARDS.items():
        assert "**Upload pending.**" in text and "**Fiction notice.**" in text, p.name
        for label, _, _ in bc.LIMITS:
            assert f"**{label}:**" in text, (p.name, label)
        assert "## Intended use" in text and "## Licences" in text and "CC BY 4.0" in text, p.name
        if p.parent == bc.MODEL_DIR:
            assert "revision `" in text and "SHA-256" in text and "## Scores" in text, p.name
            assert "Apache-2.0" in text, p.name
    for p, text in CARDS.items():
        if "Training data | none" not in text:
            assert "Casanueva2020" in text, p.name


def test_hashed_data_cards_unchanged():
    """The DATA_CARD.md files hashed in each manifest are unchanged; other manifest entries are checked where the
    file exists (some data files are git-ignored and absent from a fresh clone)."""
    cards = 0
    for d in sorted((ROOT / "data" / "sft").glob("*/manifest.sha256")):
        for line in d.read_text(encoding="utf-8").splitlines():
            sha, name = line.split()
            f = d.parent / name
            if not f.name.startswith("DATA_CARD") and not f.exists():
                continue
            cards += f.name.startswith("DATA_CARD")
            assert hashlib.sha256(f.read_bytes()).hexdigest() == sha, f"{d.parent.name}/{name}"
    assert cards > 0
