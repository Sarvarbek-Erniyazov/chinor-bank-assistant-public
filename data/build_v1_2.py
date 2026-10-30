"""SFT v1.2 = SFT v1.1 + the 60 approved handoff examples (data/drafts/handoff_candidates.md; ADR-029). CPU.

python data/build_v1_2.py
Each handoff item becomes a one-turn example (system prompt as in v1, user, assistant), category "handoff".
Split: the v1 rule (data/build_sft.py: VAL_SHARE 0.05 per stratum, at least 1) gives 3 val items; they are taken one
each from 3 different topics (topics shuffled with seed 20261029), so no topic is split and no item is in both
splits. Train = v1.1 train + 57, shuffled with seed 20261029; val = v1.1 val + 3.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from check_handoff import parse  # noqa: E402

SRC, OUT = ROOT / "data" / "sft" / "v1.1", ROOT / "data" / "sft" / "v1.2"
SYSTEM = (ROOT / "handbook" / "system_prompt.txt").read_text(encoding="utf-8").strip()
VAL_SHARE, SEED = 0.05, 20261029


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    train, val = jsonl(SRC / "train.jsonl"), jsonl(SRC / "val.jsonl")
    assert train[0]["messages"][0]["content"] == SYSTEM, "system prompt differs from v1"
    items = parse()
    ex = [{"id": f"sft-{it['id']}", "source": "handoff", "category": "handoff", "intent": None, "topic": it["topic"],
           "candidate_index": None, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": it["user"]},
                                                 {"role": "assistant", "content": it["reply"]}]} for it in items]
    by_topic = defaultdict(list)
    for e in ex:
        by_topic[e["topic"]].append(e)
    rng = random.Random(SEED)
    topics = sorted(by_topic)
    rng.shuffle(topics)
    n_val = max(1, round(VAL_SHARE * len(ex)))
    val_ids = {by_topic[t][0]["id"] for t in topics[:n_val]}
    h_train = [e for e in ex if e["id"] not in val_ids]
    h_val = [e for e in ex if e["id"] in val_ids]
    out_train, out_val = train + h_train, val + h_val
    rng.shuffle(out_train)
    ids_t, ids_v = [e["id"] for e in out_train], [e["id"] for e in out_val]
    assert not set(ids_t) & set(ids_v)
    norm = lambda e: " ".join(e["messages"][1]["content"].lower().split())
    assert not {norm(e) for e in h_train} & {norm(e) for e in h_val}, "duplicate handoff text across splits"
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in [("train.jsonl", out_train), ("val.jsonl", out_val)]:
        (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    stats = {"source": "data/sft/v1.1 + data/drafts/handoff_candidates.md", "seed": SEED, "handoff_items": len(ex),
             "handoff_train": len(h_train), "handoff_val": len(h_val), "val_topics": sorted(e["topic"] for e in h_val),
             "train": len(out_train), "val": len(out_val),
             "by_category_train": dict(sorted(Counter(e["category"] for e in out_train).items())),
             "handoff_share_of_train": round(len(h_train) / len(out_train), 4)}
    (OUT / "assemble_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8", newline="\n")
    (OUT / "DATA_CARD.md").write_text(f"""# SFT v1.2

SFT v1.1 (`data/sft/v1.1/DATA_CARD.md`: v1 with B1 / B1-dialogue repeated 4×) plus 60 hand-written handoff examples
(`data/drafts/handoff_candidates.md`, approved by the author 2026-10-29). Built by `data/build_v1_2.py` (ADR-029).

## Why: unknown topics (T-held)

On the 10 held-out intents trained models answer with a memorised answer of a different, trained intent (78–90 %
of T-held answers; `results/t_held_analysis.md`) instead of saying they do not know. SFT v1 has no example of the
assistant declining a banking question it has no information on. v1.2 adds such examples.

## Handoff examples

- 60 customer questions on 15 banking topics that are neither Banking77 labels nor covered by the handbook (safe-deposit
  boxes, joint accounts, standing orders, business accounts, payroll, insurance, gift cards, power of attorney,
  bereavement, reference letters, merchant terminals, rewards, pensions, escrow, damaged banknotes), 4 each.
- Each reply says the assistant cannot answer from what it knows and hands off to a human agent in the in-app chat
  (daily 08:00–22:00); no facts, no other numbers, no claim that the product does or does not exist.
- Checks (`data/check_handoff.py`, `data/drafts/handoff_check.md`): 0 exact and 0 fuzzy (ratio ≥ 0.90) matches
  against eval-v1 and all training user turns; every reply passes the number / length / handoff checks.
- **Nearest-intent flags (lexical overlap only).** Three questions have a held-out Banking77 intent as their nearest
  intent at character similarity ≥ 0.60. The overlap is in wording only, not topic; the author kept them as written:
  - ho-001 (safe-deposit box): `request_refund`, 0.62 ("can i have a refund for one of your products");
  - ho-036 (bereavement / inheriting an account): `visa_or_mastercard`, 0.66 ("can i get a visa or does it have to be
    something else");
  - ho-045 (rewards / cashback): `card_payment_fee_charged`, 0.60 ("i noticed an extra fee when i paid with my card").

## Split

v1 rule (5 % per stratum, at least 1): {len(h_val)} handoff items in val, one each from {', '.join(stats['val_topics'])};
{len(h_train)} in train. Topics are not split across train / val beyond those {len(h_val)} items; no text is in both
splits. v1.1 train / val are carried over unchanged. Train shuffled with seed {SEED}.

| | v1.1 | v1.2 |
|---|---|---|
| Train examples | {len(train):,} | {len(out_train):,} |
| Val examples | {len(val):,} | {len(out_val):,} |
| Handoff examples in train | 0 | {len(h_train)} ({100 * stats['handoff_share_of_train']:.1f} %) |

Risks watched: over-refusal on clear in-scope questions (T-seen) and on B2; handoffs replacing correct answers.
""", encoding="utf-8", newline="\n")
    files = ["DATA_CARD.md", "assemble_stats.json", "train.jsonl", "val.jsonl"]
    (OUT / "manifest.sha256").write_text("".join(f"{hashlib.sha256((OUT / f).read_bytes()).hexdigest()}  {f}\n" for f in files),
                                         encoding="utf-8", newline="\n")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
