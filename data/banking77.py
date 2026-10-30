"""Banking77 loader.

The Hugging Face entry `PolyAI/banking77` is a legacy loading script that
`datasets>=4` refuses to execute; the script itself only downloads the CSVs
from the PolyAI GitHub repository, so this module fetches those files
directly and caches them under data/raw/ (git-ignored).

Licence: CC BY 4.0 (Casanueva et al., 2020).
"""
from __future__ import annotations

import csv
import json
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BASE_URL = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/"
FILES = {"train": "train.csv", "test": "test.csv", "categories": "categories.json"}


def normalise(intent: str) -> str:
    """Two of the 77 labels are irregular in the source files
    ('Refund_not_showing_up', 'reverted_card_payment?'); use lower-case
    snake_case without punctuation everywhere in the project."""
    return intent.strip().lower().rstrip("?")


def _fetch(name: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"b77_{FILES[name]}"
    if not dest.exists():
        urllib.request.urlretrieve(BASE_URL + FILES[name], dest)
    return dest


def load_split(split: str) -> list[dict]:
    """Return a list of {"text", "intent"} rows for 'train' or 'test'."""
    path = _fetch(split)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [{"text": r["text"], "intent": normalise(r["category"])} for r in rows]


def intent_names() -> list[str]:
    with _fetch("categories").open(encoding="utf-8") as f:
        return sorted(normalise(c) for c in json.load(f))


def intent_counts(split: str) -> Counter:
    return Counter(r["intent"] for r in load_split(split))


if __name__ == "__main__":
    for s in ("train", "test"):
        c = intent_counts(s)
        print(s, sum(c.values()), "rows;", len(c), "intents; min", min(c.values()), "max", max(c.values()))
