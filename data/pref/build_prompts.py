"""Preference stage §1: prompts for on-policy sampling (C4). CPU.

python data/pref/build_prompts.py
Task prompts: Banking77 TRAIN queries of the 67 non-held-out intents that SFT v1 did NOT select
(data/sft/v1/task_prompts.jsonl), after the SFT filters (data/build_sft.py stage_select: held-out intents out, eval-v1
exact / fuzzy >= 90 out, duplicates out) plus the same filter against the frozen red-team set; 30 per intent,
length-stratified (build_sft.stratified_sample), seed 20261029. Intents with fewer than 30 unused queries left after SFT's
40 contribute all of them (reported as short_intents).
Behaviour prompts: the 160 approved SFT behaviour items (data/sft/v1/behaviour_examples.jsonl) and the 60 approved
handoff items (data/drafts/handoff_candidates.md), user turns only: the conversation up to its last user turn (the
B1 dialogues keep their first exchange). The SFT reply is kept as `reference` (the judge's reference text, §4); it
is never a chosen response.
Writes data/pref/v1/prompts.jsonl (id, source, category, intent, messages, reference) and prints the counts.
Refuses to run without the tag redteam-v1.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))
sys.path.insert(0, str(ROOT / "eval"))
import banking77 as b77  # noqa: E402
from build_eval import HELD_OUT  # noqa: E402
from build_sft import eval_queries, stratified_sample  # noqa: E402
from check_handoff import parse as parse_handoff  # noqa: E402
from contamination import norm  # noqa: E402

SEED = 20261029
PER_INTENT = 30
OUT = ROOT / "data" / "pref" / "v1"
REDTEAM = ROOT / "eval" / "redteam_set.jsonl"


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def require_tag(tag: str = "redteam-v1") -> None:
    if subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=ROOT, capture_output=True).returncode:
        sys.exit(f"refusing: tag {tag} is missing (the red-team set must be frozen before any preference data)")


def protected_texts() -> list[str]:
    """Normalised user texts of eval-v1 and the frozen red-team set: none may enter a preference prompt."""
    rt = [m["content"] for it in jsonl(REDTEAM) if not it.get("_meta") for m in it["messages"] if m["role"] == "user"]
    return [norm(q) for q in eval_queries() + rt]


def task_prompts(rng: random.Random, prot: list[str]) -> tuple[list[dict], dict]:
    prot_set = set(prot)
    sft = {norm(r["query"]) for r in jsonl(ROOT / "data" / "sft" / "v1" / "task_prompts.jsonl")}
    by_intent: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    stats = Counter()
    all_intents = set()
    for r in b77.load_split("train"):
        stats["train_rows"] += 1
        all_intents.add(r["intent"])
        qn = norm(r["text"])
        if r["intent"] in HELD_OUT:
            stats["held_out"] += 1
        elif qn in sft:
            stats["selected_for_sft"] += 1
        elif qn in prot_set:
            stats["eval_or_redteam_exact"] += 1
        elif process.extractOne(qn, prot, scorer=fuzz.ratio, score_cutoff=90) is not None:
            stats["eval_or_redteam_fuzzy"] += 1
        elif qn in seen:
            stats["duplicate"] += 1
        else:
            seen.add(qn)
            by_intent[r["intent"]].append(r["text"].strip())
    rows = []
    for intent in sorted(by_intent):
        for q in stratified_sample(rng, by_intent[intent], PER_INTENT):
            rows.append({"id": f"pt-{len(rows) + 1:04d}", "source": "banking77_train", "category": "task", "intent": intent,
                         "messages": [{"role": "user", "content": q}], "reference": None})
    # SFT took 40 per intent; intents with fewer than 30 unused queries contribute what is left (possibly none)
    n = Counter(r["intent"] for r in rows)
    intents = sorted({i for i in all_intents if i not in HELD_OUT})
    stats["short_intents"] = {i: n[i] for i in intents if n[i] < PER_INTENT}
    stats["intents_with_prompts"] = len(n)
    return rows, dict(stats)


def behaviour_prompts() -> list[dict]:
    rows = []
    for ex in jsonl(ROOT / "data" / "sft" / "v1" / "behaviour_examples.jsonl"):
        last = max(i for i, t in enumerate(ex["turns"]) if t["role"] == "user")
        rows.append({"id": f"pb-{ex['id'][4:]}", "source": "behaviour_sft", "category": ex["category"], "intent": ex["intent"],
                     "messages": ex["turns"][:last + 1], "reference": ex["turns"][last + 1]["content"]})
    for it in parse_handoff():
        rows.append({"id": f"pb-{it['id']}", "source": "handoff", "category": "handoff", "intent": it["topic"],
                     "messages": [{"role": "user", "content": it["user"]}], "reference": it["reply"]})
    return rows


def main():
    require_tag()
    prot = protected_texts()
    tasks, stats = task_prompts(random.Random(SEED), prot)
    beh = behaviour_prompts()
    rows = tasks + beh
    # final contamination check on every user turn (exact 0, fuzzy >= 90 0)
    prot_set = set(prot)
    bad = [r["id"] for r in rows for m in r["messages"] if m["role"] == "user" and
           (norm(m["content"]) in prot_set or process.extractOne(norm(m["content"]), prot, scorer=fuzz.ratio, score_cutoff=90))]
    assert not bad, f"contaminated prompts: {bad}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prompts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    print(json.dumps(stats))
    print(f"{len(rows)} prompts: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r["category"] for r in rows).items())))
    print("contamination vs eval-v1 + redteam-v1: exact 0, fuzzy >= 90 0")


if __name__ == "__main__":
    main()
