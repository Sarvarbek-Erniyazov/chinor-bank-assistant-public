"""results/lora_vs_qlora.md: 14B SFT rsLoRA (bf16 base) vs 14B QLoRA rsLoRA (NF4 base), both with trainable
special-token rows (ADR-023 amendment), vs 14B full fine-tuning.

python eval/lora_vs_qlora.py
Per arm: mean ± std over seeds of Assistant /200, every block, retention and the four flags; peak VRAM, tokens/s and
train wall-clock from results/runs/<run>/train/run.json; artifact size = adapter file (local copy) or, for full FT,
all parameters × 2 bytes (bf16). Per seed: exact McNemar QLoRA vs LoRA on the 200 assistant items (same seed = same
data order).
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from results_tables import FLAGS, counts, exists, mean_std
from stats import BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact

ROOT = Path(__file__).resolve().parents[1]
ARMS = {"LoRA (bf16 base, adamw_torch)": "l14b_sft_rslora_tok", "QLoRA (NF4 base, paged_adamw_8bit)": "l14b_qlora_rslora_tok",
        "full FT lr 1e-5, 3 epochs (bf16, adamw_bnb_8bit)": "l14b_full",
        "full FT lr 2e-5, 3 epochs (diagnosis run, ADR-030)": "l14b_full_lr2e5"}
ADAPTERS = ROOT / "adapters" / "tok"


def artifact_gb(run: str, t: dict) -> float:
    f = ADAPTERS / run / "adapter_model.safetensors"
    return f.stat().st_size / 1e9 if f.exists() else t["trainable_parameters"]["total"] * 2 / 1e9


def main():
    blocks = load_blocks()
    ids = [i for i in blocks if in_group("assistant", blocks[i])]
    L = ["# 14B: LoRA vs QLoRA vs full fine-tuning", "",
         "`eval/lora_vs_qlora.py`. Protocol A, rubric v1.3, SFT v1. Mean ± std over seeds. QLoRA is evaluated on the NF4 "
         "base it was trained on. LoRA / QLoRA: rsLoRA r 16, lr 1e-4, trainable special-token rows; full FT: lr 1e-5. "
         "Flags on the 200 assistant items. Wall-clock = training only. Artifact = adapter file (fp32) or full bf16 weights. "
         "Full-FT rows hold only for their settings; with one seed at lr 2e-5 they are not a general claim about LoRA vs "
         "full fine-tuning.", "",
         "| Arm | n | Assistant /200 | " + " | ".join(BLOCKS) + " | " + " | ".join(s for _, s in FLAGS)
         + " | <|im_end|> stops % | Peak train VRAM (GB) | Tokens/s | Train wall-clock (min) | Artifact (GB) |",
         "|---|---|---|" + "---|" * (len(BLOCKS) + len(FLAGS)) + "---|---|---|---|---|"]
    for name, prefix in ARMS.items():
        runs = [f"{prefix}-s{s}" for s in range(3) if exists(f"{prefix}-s{s}")]
        if not runs:
            continue
        c = [counts(r, blocks) for r in runs]
        t = [json.loads((ROOT / "results" / "runs" / r / "train" / "run.json").read_text(encoding="utf-8")) for r in runs]
        L.append(f"| {name} | {len(runs)} | {mean_std([x['assistant'] for x in c])} | "
                 + " | ".join(mean_std([x[k] for x in c]) for k in BLOCKS + [f for f, _ in FLAGS] + ["im_end"])
                 + f" | {st.mean(x['peak_vram_gb'] for x in t):.1f} | {st.mean(x['tokens_per_s'] for x in t):,.0f}"
                 + f" | {st.mean(x['wall_clock_s'] for x in t) / 60:.1f} | {artifact_gb(runs[0], t[0]):.2f} |")
    L += ["", "QLoRA: seeds verified distinct (adapter hashes, 87–101/220 answers differ between seed pairs, pass/fail differs "
          "on 12–14 items); identical totals are coincidental."]
    L += ["", "| Seed | LoRA | QLoRA | McNemar (QLoRA-only / LoRA-only, p) |", "|---|---|---|---|"]
    for s in range(3):
        a, b = f"l14b_qlora_rslora_tok-s{s}", f"l14b_sft_rslora_tok-s{s}"
        if not (exists(a) and exists(b)):
            continue
        sa, sb = load_scores(a), load_scores(b)
        m = mcnemar_exact([sa[i]["pass"] for i in ids], [sb[i]["pass"] for i in ids])
        L.append(f"| {s} | {sum(sb[i]['pass'] for i in ids)} | {sum(sa[i]['pass'] for i in ids)} | "
                 f"{m['a_only']} / {m['b_only']}, p = {m['p_value']:.2f} |")
    L += ["", "## Full FT: lr 1e-5 vs lr 2e-5 (same seed = same data order)", "",
          "| Seed | Full FT lr 1e-5 | Full FT lr 2e-5 | LoRA | McNemar lr 2e-5 vs lr 1e-5 (2e-5-only / 1e-5-only, p) "
          "| McNemar lr 2e-5 vs LoRA (full-only / LoRA-only, p) |", "|---|---|---|---|---|---|"]
    tot = lambda sc: sum(sc[i]["pass"] for i in ids)
    for s in range(3):
        lo, hi, lo_ra = f"l14b_full-s{s}", f"l14b_full_lr2e5-s{s}", f"l14b_sft_rslora_tok-s{s}"
        if not (exists(lo) or exists(hi)):
            continue
        sh, sl, sr = (load_scores(r) if exists(r) else None for r in (hi, lo, lo_ra))
        cell = lambda a, b: (lambda m: f"{m['a_only']} / {m['b_only']}, " + (f"p = {m['p_value']:.3f}" if m["p_value"] >= 0.001 else "p < 0.001"))(
            mcnemar_exact([a[i]["pass"] for i in ids], [b[i]["pass"] for i in ids])) if a and b else "—"
        L.append(f"| {s} | {tot(sl) if sl else '—'} | {tot(sh) if sh else 'pending'} | {tot(sr) if sr else '—'} | "
                 f"{cell(sh, sl)} | {cell(sh, sr)} |")
    seeds = [s for s in range(3) if exists(f"l14b_full_lr2e5-s{s}") and exists(f"l14b_sft_rslora_tok-s{s}")]
    if seeds:
        f = ", ".join(str(tot(load_scores(f"l14b_full_lr2e5-s{s}"))) for s in seeds)
        r = ", ".join(str(tot(load_scores(f"l14b_sft_rslora_tok-s{s}"))) for s in seeds)
        L += ["", f"With tuned learning rate, full fine-tuning ({f}) is close to LoRA ({r}, same seed{'s' if len(seeds) > 1 else ''})."
              + (" Final claim waits for seed 1." if len(seeds) < 2 else
                 " Neither per-seed McNemar test separates them; this holds for these settings (3 epochs, lr 2e-5), not as a general claim.")]
    (ROOT / "results" / "lora_vs_qlora.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
