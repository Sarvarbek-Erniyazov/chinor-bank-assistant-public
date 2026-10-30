"""Make an audit sheet blind: move the automatic verdict columns to a separate file.

python eval/audit/blind_split.py eval/audit/14b-lora-s0.csv
The sheet keeps id, block, user_message, answer and the manual columns (manual_pass, manual_hard_violation, note);
auto_pass, auto_hard_violation, hv_sentence, reason and in_sample (in_sample = 0 would reveal a scorer flag) go to
<sheet>.auto.csv, keyed by id. Refuses to run if any manual column is already filled (marks are never touched).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SHEET = ["id", "block", "user_message", "answer", "manual_pass", "manual_hard_violation", "note"]
AUTO = ["id", "in_sample", "auto_pass", "auto_hard_violation", "hv_sentence", "reason"]


def main(path: str) -> None:
    p = Path(path)
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if any(r.get(k, "").strip() for r in rows for k in ("manual_pass", "manual_hard_violation", "note")):
        sys.exit(f"refusing: {p} already has manual marks")
    auto = p.with_suffix(".auto.csv")
    for out, cols in [(auto, AUTO), (p, SHEET)]:
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    print(f"{p}: {len(rows)} rows, columns {', '.join(SHEET)}; verdicts -> {auto}")


if __name__ == "__main__":
    main(sys.argv[1])
