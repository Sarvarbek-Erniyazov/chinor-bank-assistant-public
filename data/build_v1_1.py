"""SFT v1.1 = SFT v1 + repeats of the approved B1 and B1-dialogue training examples (ADR-028). CPU, no new text.

python data/build_v1_1.py
Asking-type assistant turns (contain "?", the B1 scorer's rule) are 2.5 % of SFT v1 train (results/negative_results.md).
Every B1 / B1-dialogue example in v1 TRAIN appears k times in v1.1 train; k is the integer that brings asking-type
turns closest to 10 % of all train examples. Val is v1 val unchanged, so no example is repeated across train / val.
Repeats get the id "<id>-rep<n>" (n = 2..k); train is shuffled with seed 20261029. Writes data/sft/v1.1/ (train,
val, assemble_stats.json, DATA_CARD.md, manifest.sha256).
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "data" / "sft" / "v1", ROOT / "data" / "sft" / "v1.1"
REPEAT = {"B1", "B1-dialogue"}
TARGET, SEED = 0.10, 20261029


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def asks(ex: dict) -> int:
    return sum("?" in m["content"] for m in ex["messages"] if m["role"] == "assistant")


def shares(train: list[dict]) -> dict:
    turns = sum(1 for ex in train for m in ex["messages"] if m["role"] == "assistant")
    k = sum(asks(ex) for ex in train)
    return {"examples": len(train), "assistant_turns": turns, "asking_turns": k,
            "asking_share_of_examples": round(k / len(train), 4), "asking_share_of_turns": round(k / turns, 4)}


def main():
    train, val = jsonl(SRC / "train.jsonl"), jsonl(SRC / "val.jsonl")
    rep = [ex for ex in train if ex["category"] in REPEAT]
    rest_ask = sum(asks(ex) for ex in train if ex["category"] not in REPEAT)
    rep_ask = sum(asks(ex) for ex in rep)
    n0 = len(train) - len(rep)
    k = min(range(1, 21), key=lambda k: abs((rest_ask + k * rep_ask) / (n0 + k * len(rep)) - TARGET))
    out = train + [dict(ex, id=f"{ex['id']}-rep{n}") for n in range(2, k + 1) for ex in rep]
    random.Random(SEED).shuffle(out)
    assert not {ex["id"] for ex in out} & {ex["id"] for ex in val}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in [("train.jsonl", out), ("val.jsonl", val)]:
        (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    stats = {"source": "data/sft/v1", "repeat_categories": sorted(REPEAT), "repeated_examples": len(rep),
             "factor": k, "target_asking_share_of_examples": TARGET, "seed": SEED,
             "v1_train": shares(train), "v1.1_train": shares(out), "val": shares(val),
             "by_category_train": dict(sorted(Counter(ex["category"] for ex in out).items()))}
    (OUT / "assemble_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8", newline="\n")
    a, b = stats["v1_train"], stats["v1.1_train"]
    (OUT / "DATA_CARD.md").write_text(f"""# SFT v1.1

SFT v1 (`data/sft/v1/DATA_CARD.md`, canonical answers, ADR-024) with the approved B1 and B1-dialogue training
examples repeated; no new text. Built by `data/build_v1_1.py` (ADR-028).

## Why: asking for a missing detail (B1)

Every trained arm passes 0–1 of the 20 B1 eval items. Only {a['asking_turns']} of {a['assistant_turns']} SFT v1 train
assistant turns ({100 * a['asking_share_of_turns']:.1f} %) ask a question (`results/negative_results.md`). v1.1 raises
that share by repetition to test whether data balance, not capacity, is the cause.

## Construction

- Repeated: the {len(rep)} train examples of categories B1 ({stats['by_category_train']['B1'] // k}) and B1-dialogue
  ({stats['by_category_train']['B1-dialogue'] // k}); each appears **{k}×** in train (ids `<id>-rep2` … `-rep{k}`).
  Factor rule: the integer that brings asking-type turns closest to {100 * TARGET:.0f} % of all train examples.
- Val: SFT v1 val unchanged (its 2 B1 and 2 B1-dialogue examples are not repeated); no example in both splits.
- Train shuffled with seed {SEED}.

| | v1 train | v1.1 train |
|---|---|---|
| Examples | {a['examples']:,} | {b['examples']:,} |
| Assistant turns | {a['assistant_turns']:,} | {b['assistant_turns']:,} |
| Asking-type turns (contain "?") | {a['asking_turns']} | {b['asking_turns']} |
| … share of examples | {100 * a['asking_share_of_examples']:.1f} % | {100 * b['asking_share_of_examples']:.1f} % |
| … share of assistant turns | {100 * a['asking_share_of_turns']:.1f} % | {100 * b['asking_share_of_turns']:.1f} % |

Risk watched: more asking turns may make the model ask instead of answer on clear requests (over-asking /
over-refusal on the T blocks).
""", encoding="utf-8", newline="\n")
    files = ["DATA_CARD.md", "assemble_stats.json", "train.jsonl", "val.jsonl"]
    (OUT / "manifest.sha256").write_text("".join(f"{hashlib.sha256((OUT / f).read_bytes()).hexdigest()}  {f}\n" for f in files),
                                         encoding="utf-8", newline="\n")
    print(json.dumps({k_: stats[k_] for k_ in ("factor", "v1_train", "v1.1_train")}, indent=1))


if __name__ == "__main__":
    main()
