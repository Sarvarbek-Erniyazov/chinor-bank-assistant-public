"""results/robustness_sysprompt.md: the 14B v1.2 adapters under a paraphrased system prompt (plan 2026-10-29, step 5).

python eval/robustness_sysprompt.py
Same adapters, items and Protocol A; only the system prompt differs (eval/system_prompt_paraphrase.txt: same content,
other wording; eval/check_paraphrase.py). Per seed: Assistant /200 and every block under both prompts, exact McNemar
(paraphrase vs original), share of the 220 answers whose text is identical, and the stop reasons. Pooled: paired
bootstrap of Δ (figures/stats.py). Block R has no system prompt, so its answers should be identical.
"""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np

from score import clean_answer
from stats import BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("figure_stats", ROOT / "figures" / "stats.py")
_fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fs)
SEEDS = [0, 1, 2]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    blocks = load_blocks()
    asst = sorted(i for i in blocks if in_group("assistant", blocks[i]))
    L = ["# Robustness: paraphrased system prompt (14B SFT rsLoRA, data v1.2)", "",
         "`eval/robustness_sysprompt.py`. Same adapters (`l14b_sft_rslora_tok-s<seed>-v1.2`), items and Protocol A; the "
         "system prompt is `eval/system_prompt_paraphrase.txt` (every number, hour and channel of the frozen prompt, other "
         "wording, 446 tokens; recorded with its SHA-256 in each run.json) instead of `handbook/system_prompt.txt`. Block "
         "R is asked without a system prompt.", "",
         "| Seed | Prompt | Assistant /200 | " + " | ".join(BLOCKS) + " | Identical answers /220 (assistant / R) | Stops on <\\|im_end\\|> | McNemar (paraphrase-only / original-only, p) |",
         "|---|---|---|" + "---|" * len(BLOCKS) + "---|---|---|"]
    va, vb = [], []
    for s in SEEDS:
        o, p = f"l14b_sft_rslora_tok-s{s}-v1.2", f"l14b_sft_rslora_tok-s{s}-v1.2-paraphrase"
        so, sp = load_scores(o), load_scores(p)
        ao = {a["id"]: a for a in jsonl(ROOT / "eval" / "outputs" / o / "answers.jsonl")}
        ap = {a["id"]: a for a in jsonl(ROOT / "eval" / "outputs" / p / "answers.jsonl")}
        same = [i for i in ao if clean_answer(ao[i]["raw"]) == clean_answer(ap[i]["raw"])]
        same_a = sum(blocks[i] != "R" for i in same)
        same_r = sum(blocks[i] == "R" for i in same)
        m = mcnemar_exact([sp[i]["pass"] for i in asst], [so[i]["pass"] for i in asst])
        va.append(np.array([sp[i]["pass"] for i in asst]))
        vb.append(np.array([so[i]["pass"] for i in asst]))
        for name, sc, ans, extra in [("original", so, ao, "—"), ("paraphrase", sp, ap, f"{m['a_only']} / {m['b_only']}, p = {m['p_value']:.2f}")]:
            stops = Counter(a["stop_reason"] for a in ans.values())
            L.append(f"| {s} | {name} | {sum(sc[i]['pass'] for i in asst)} | "
                     + " | ".join(str(sum(sc[i]["pass"] for i in sc if blocks[i] == b)) for b in BLOCKS)
                     + f" | {len(same)} ({same_a} / {same_r}) | {stops['im_end']}/220 | {extra} |")
    bt = _fs.paired_bootstrap(va, vb)
    mo, mp = np.mean([v.sum() for v in vb]), np.mean([v.sum() for v in va])
    L += ["", f"**Pooled (3 seeds):** Assistant /200 original {mo:.1f}, paraphrase {mp:.1f}; Δ (paraphrase − original) = "
          f"{bt['delta']:+.1f} [{bt['ci_lo']:.1f}, {bt['ci_hi']:.1f}], paired bootstrap p = {bt['p_value']:.3f} "
          f"({bt['n_boot']:,} resamples over items, stratified by seed, seed 20261029)."]
    (ROOT / "results" / "robustness_sysprompt.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
