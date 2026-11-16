"""Diagnostic only, never the official score: cut an answer where the model's turn was meant to end.

LoRA arms without trainable special-token rows never emit <|im_end|> (docs/limitations.md): they end the turn with
a neighbouring under-trained token and invent further turns. The cut is at the first character outside Latin script
and common punctuation / arrows, or at an invented "\nuser\n" / "\nassistant\n" turn, after the official
stop-string cut (score.clean_answer). Used for the "score if cut at intended end" column (eval/results_tables.py)
and for eval/t_held_analysis.py.
"""
from __future__ import annotations

import re

from score import clean_answer

CUT = re.compile(r"[^\x00-ɏ -⃏←-⇿]|\n(?:user|assistant)\n")


def turn_text(raw: str) -> str:
    text = clean_answer(raw)
    m = CUT.search(text)
    return (text[:m.start()] if m else text).strip()
