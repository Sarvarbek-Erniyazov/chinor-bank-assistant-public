"""results/full_ft_analysis.md: why 14B full FT (lr 1e-5, 3 epochs) scores below 14B LoRA. CPU only.

python eval/full_ft_analysis.py
(1) Final val loss (results/runs/<run>/train/run.json) next to Assistant /200 for 14B LoRA, QLoRA (seeds 0-2) and
    full FT (seeds 0-1). Val loss is on SFT v1 val (assistant tokens only); QLoRA's is computed on the NF4 base.
(2) Items failed by full FT (either seed) but passed by LoRA (at least 2 of 3 seeds). Each full-FT failure
    (item × seed) is put in the first class that applies:
      wrong-intent  answer is >= 0.80 similar (difflib, as eval/t_held_analysis.py) to the canonical answer of an
                    intent other than the item's own
      refusal       over-refusal flag, or the answer declines / hands off (eval/score.py cues) on a block where
                    declining is wrong (T-seen, T-held, B1, B4)
      number        fabricated-number flag
      missing fact  the scorer's "missing facts" reason
      other         anything else (the scorer's reason is shown)
"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from score import HANDOFF, clean_answer, declines
from stats import BLOCKS, in_group, load_blocks, load_scores
from t_held_analysis import load_intents, sim

ROOT = Path(__file__).resolve().parents[1]
ARMS = {"LoRA": ("l14b_sft_rslora_tok", 3), "QLoRA": ("l14b_qlora_rslora_tok", 3), "full FT": ("l14b_full", 2)}
THRESHOLD = 0.80
CLASSES = ["wrong-intent", "refusal", "number", "missing fact", "other"]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def classify(item: dict, text: str, score: dict, canon: dict[str, str]) -> tuple[str, str, float]:
    near, s = max(((k, sim(text, v)) for k, v in canon.items() if k != item.get("intent")), key=lambda x: x[1])
    if s >= THRESHOLD:
        return "wrong-intent", near, s
    # declining is the expected behaviour on B2 / B3, so it is a failure class only on the other blocks
    if score["flags"]["over_refusal"] or (item["block"] not in ("B2", "B3") and (declines(text) or HANDOFF.search(text))):
        return "refusal", near, s
    if score["flags"]["fabricated_number"]:
        return "number", near, s
    if "missing facts" in score["reason"]:
        return "missing fact", near, s
    return "other", near, s


def main():
    blocks = load_blocks()
    items = {it["id"]: it for it in jsonl(ROOT / "eval" / "eval_set.jsonl")}
    canon, _ = load_intents()
    asst = [i for i in blocks if in_group("assistant", blocks[i])]
    L = ["# 14B full fine-tuning: what goes wrong", "", "`eval/full_ft_analysis.py`. Protocol A, rubric v1.3, SFT v1. Full FT "
         "settings: lr 1e-5, 3 epochs (`train/configs/l14b_full.yaml`); LoRA / QLoRA: rsLoRA r 16, lr 1e-4, 3 epochs.", "",
         "## (1) Final val loss vs score", "", "| Arm | Seed | Final val loss | Final train loss | Assistant /200 |", "|---|---|---|---|---|"]
    means = {}
    for name, (prefix, n) in ARMS.items():
        vals = []
        for s in range(n):
            run = f"{prefix}-s{s}"
            t = json.loads((ROOT / "results" / "runs" / run / "train" / "run.json").read_text(encoding="utf-8"))
            a = sum(load_scores(run)[i]["pass"] for i in asst)
            vals.append((t["final_val_loss"], a))
            L.append(f"| {name} | {s} | {t['final_val_loss']:.4f} | {t['final_train_loss']:.4f} | {a} |")
        means[name] = (st.mean(v for v, _ in vals), st.mean(a for _, a in vals))
    L += ["", "Means: " + "; ".join(f"{k} val loss {v:.4f}, Assistant {a:.1f}" for k, (v, a) in means.items()) + ".", ""]

    lora = [load_scores(f"l14b_sft_rslora_tok-s{s}") for s in range(3)]
    full = {s: load_scores(f"l14b_full-s{s}") for s in range(2)}
    ans = {s: {a["id"]: clean_answer(a["raw"]) for a in jsonl(ROOT / "eval" / "outputs" / f"l14b_full-s{s}" / "answers.jsonl")} for s in range(2)}
    target = [i for i in asst if sum(l[i]["pass"] for l in lora) >= 2 and any(not full[s][i]["pass"] for s in full)]
    per_block = Counter(blocks[i] for i in target)
    fails = []
    for i in target:
        for s in full:
            if not full[s][i]["pass"]:
                cls, near, sv = classify(items[i], ans[s][i], full[s][i], canon)
                fails.append({"id": i, "seed": s, "block": blocks[i], "cls": cls, "near": near, "sim": sv,
                              "reason": full[s][i]["reason"], "text": ans[s][i]})
    by = defaultdict(Counter)
    for f in fails:
        by[f["block"]][f["cls"]] += 1
    L += ["## (2) Items full FT fails but LoRA passes", "",
          f"Items passed by LoRA in ≥ 2 of 3 seeds and failed by full FT in at least one of 2 seeds: **{len(target)}** "
          f"({len(fails)} item × seed failures).", "",
          "| Block | Items | " + " | ".join(CLASSES) + " |", "|---|---|" + "---|" * len(CLASSES)]
    for b in BLOCKS:
        if per_block[b]:
            L.append(f"| {b} | {per_block[b]} | " + " | ".join(str(by[b][c]) for c in CLASSES) + " |")
    tot = Counter(f["cls"] for f in fails)
    L.append(f"| **all** | {len(target)} | " + " | ".join(f"{tot[c]} ({100 * tot[c] / len(fails):.0f} %)" for c in CLASSES) + " |")
    other = Counter(f["reason"] for f in fails if f["cls"] == "other")
    if other:
        L += ["", "Scorer reasons in *other*: " + "; ".join(f"{r} ({n})" for r, n in other.most_common()) + "."]
    wi = [f for f in fails if f["cls"] == "wrong-intent"]
    if wi:
        L += ["", "Wrong-intent answers, nearest other intent: " + "; ".join(
            f"{f['id']} s{f['seed']} → `{f['near']}` ({f['sim']:.2f})" for f in sorted(wi, key=lambda f: -f["sim"])) + "."]
    L += ["", "## Examples (first failure of each of the three most common classes)", ""]
    for c, _ in tot.most_common(3):
        f = next(f for f in fails if f["cls"] == c)
        user = [m["content"] for m in items[f["id"]]["messages"] if m["role"] == "user"][-1]
        lora_text = clean_answer(next(a["raw"] for a in jsonl(ROOT / "eval" / "outputs" / "l14b_sft_rslora_tok-s0" / "answers.jsonl") if a["id"] == f["id"]))
        L += [f"- **{f['id']}** ({f['block']}, full FT seed {f['seed']}, class *{c}*; scorer: {f['reason']}"
              + (f"; nearest other intent `{f['near']}` {f['sim']:.2f}" if c == "wrong-intent" else "") + ")",
              f"  - User: {user}", f"  - Full FT: {f['text']}".replace("\n", " "), f"  - LoRA seed 0: {lora_text}".replace("\n", " "), ""]
    (ROOT / "results" / "full_ft_analysis.md").write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
