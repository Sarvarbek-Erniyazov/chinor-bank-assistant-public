"""Checks for the SFT v1.2 handoff drafts (data/drafts/handoff_candidates.md); writes data/drafts/handoff_check.md.

python data/check_handoff.py
1. Contamination: each draft customer question vs every eval-v1 user turn and every user turn in the training data
   (SFT v1 train/val, v1_rewrite train/val, behaviour examples, task prompts). Normalised (eval/contamination.norm)
   exact matches must be 0; fuzzy matches (rapidfuzz ratio >= 90) must be 0.
2. Nearest intent: rapidfuzz ratio / 100 against every Banking77 train query; the intent of the most similar query is
   the item's nearest intent. Flag: nearest intent is one of the 10 held-out intents and similarity >= 0.60.
3. Reply rules: data/verify.py-style checks: no number other than the handoff hours 08:00 and 22:00; 15-120 words;
   mentions the in-app chat.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
sys.path.insert(0, str(ROOT / "eval"))
import banking77 as b77  # noqa: E402
from build_eval import HELD_OUT  # noqa: E402
from contamination import norm  # noqa: E402

DRAFT = ROOT / "data" / "drafts" / "handoff_candidates.md"
OUT = ROOT / "data" / "drafts" / "handoff_check.md"
FUZZY, NEAR = 90, 0.60


def parse() -> list[dict]:
    items = []
    for block in re.split(r"\n### ", DRAFT.read_text(encoding="utf-8"))[1:]:
        head, body = block.split("\n", 1)
        m = re.match(r"(ho-\d+) · topic: (\w+)", head)
        u = re.search(r"\*\*User:\*\* (.+?)\n\*\*Assistant:\*\* (.+?)(?:\n|$)", body, re.S)
        items.append({"id": m.group(1), "topic": m.group(2), "user": u.group(1).strip(), "reply": u.group(2).strip()})
    return items


def jsonl_users(p: Path) -> list[str]:
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if "messages" in r:
            out += [m["content"] for m in r["messages"] if m["role"] == "user"]
        elif "query" in r:
            out.append(r["query"])
    return out


def main():
    items = parse()
    evals = jsonl_users(ROOT / "eval" / "eval_set.jsonl")
    sft = ROOT / "data" / "sft"
    train = []
    for p in [sft / "v1" / "train.jsonl", sft / "v1" / "val.jsonl", sft / "v1_rewrite" / "train.jsonl", sft / "v1_rewrite" / "val.jsonl",
              sft / "v1" / "behaviour_examples.jsonl", sft / "v1" / "task_prompts.jsonl", sft / "v1" / "task_examples.jsonl"]:
        train += jsonl_users(p)
    corpora = {"eval-v1": [norm(t) for t in evals], "training data": [norm(t) for t in set(train)]}
    b77_rows = [(norm(r["text"]), r["intent"]) for r in b77.load_split("train")]
    rows, flags, fails = [], [], []
    for it in items:
        q = norm(it["user"])
        res = {"id": it["id"], "topic": it["topic"]}
        for name, corp in corpora.items():
            res[f"exact {name}"] = sum(q == c for c in corp)
            best = max(corp, key=lambda c: fuzz.ratio(q, c))
            res[f"fuzzy {name}"] = round(fuzz.ratio(q, best), 1)
        text, intent = max(b77_rows, key=lambda r: fuzz.ratio(q, r[0]))
        res["nearest intent"], res["sim"], res["nearest query"] = intent, round(fuzz.ratio(q, text) / 100, 2), text
        nums = sorted(set(re.findall(r"\d+(?:[:.,]\d+)*", it["reply"])) - {"08:00", "22:00", "08:00–22:00"})
        words = len(it["reply"].split())
        res["reply ok"] = not nums and 15 <= words <= 120 and "in-app chat" in it["reply"]
        if intent in HELD_OUT and res["sim"] >= NEAR:
            flags.append(it["id"])
        if res["exact eval-v1"] or res["exact training data"] or res["fuzzy eval-v1"] >= FUZZY or res["fuzzy training data"] >= FUZZY or not res["reply ok"]:
            fails.append(it["id"])
        rows.append(res)
    L = ["# Handoff draft checks", "", f"`data/check_handoff.py` on {len(items)} items. Contamination: exact (normalised) "
         f"and fuzzy (rapidfuzz ratio ≥ {FUZZY}) against {len(corpora['eval-v1'])} eval-v1 user turns and "
         f"{len(corpora['training data'])} distinct training user turns. Nearest intent: most similar Banking77 train query; "
         f"flag = held-out intent with similarity ≥ {NEAR:.2f}.", "",
         f"- Exact matches: eval-v1 {sum(r['exact eval-v1'] for r in rows)}, training {sum(r['exact training data'] for r in rows)}.",
         f"- Fuzzy ≥ {FUZZY}: eval-v1 {sum(r['fuzzy eval-v1'] >= FUZZY for r in rows)}, training {sum(r['fuzzy training data'] >= FUZZY for r in rows)} "
         f"(max {max(r['fuzzy eval-v1'] for r in rows)} / {max(r['fuzzy training data'] for r in rows)}).",
         f"- Held-out nearest-intent flags (sim ≥ {NEAR:.2f}): {', '.join(flags) or 'none'}.",
         f"- Items failing a hard check: {', '.join(fails) or 'none'}.", "",
         "| Id | Topic | Max fuzzy eval | Max fuzzy train | Nearest intent | Sim. | Held out | Reply ok |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['id']} | {r['topic']} | {r['fuzzy eval-v1']} | {r['fuzzy training data']} | `{r['nearest intent']}` | {r['sim']:.2f} | "
          f"{'**yes**' if r['nearest intent'] in HELD_OUT else ''} | {'yes' if r['reply ok'] else '**no**'} |" for r in rows]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L[:9]))
    held = [r for r in rows if r["nearest intent"] in HELD_OUT]
    print("held-out nearest (any sim):", [(r["id"], r["nearest intent"], r["sim"]) for r in held])
    print("top sims:", sorted(((r["sim"], r["id"], r["nearest intent"]) for r in rows), reverse=True)[:6])


if __name__ == "__main__":
    main()
