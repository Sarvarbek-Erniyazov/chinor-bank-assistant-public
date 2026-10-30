"""Check eval/system_prompt_paraphrase.txt against handbook/system_prompt.txt (robustness arm, plan 2026-10-29 step 5).

python eval/check_paraphrase.py
Every number (incl. phone number pieces, hours and ranges), channel name and hour of the original must appear
verbatim in the paraphrase; the paraphrase must not be identical; it must be <= 450 tokens (Qwen3 tokenizer).
Exit 1 on any failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIG = ROOT / "handbook" / "system_prompt.txt"
PARA = ROOT / "eval" / "system_prompt_paraphrase.txt"
CHANNELS = ["in-app human chat", "24-hour card line", "branches", "Chinor Loans team", "human agent"]
MAX_TOKENS = 450


def main() -> int:
    o, p = ORIG.read_text(encoding="utf-8").strip(), PARA.read_text(encoding="utf-8").strip()
    numbers = sorted(set(re.findall(r"\+?\d+(?:[:,.\-]\d+)*(?: \(\d+\) [\d-]+)?", o)))
    missing = [n for n in numbers if n not in p] + [c for c in CHANNELS if c in o and c not in p]
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B-Base", local_files_only=True)
    n_o, n_p = len(tok(o)["input_ids"]), len(tok(p)["input_ids"])
    print(f"numbers / hours checked: {len(numbers)} ({', '.join(numbers)})")
    print(f"channels checked: {', '.join(c for c in CHANNELS if c in o)}")
    print(f"tokens: original {n_o}, paraphrase {n_p} (max {MAX_TOKENS})")
    ok = not missing and n_p <= MAX_TOKENS and o != p
    print("missing: " + (", ".join(missing) or "none"))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
