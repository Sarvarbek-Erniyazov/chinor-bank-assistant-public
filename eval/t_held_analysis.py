"""results/t_held_analysis.md: what trained models answer on the 20 held-out-intent items (T-held).

python eval/t_held_analysis.py
Each T-held answer is put in one class, checked in this order:
  (a) near-verbatim canonical answer of a TRAINING intent: character similarity (difflib ratio, lower-cased,
      whitespace collapsed) to the nearest training intent's canonical answer >= 0.80;
  (b) handoff / "don't know": the scorer's handoff markers or decline cues, or an explicit "I don't know / not sure";
  (c) other.
The nearest training intent and its similarity are reported for every answer; the held-out intent's own canonical
answer similarity is reported alongside (it was never a training target).
Answers are first cut where the model's turn should have ended: LoRA-trained models never emit <|im_end|> (its
frozen lm_head row sits in a cluster of near-identical under-trained rows) and run on with a stand-in token and
invented turns; the cut is at the first character outside Latin script / punctuation or at an invented
"\\nuser\\n" / "\\nassistant\\n" turn (CUT). The official scores (eval/score.py) are not cut.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from build_eval import HELD_OUT  # noqa: E402
from score import HANDOFF, declines  # noqa: E402
from turn_cut import turn_text  # noqa: E402

THRESHOLD = 0.80
# fixed arms (trainable special-token rows, ADR-023 amendment) when they exist, else the runs without the rows
FIXED = [f"tier_s_main_rslora_tok-s{s}" for s in range(3)] + [f"l14b_sft_rslora_tok-s{s}" for s in range(3)]
OLD = [f"tier_s_main_rslora-s{s}" for s in range(3)] + [f"l14b_sft_rslora-s{s}" for s in range(3)]
ARMS = [a for a in FIXED if (ROOT / "eval" / "outputs" / a / "answers.jsonl").exists()] or OLD
DONT_KNOW = re.compile(r"\b(i (?:do not|don't) know|not sure|i (?:do not|don't) have (?:that|this|the) information|"
                       r"unable to (?:answer|help)|can(?:no|')t (?:answer|help))", re.I)
def norm(t: str) -> str:
    return " ".join(t.lower().split())


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_intents() -> tuple[dict[str, str], dict[str, str]]:
    intents = {k: v["canonical_answer"] for k, v in yaml.safe_load((ROOT / "handbook" / "intents.yaml").read_text(encoding="utf-8")).items()}
    return intents, {k: v for k, v in intents.items() if k not in HELD_OUT}


def classify(arm: str) -> list[dict]:
    """The 20 T-held answers of one arm, each with its class (a/b/c), nearest training intent and similarities."""
    intents, train_intents = load_intents()
    items = [it for it in jsonl(ROOT / "eval" / "eval_set.jsonl") if it["block"] == "T-held"]
    ans = {r["id"]: turn_text(r["raw"]) for r in jsonl(ROOT / "eval" / "outputs" / arm / "answers.jsonl")}
    out = []
    for it in items:
        text = ans[it["id"]]
        near, s = max(((k, sim(text, v)) for k, v in train_intents.items()), key=lambda x: x[1])
        own = sim(text, intents[it["intent"]]) if it["intent"] in intents else float("nan")
        if s >= THRESHOLD:
            cls = "a"
        elif HANDOFF.search(text) or declines(text) or DONT_KNOW.search(text):
            cls = "b"
        else:
            cls = "c"
        out.append({"id": it["id"], "intent": it["intent"], "cls": cls, "near": near, "sim": s, "own": own, "text": text,
                    "user": [m["content"] for m in it["messages"] if m["role"] == "user"][-1]})
    return out


def main():
    _, train_intents = load_intents()
    rows, examples = {arm: classify(arm) for arm in ARMS}, []
    pool = [dict(r, arm=arm) for arm in reversed(ARMS) for r in rows[arm] if r["cls"] == "a"]
    seen = set()
    for r in sorted(pool, key=lambda r: -r["sim"]):
        if r["id"] not in seen and len(examples) < 3:
            seen.add(r["id"]); examples.append(r)

    L = ["# T-held diagnosis: answers on the 10 held-out intents (20 items)", "",
         "`eval/t_held_analysis.py`. Classes, checked in order: **(a)** near-verbatim canonical answer of a training "
         f"intent (difflib ratio ≥ {THRESHOLD:.2f} to the nearest training intent's canonical answer); **(b)** handoff or "
         "\"don't know\" (scorer handoff markers, decline cues, explicit don't-know); **(c)** other. Training data: SFT v1, "
         "canonical answers only (ADR-024).", "",
         "| Arm | (a) training-intent answer | (b) handoff / don't know | (c) other | T-held pass | median sim. to nearest training intent | median sim. to own (held-out) canonical |",
         "|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        c = Counter(r["cls"] for r in rows[arm])
        sc = {r["id"]: r["pass"] for r in jsonl(ROOT / "eval" / "outputs" / arm / "scores.jsonl")}
        sims = sorted(r["sim"] for r in rows[arm]); owns = sorted(r["own"] for r in rows[arm])
        L.append(f"| `{arm}` | {c['a']} | {c['b']} | {c['c']} | {sum(sc[r['id']] for r in rows[arm])} / 20 | "
                 f"{(sims[9] + sims[10]) / 2:.2f} | {(owns[9] + owns[10]) / 2:.2f} |")
    L += ["", "## Examples of (a)", ""]
    for r in examples:
        L += [f"- **{r['id']}** (`{r['arm']}`), held-out intent `{r['intent']}`; nearest training intent "
              f"`{r['near']}`, similarity {r['sim']:.2f}.", f"  - User: {r['user']}", f"  - Answer: {r['text']}",
              f"  - Canonical answer of `{r['near']}`: {train_intents[r['near']]}", ""]
    L += ["## Per item (14B, first seed)", "", "| Id | Held-out intent | Class | Nearest training intent | Sim. |", "|---|---|---|---|---|"]
    L += [f"| {r['id']} | `{r['intent']}` | {r['cls']} | `{r['near']}` | {r['sim']:.2f} |" for r in rows[[a for a in ARMS if a.startswith("l14b")][0]]]
    out = ROOT / "results" / "t_held_analysis.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
