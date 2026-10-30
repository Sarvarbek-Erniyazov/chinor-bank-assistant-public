"""results/negative_results.md: diagnostics behind the results that did not work (CPU only).

python eval/negative_results.py
(a) B1 tail attribution. The LoRA runs without trainable special-token rows never emit <|im_end|> and run on with
    invented turns (docs/limitations.md). Each B1 item of those runs is rescored on the answer cut at the intended
    turn end (eval/turn_cut.py) and put in one class: survives (passes official and cut), tail-only (passes only
    because of text after the intended end), cut-only (fails official, passes cut). The fixed counterparts
    (trainable special-token rows) are listed alongside.
(b) Data balance. Every assistant turn in SFT v1 train is either a question (contains "?", the same rule the B1
    scorer uses) or a resolving answer, counted per training category.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from score import Scorer
from stats import load_blocks, load_scores
from turn_cut import turn_text

ROOT = Path(__file__).resolve().parents[1]
OLD = {"1.7B rsLoRA (Tier-S main)": "tier_s_main_rslora", "14B rsLoRA lr 1e-4": "l14b_sft_rslora"}
FIXED = {"tier_s_main_rslora": "tier_s_main_rslora_tok", "l14b_sft_rslora": "l14b_sft_rslora_tok"}


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def b1_attribution(scorer: Scorer, blocks: dict[str, str]) -> tuple[list[str], list[dict]]:
    ids = [i for i, b in blocks.items() if b == "B1"]
    rows, examples = [], []
    for name, prefix in OLD.items():
        for s in range(3):
            run = f"{prefix}-s{s}"
            off = load_scores(run)
            ans = {a["id"]: a["raw"] for a in jsonl(ROOT / "eval" / "outputs" / run / "answers.jsonl")}
            c = Counter()
            for i in ids:
                cut = scorer.score(i, turn_text(ans[i]))["pass"]
                o = off[i]["pass"]
                c["official"] += o
                c["survive" if o and cut else "tail" if o else "cut_only" if cut else "neither"] += 1
                if o and not cut and len(examples) < 2 and prefix.startswith("l14b"):
                    examples.append({"run": run, "id": i, "cut": turn_text(ans[i]), "raw": ans[i]})
            fx = f"{FIXED[prefix]}-s{s}"
            fixed = sum(load_scores(fx)[i]["pass"] for i in ids) if (ROOT / "eval" / "outputs" / fx / "scores.jsonl").exists() else None
            rows.append(f"| {name} | {s} | {c['official']} | {c['survive']} | {c['tail']} | {c['cut_only']} | "
                        f"{'—' if fixed is None else fixed} |")
    return rows, examples


def balance() -> list[str]:
    per = Counter(); q = Counter()
    for ex in jsonl(ROOT / "data" / "sft" / "v1" / "train.jsonl"):
        for m in ex["messages"]:
            if m["role"] == "assistant":
                per[ex["category"]] += 1
                q[ex["category"]] += "?" in m["content"]
    rows = [f"| {c} | {per[c]} | {q[c]} | {per[c] - q[c]} | {100 * q[c] / per[c]:.1f} % |" for c in sorted(per)]
    n, k = sum(per.values()), sum(q.values())
    rows.append(f"| **all** | {n} | {k} | {n - k} | {100 * k / n:.1f} % |")
    return rows


def main():
    scorer, blocks = Scorer(), load_blocks()
    rows, ex = b1_attribution(scorer, blocks)
    L = ["# Negative results: diagnostics", "", "`eval/negative_results.py` (CPU). Official scores: rubric v1.3 "
         "(`eval/score.py`); the cut is a diagnostic only (`eval/turn_cut.py`).", "",
         "## (a) B1 tail attribution — LoRA runs without trainable special-token rows", "",
         "B1 = 20 under-specified requests; pass = the answer asks a question and names the missing slot. Each "
         "official B1 pass is rescored on the answer cut at the intended turn end. *Tail-only* = the pass came from "
         "text after the intended end (an invented later turn or a run-on).", "",
         "| Arm | Seed | Official B1 pass /20 | Survive the cut | Tail-only | Cut-only | Fixed counterpart B1 /20 |",
         "|---|---|---|---|---|---|---|"] + rows + [""]
    for e in ex:
        L += [f"- `{e['run']}` **{e['id']}**, answer up to the intended end: “{e['cut'][:300]}”; the question appears "
              f"only after it: “{e['raw'][len(e['cut']):][:300].strip()}…”".replace("\n", " ⏎ "), ""]
    L += ["## (b) Data balance — SFT v1 train, assistant turns", "",
          "Question = the turn contains \"?\" (the B1 scorer's rule); resolve = it does not.", "",
          "| Training category | Assistant turns | Ask a question | Resolve | Share asking |", "|---|---|---|---|---|"]
    L += balance() + [""]
    out = ROOT / "results" / "negative_results.md"
    out.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
