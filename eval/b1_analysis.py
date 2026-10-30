"""results/b1_analysis.md: what the trained 14B models do on the 20 B1 items (CPU; the frozen B1 rule is unchanged).

python eval/b1_analysis.py
B1 items leave out one detail (the "slot"); the rule passes an answer that asks a question naming the slot.
Here every B1 answer of 14B SFT rsLoRA v1 and v1.1 (seeds 0-2) and 14B full FT (seeds 0-1) is classified:
  (a) covers all branches: for every value of the missing slot, that branch's handbook facts are present
  (b) some branches: the facts of at least one branch, not all, and no question (assumes a value or misses one)
  (c) asks a question but fails the rule (reason: slot keyword absent, more than one question, ...)
  (d) other (no branch's facts, no question: generic answer, wrong topic, refusal)
  plus "asks (pass)": asks a question naming the slot, i.e. passes the frozen rule.
Branch facts (BRANCHES) are taken from handbook/handbook.md §2-§6 and checked as case-insensitive regexes, all of
which must match for a branch to count. Each item is also marked: covering every branch is possible / partly
possible (the rules can be stated, the customer's own case cannot be resolved without the detail) / not possible.
Ambiguous answers (a branch whose facts match only in part; or class (a) on a "partly" item) are listed for the
author to confirm.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from score import clean_answer
from stats import load_scores

ROOT = Path(__file__).resolve().parents[1]
ARMS = {"14B rsLoRA v1": [f"l14b_sft_rslora_tok-s{s}" for s in range(3)],
        "14B rsLoRA v1.1": [f"l14b_sft_rslora_tok-s{s}-v1.1" for s in range(3)],
        "14B full FT (lr 1e-5)": [f"l14b_full-s{s}" for s in range(2)]}
# item: (coverage possible?, {branch: [regex, ...]})
BRANCHES = {
    "B1-001": ("possible", {"domestic": [r"2,500\b|20 (free )?(domestic )?transfers|free up to 20"], "international / SWIFT": [r"0\.8 ?%", r"60,000"]}),
    "B1-002": ("possible", {"standard": [r"7 business days"], "express": [r"2 business days", r"45,000"]}),
    "B1-003": ("possible", {"Standard": [r"standard", r"\b(1|one) virtual"], "Plus": [r"plus", r"\b(5|five)\b"]}),
    "B1-004": ("possible", {"Standard": [r"2,500,000"], "Plus": [r"6,000,000"]}),
    "B1-005": ("partly", {"Chinor to Chinor": [r"instant"], "other Uzbek bank": [r"16:30"], "international": [r"2.4 business days"]}),
    "B1-006": ("possible", {"first this year": [r"first", r"free"], "already replaced": [r"35,000"]}),
    "B1-007": ("possible", {"card payment": [r"9 business days"], "ATM withdrawal": [r"4 business days"], "top-up": [r"top-?up"]}),
    "B1-008": ("possible", {"domestic": [r"scheduled"], "SWIFT": [r"24 hours", r"90,000"]}),
    "B1-009": ("not possible", {"payment context": [r"balance|frozen|limit|3-?d secure|fraud"]}),
    "B1-010": ("possible", {"Standard": [r"15,000,000", r"0\.6 ?%"], "Plus": [r"unlimited"], "weekend": [r"0\.9 ?%"]}),
    "B1-011": ("possible", {"weekend": [r"0\.9 ?%"], "above allowance": [r"0\.6 ?%"], "merchant category": [r"0\.5 ?%"]}),
    "B1-012": ("possible", {"debit card / bank transfer / cash": [r"free"], "credit card": [r"1\.1 ?%"]}),
    "B1-013": ("partly", {"card": [r"instant|2 business days"], "bank transfer": [r"1 business day"], "cash": [r"immediately|same business day"]}),
    "B1-014": ("possible", {"physical": [r"35,000|spare|2 physical|two physical"], "virtual": [r"virtual"]}),
    "B1-015": ("possible", {"daily spending": [r"25,000,000"], "contactless": [r"900,000"], "ATM": [r"6,000,000"], "disposable": [r"3,000,000"]}),
    "B1-016": ("possible", {"age": [r"\b16\b"], "country": [r"\b12\b|supported countr"]}),
    "B1-017": ("possible", {"identity": [r"2 hours|1 business day"], "source of funds": [r"10 days"]}),
    "B1-018": ("partly", {"card payment / ATM": [r"60 days"], "wrong cash at ATM": [r"48 hours"], "merchant refund": [r"15 days|merchant first"]}),
    "B1-019": ("possible", {"collection date": [r"1 business day"]}),
    "B1-020": ("possible", {"daily": [r"6,000,000"], "monthly free (Standard)": [r"2,500,000"]}),
}
CLASSES = ["asks (pass)", "a", "b", "c", "d"]
NAMES = {"asks (pass)": "asks the right question (passes the rule)", "a": "(a) covers all branches", "b": "(b) some branches, not all",
         "c": "(c) asks but fails the rule", "d": "(d) other"}


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def branch_hits(item: str, text: str) -> dict[str, tuple[int, int]]:
    return {b: (sum(bool(re.search(p, text, re.I)) for p in pats), len(pats)) for b, pats in BRANCHES[item][1].items()}


def classify(item: str, text: str, score: dict) -> tuple[str, str, dict]:
    hits = branch_hits(item, text)
    full = [b for b, (k, n) in hits.items() if k == n]
    q = text.count("?")
    if score["pass"]:
        return "asks (pass)", "", hits
    if len(full) == len(hits):
        return "a", "", hits
    if q:
        why = "; ".join(r for r in [score["reason"], "more than one question" if q > 1 else ""] if r)
        return "c", why, hits
    if full:
        return "b", "covers: " + ", ".join(full), hits
    return "d", score["reason"], hits


def main():
    items = {it["id"]: it for it in jsonl(ROOT / "eval" / "eval_set.jsonl") if it["block"] == "B1"}
    counts, examples, ambiguous = {}, defaultdict(list), []
    for arm, runs in ARMS.items():
        c = Counter()
        for run in runs:
            p = ROOT / "eval" / "outputs" / run / "answers.jsonl"
            if not p.exists():
                continue
            sc = load_scores(run)
            ans = {a["id"]: clean_answer(a["raw"]) for a in jsonl(p) if a["id"] in items}
            for i, text in sorted(ans.items()):
                cls, why, hits = classify(i, text, sc[i])
                c[cls] += 1
                rec = {"arm": arm, "run": run, "id": i, "text": text, "why": why}
                if len(examples[cls]) < 3 and all(e["id"] != i for e in examples[cls]):
                    examples[cls].append(rec)
                partial = [b for b, (k, n) in hits.items() if 0 < k < n]
                if partial or (cls == "a" and BRANCHES[i][0] != "possible"):
                    ambiguous.append(dict(rec, cls=cls, note=("partial facts for: " + ", ".join(partial)) if partial
                                          else f"class (a) on a '{BRANCHES[i][0]}' item"))
        counts[arm] = (c, sum(c.values()))
    with (ROOT / "results" / "tidy" / "b1_classes.csv").open("w", encoding="utf-8", newline="") as f:  # for F15
        f.write("arm,class,count,n\n" + "".join(f"{arm},{k},{c[k]},{n}\n" for arm, (c, n) in counts.items() for k in sorted(c)))
    L = ["# B1 diagnosis: what the 14B models answer when a detail is missing", "",
         "`eval/b1_analysis.py` (CPU). The frozen B1 rule is unchanged: pass = the answer asks a question that names "
         "the missing slot. Classes, checked in order: *asks (pass)*; **(a)** covers every branch of the missing slot "
         "(all of each branch's handbook facts present); **(c)** asks a question but fails the rule; **(b)** covers "
         "some branches but not all, no question; **(d)** other. Branch facts are regexes from the handbook (`BRANCHES` in the "
         "script) — a hand-made mapping, listed below for checking.", "",
         "| Arm | Answers | " + " | ".join(NAMES[c] for c in CLASSES) + " |", "|---|---|" + "---|" * len(CLASSES)]
    for arm, (c, n) in counts.items():
        L.append(f"| {arm} | {n} | " + " | ".join(f"{c[k]} ({100 * c[k] / n:.0f} %)" if n else "—" for k in CLASSES) + " |")
    L += ["", "## Can an answer cover every branch? (per item)", "",
          "| Item | Question | Slot keyword (rule) | Branches (handbook facts) | Covering all branches |", "|---|---|---|---|---|"]
    for i, it in items.items():
        poss, br = BRANCHES[i]
        L.append(f"| {i} | {it['messages'][-1]['content']} | {it['slot_keyword'].replace('|', ' / ')} | "
                 + "; ".join(f"{b}: `{' & '.join(p)}`".replace("|", "\\|") for b, p in br.items()) + f" | {poss} |")
    L += ["", "*possible*: general handbook rules answer every branch. *partly*: the rules for each branch can be "
          "stated, but the customer's own case (why it has not arrived, which transaction) cannot be resolved without "
          "the detail. *not possible*: the answer depends on facts the assistant cannot see (the decline reason).", ""]
    L += ["## Examples (up to 3 per class, different items)", ""]
    for c in CLASSES:
        L += [f"### {NAMES[c]}", ""]
        for e in examples[c]:
            L.append(f"- **{e['id']}** (`{e['run']}`){': ' + e['why'] if e['why'] else ''}. User: “{items[e['id']]['messages'][-1]['content']}” "
                     f"Answer: “{e['text']}”".replace("\n", " "))
        L.append("")
    L += ["## Ambiguous cases for the author to confirm", "",
          f"{len(ambiguous)} answers: a branch's facts match only in part, or class (a) on an item where full coverage "
          "is only partly possible.", "", "| Item | Run | Class given | Why ambiguous | Answer |", "|---|---|---|---|---|"]
    L += [f"| {a['id']} | `{a['run']}` | {a['cls']} | {a['note']} | {a['text'][:220]}{'…' if len(a['text']) > 220 else ''} |".replace("\n", " ")
          for a in ambiguous]
    (ROOT / "results" / "b1_analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L[:12]))
    print(f"ambiguous: {len(ambiguous)}")


if __name__ == "__main__":
    main()
