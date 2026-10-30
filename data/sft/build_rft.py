"""SFT v1.2_rft (ADR-033, exploratory): SFT v1.2 plus one verified on-policy sample per preference prompt.

python data/sft/build_rft.py      -> data/sft/v1.2_rft/{train.jsonl, val.jsonl, DATA_CARD.md, manifest.sha256}
Added rows: the chosen response of every pair in data/pref/v1/pairs_rules.jsonl (a sample of sft-merged that passed
every rule, the one the DPO / SimPO runs used), as a system + conversation + assistant example with the frozen
system prompt. Contamination check before writing: every user turn and every added response against eval-v1 and
redteam-v1 user turns, exact (normalised) 0 and rapidfuzz ratio >= 90 0, else the script stops. val.jsonl is
v1.2's, unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[2]
SRC, DST = ROOT / "data" / "sft" / "v1.2", ROOT / "data" / "sft" / "v1.2_rft"
PAIRS = ROOT / "data" / "pref" / "v1" / "pairs_rules.jsonl"


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip()


def main():
    system = (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()
    train = jsonl(SRC / "train.jsonl")
    assert train[0]["messages"][0]["content"].strip() == system
    pairs = jsonl(PAIRS)
    added = [{"id": f"rft-{p['id']}", "source": "rft_on_policy", "category": p["category"], "intent": p["intent"],
              "candidate_index": None, "messages": [{"role": "system", "content": system}] + p["messages"]
              + [{"role": "assistant", "content": p["chosen"]}]} for p in pairs]
    evals = [m["content"] for f in ("eval_set.jsonl", "redteam_set.jsonl") for it in jsonl(ROOT / "eval" / f) if not it.get("_meta")
             for m in it["messages"] if m["role"] == "user"]
    ev_norm = [norm(e) for e in evals]
    ev_set = set(ev_norm)
    texts = [m["content"] for r in added for m in r["messages"][1:]]
    exact = sum(norm(t) in ev_set for t in texts)
    fuzzy = sum(process.extractOne(norm(t), ev_norm, scorer=fuzz.ratio, score_cutoff=90) is not None for t in texts)
    if exact or fuzzy:
        sys.exit(f"contamination: exact {exact}, fuzzy >= 90 {fuzzy}; nothing written")
    DST.mkdir(parents=True, exist_ok=True)
    rows = train + added
    (DST / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    (DST / "val.jsonl").write_bytes((SRC / "val.jsonl").read_bytes())
    card = (f"# SFT data v1.2_rft (ADR-033, exploratory)\n\n`data/sft/build_rft.py`. SFT v1.2 ({len(train):,} train rows, "
            f"`data/sft/v1.2`) plus {len(added):,} on-policy rows: the chosen responses of `data/pref/v1/pairs_rules.jsonl` "
            f"(samples of sft-merged that passed every rule; {sum(r['category'] == 'task' for r in added)} task, "
            f"{sum(r['category'] != 'task' for r in added)} behaviour / handoff). Train rows: {len(rows):,}; val: v1.2's "
            f"({len(jsonl(SRC / 'val.jsonl'))} rows, unchanged).\n\nContamination of the added user turns and responses vs "
            f"eval-v1 and redteam-v1 user turns ({len(evals)}): exact 0, rapidfuzz ratio >= 90 0.\n")
    (DST / "DATA_CARD.md").write_text(card, encoding="utf-8", newline="\n")
    man = "".join(f"{hashlib.sha256((DST / n).read_bytes()).hexdigest()}  {n}\n" for n in ("DATA_CARD.md", "train.jsonl", "val.jsonl"))
    (DST / "manifest.sha256").write_text(man, encoding="utf-8", newline="\n")
    print(card)


if __name__ == "__main__":
    main()
