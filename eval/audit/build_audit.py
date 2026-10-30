"""Build the manual-audit sheet for one arm.

Usage: python eval/audit/build_audit.py --arm base-1.7B-0shot
Writes eval/audit/<arm>.csv: the 60 sampled items (in_sample=1) plus every other
item the scorer flagged as a hard violation (in_sample=0, used only for the
precision of the hard-violation flag). Fill manual_pass and
manual_hard_violation with 1/0.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
from score import clean_answer, hard_violation_sentences  # noqa: E402

AUDIT = ROOT / "eval" / "audit"
FIELDS = ["id", "block", "in_sample", "user_message", "answer", "auto_pass", "auto_hard_violation",
          "hv_sentence", "reason", "manual_pass", "manual_hard_violation", "note"]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    args = ap.parse_args()
    out_dir = ROOT / "eval" / "outputs" / args.arm
    items = {r["id"]: r for r in jsonl(ROOT / "eval" / "eval_set.jsonl")}
    answers = {r["id"]: r for r in jsonl(out_dir / "answers.jsonl")}
    scores = {r["id"]: r for r in jsonl(out_dir / "scores.jsonl")}
    sample = json.loads((AUDIT / "audit_sample_ids.json").read_text(encoding="utf-8"))["ids"]
    extra = [i for i in sorted(scores) if scores[i]["flags"]["hard_violation"] and i not in sample]

    rows = []
    for i in sample + extra:
        it, sc = items[i], scores[i]
        text = clean_answer(answers[i]["raw"])
        user = [m["content"] for m in it["messages"] if m["role"] == "user"][-1]
        rows.append({
            "id": i, "block": it["block"], "in_sample": int(i in sample),
            "user_message": user, "answer": text,
            "auto_pass": int(sc["pass"]), "auto_hard_violation": int(sc["flags"]["hard_violation"]),
            "hv_sentence": " || ".join(hard_violation_sentences(text, user)) if sc["flags"]["hard_violation"] else "",
            "reason": sc["reason"], "manual_pass": "", "manual_hard_violation": "", "note": "",
        })
    path = AUDIT / f"{args.arm}.csv"
    # utf-8-sig so the sheet opens with the right encoding in Excel
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{path.relative_to(ROOT)}: {len(sample)} sampled + {len(extra)} extra hard-violation rows")


if __name__ == "__main__":
    main()
