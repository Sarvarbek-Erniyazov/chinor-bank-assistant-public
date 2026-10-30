"""results/size_curve.md: base vs SFT rsLoRA (trainable special-token rows) across Qwen3 sizes.

python eval/size_curve.py
Per size: base 0-shot (Protocol A) and the fixed SFT arm (mean ± std over the seeds that exist), Assistant /200,
every block, retention, flags, <|im_end|> stops, exact McNemar seed 0 vs base, peak VRAM and tokens/s.
"""
from __future__ import annotations

import json
from pathlib import Path

from results_tables import FLAGS, counts, exists, mean_std
from stats import BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact

ROOT = Path(__file__).resolve().parents[1]
SFT = {"1.7B": "tier_s_main_rslora_tok", "4B": "size_4b_rslora_tok", "8B": "size_8b_rslora_tok", "14B": "l14b_sft_rslora_tok"}


def main():
    blocks = load_blocks()
    ids = [i for i in blocks if in_group("assistant", blocks[i])]
    cols = ["assistant"] + BLOCKS + [f for f, _ in FLAGS] + ["im_end"]
    L = ["# Size curve: Qwen3 base vs SFT rsLoRA (trainable special-token rows)", "",
         "`eval/size_curve.py`. Protocol A, rubric v1.3, SFT v1. SFT rows: mean ± std over the seeds that exist (n). "
         "McNemar: exact, seed 0 vs base, 200 assistant items. 1.7B uses lr 2e-4, 4B lr 2e-4, 8B / 14B lr 1e-4 (ADR-026).", "",
         "| Size | Arm | n | Assistant /200 | " + " | ".join(BLOCKS) + " | " + " | ".join(s for _, s in FLAGS)
         + " | <|im_end|> stops % | McNemar vs base (SFT-only / base-only, p) | Peak train VRAM (GB) | Tokens/s |",
         "|---|---|---|---|" + "---|" * (len(BLOCKS) + len(FLAGS)) + "---|---|---|---|"]
    for size, prefix in SFT.items():
        base = f"base-{size}-0shot-A"
        runs = [f"{prefix}-s{s}" for s in range(3) if exists(f"{prefix}-s{s}")]
        if not runs or not exists(base):
            continue
        bc = counts(base, blocks)
        L.append(f"| {size} | base 0-shot | 1 | " + " | ".join(str(bc[k]) for k in cols) + " | — | — | — |")
        c = [counts(r, blocks) for r in runs]
        sa, sb = load_scores(runs[0]), load_scores(base)
        m = mcnemar_exact([sa[i]["pass"] for i in ids], [sb[i]["pass"] for i in ids])
        t = json.loads((ROOT / "results" / "runs" / runs[0] / "train" / "run.json").read_text(encoding="utf-8"))
        L.append(f"| {size} | SFT rsLoRA | {len(runs)} | " + " | ".join(mean_std([x[k] for x in c]) for k in cols)
                 + f" | {m['a_only']} / {m['b_only']}, p = {m['p_value']:.1e} | {t['peak_vram_gb']:.1f} | {t['tokens_per_s']:,.0f} |")
    (ROOT / "results" / "size_curve.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
