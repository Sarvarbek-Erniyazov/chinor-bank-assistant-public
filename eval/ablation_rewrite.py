"""results/ablation_rewrite.md: 14B SFT rsLoRA seed 0 on SFT v1 (canonical answers) vs v1_rewrite (paraphrases, ADR-024).

python eval/ablation_rewrite.py
Same config and seed; only the data differs. Exact McNemar on the 200 assistant items.
"""
from __future__ import annotations

from pathlib import Path

from results_tables import FLAGS, counts
from stats import BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact

ROOT = Path(__file__).resolve().parents[1]
ARMS = {"SFT v1 (canonical)": "l14b_sft_rslora_tok-s0", "SFT v1_rewrite (paraphrases)": "l14b_sft_rslora_tok-s0-v1_rewrite"}


def main():
    blocks = load_blocks()
    ids = [i for i in blocks if in_group("assistant", blocks[i])]
    cols = ["assistant"] + BLOCKS + [f for f, _ in FLAGS] + ["im_end"]
    L = ["# Ablation: canonical vs rewritten training answers (14B SFT rsLoRA, seed 0)", "",
         "`eval/ablation_rewrite.py`. Protocol A, rubric v1.3. Same config (`l14b_sft_rslora_tok.yaml`) and seed; v1_rewrite "
         "replaces most canonical task answers with Qwen3-32B paraphrases that passed verifier v2 and the entailment judge "
         "(about 1 in 6 still states something the handbook does not; `results/rewrite_funnel.json`).", "",
         "| Data | Assistant /200 | " + " | ".join(BLOCKS) + " | " + " | ".join(s for _, s in FLAGS) + " | <|im_end|> stops % |",
         "|---|---|" + "---|" * (len(BLOCKS) + len(FLAGS)) + "---|"]
    for name, run in ARMS.items():
        c = counts(run, blocks)
        L.append(f"| {name} | " + " | ".join(str(c[k]) for k in cols) + " |")
    a, b = (load_scores(r) for r in ARMS.values())
    m = mcnemar_exact([b[i]["pass"] for i in ids], [a[i]["pass"] for i in ids])
    L += ["", f"McNemar (rewrite-only / canonical-only passes): {m['a_only']} / {m['b_only']}, p = {m['p_value']:.2f}."]
    (ROOT / "results" / "ablation_rewrite.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
