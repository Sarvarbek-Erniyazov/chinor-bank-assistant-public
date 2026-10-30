"""results/ablations_tier_s.md from the Tier-S pilot matrix (C2a §3).

python eval/ablation_report.py   (results/seeds.md: eval/results_tables.py)
Per configuration: mean ± std (over seeds) of Assistant /200 and of each block; peak VRAM, tokens/s, wall-clock.
Each variant vs plain LoRA: difference of means, standard error of the difference from the seed spreads
(sqrt(s_a²/n_a + s_b²/n_b)), and exact McNemar on the seed-0 pair. Then the decision rule (C2a §3) is applied.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from stats import AGGREGATES, BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact

ROOT = Path(__file__).resolve().parents[1]
REF = "tier_s_pilot_lora"
CONFIGS = {
    "tier_s_pilot_lora": "plain LoRA (reference)",
    "tier_s_pilot_rslora": "rsLoRA",
    "tier_s_pilot_dora": "DoRA",
    "tier_s_pilot_lora_paged8": "LoRA + paged 8-bit AdamW",
    "tier_s_pilot_lora_nogroup": "LoRA, group_by_length false",
}
SEEDS = [0, 1, 2]
FLAGS = {"hard_violation": "HV", "fabricated_number": "NUM", "over_refusal": "OR", "injection_success": "INJ"}


def runs(cfg: str) -> list[str]:
    return [f"{cfg}-s{s}" for s in SEEDS if (ROOT / "eval" / "outputs" / f"{cfg}-s{s}" / "scores.jsonl").exists()]


def block_counts(run: str, blocks: dict[str, str]) -> dict[str, int]:
    sc = load_scores(run)
    out = {b: sum(r["pass"] for i, r in sc.items() if blocks[i] == b) for b in BLOCKS}
    out["assistant"] = sum(r["pass"] for i, r in sc.items() if in_group("assistant", blocks[i]))
    for f in FLAGS:  # scorer flags on the 200 assistant items
        out[f] = sum(r["flags"][f] for i, r in sc.items() if in_group("assistant", blocks[i]))
    return out


def train_run(run: str) -> dict:
    return json.loads((ROOT / "results" / "runs" / run / "train" / "run.json").read_text(encoding="utf-8"))


def ms(xs: list[float]) -> tuple[float, float]:
    return st.mean(xs), (st.stdev(xs) if len(xs) > 1 else float("nan"))


def fmt(xs: list[float], d: int = 1) -> str:
    m, s = ms(xs)
    return f"{m:.{d}f}" if len(xs) == 1 else f"{m:.{d}f} ± {s:.{d}f}"


def main():
    blocks = load_blocks()
    data = {}
    for cfg in CONFIGS:
        rs = runs(cfg)
        data[cfg] = {"runs": rs, "counts": [block_counts(r, blocks) for r in rs], "train": [train_run(r) for r in rs]}
    ref = data[REF]
    ref_a = [c["assistant"] for c in ref["counts"]]

    L = ["# Tier-S pilot ablations (Qwen3-0.6B-Base, SFT v1, Protocol A, rubric v1.3)", "",
         "`eval/ablation_report.py`. Mean ± std over seeds (n per row). Assistant /200 = T-seen + T-held + B1–B4; "
         "retention /20 is reported separately. Flags (HV hard violation, NUM fabricated number, OR over-refusal, INJ injection "
         "success) are counted on the 200 assistant items; per-seed rows in results/seeds.md.", "",
         "| Config | n | Assistant /200 | " + " | ".join(BLOCKS) + " | " + " | ".join(FLAGS.values()) + " | Peak VRAM (GB) | Tokens/s | Train wall-clock (s) |",
         "|---|---|---|" + "---|" * (len(BLOCKS) + len(FLAGS)) + "---|---|---|"]
    for cfg, name in CONFIGS.items():
        d = data[cfg]
        if not d["runs"]:
            continue
        cells = [fmt([c[b] for c in d["counts"]]) for b in BLOCKS]
        cells += [fmt([c[f] for c in d["counts"]]) for f in FLAGS]
        L.append(f"| {name} | {len(d['runs'])} | {fmt([c['assistant'] for c in d['counts']])} | " + " | ".join(cells)
                 + f" | {fmt([t['peak_vram_gb'] for t in d['train']], 2)} | {fmt([t['tokens_per_s'] for t in d['train']], 0)}"
                 + f" | {fmt([t['wall_clock_s'] for t in d['train']], 0)} |")

    L += ["", "## Variants vs plain LoRA", "",
          "SE of the difference = sqrt(s_variant²/n_variant + s_LoRA²/n_LoRA); for a single-seed variant the LoRA "
          "seed spread is used for both. McNemar: exact, seed-0 pair, 200 assistant items.", "",
          "| Variant | Δ mean Assistant /200 | SE of Δ | Δ > 2 SE | McNemar seed 0 (variant-only / LoRA-only, p) |",
          "|---|---|---|---|---|"]
    ids = [i for i in blocks if in_group("assistant", blocks[i])]
    s_ref = st.stdev(ref_a)
    decisions = {}
    for cfg, name in CONFIGS.items():
        if cfg == REF or not data[cfg]["runs"]:
            continue
        va = [c["assistant"] for c in data[cfg]["counts"]]
        s_v = st.stdev(va) if len(va) > 1 else s_ref
        se = (s_v ** 2 / len(va) + s_ref ** 2 / len(ref_a)) ** 0.5
        delta = st.mean(va) - st.mean(ref_a)
        a, b = load_scores(f"{cfg}-s0"), load_scores(f"{REF}-s0")
        mc = mcnemar_exact([a[i]["pass"] for i in ids], [b[i]["pass"] for i in ids])
        decisions[cfg] = {"delta": delta, "se": se, "adopt": delta > 2 * se}
        L.append(f"| {name} | {delta:+.1f} | {se:.1f} | {'yes' if delta > 2 * se else 'no'} | "
                 f"{mc['a_only']} / {mc['b_only']}, p = {mc['p_value']:.3f} |")

    # decision rule (C2a §3)
    tok_ref = st.mean(t["tokens_per_s"] for t in ref["train"])
    ng = data["tier_s_pilot_lora_nogroup"]
    tok_ng = st.mean(t["tokens_per_s"] for t in ng["train"]) if ng["runs"] else float("nan")
    ng_a = st.mean(c["assistant"] for c in ng["counts"]) if ng["runs"] else float("nan")
    lo, hi = min(ref_a), max(ref_a)
    vram_ref = st.mean(t["peak_vram_gb"] for t in ref["train"])
    vram_p8 = st.mean(t["peak_vram_gb"] for t in data["tier_s_pilot_lora_paged8"]["train"])
    adapter = next((c for c in ("tier_s_pilot_rslora", "tier_s_pilot_dora") if decisions.get(c, {}).get("adopt")), None)
    optim = "paged_adamw_8bit" if decisions.get("tier_s_pilot_lora_paged8", {}).get("adopt") else "adamw_torch"
    # group_by_length true is kept if it is faster than false with no score change beyond the seed spread
    group_kept = tok_ref > tok_ng and lo <= ng_a <= hi
    L += ["", "## Decision rule", "",
          "A variant is adopted for Tier S main only if its mean Assistant /200 exceeds plain LoRA by more than twice "
          "the SE of the difference; the optimizer on the same rule, VRAM saving noted either way; group_by_length is "
          "kept if tokens/s improves with no score change beyond the seed spread. Otherwise plain LoRA, adamw_torch, "
          "group_by_length true.", "",
          f"- Adapter: **{CONFIGS[adapter] if adapter else 'plain LoRA'}**"
          + ("" if adapter else " — no variant exceeds 2 SE") + ".",
          f"- Optimizer: **{optim}**; peak VRAM {vram_ref:.2f} GB (adamw_torch) vs {vram_p8:.2f} GB (paged 8-bit), "
          f"saving {vram_ref - vram_p8:+.2f} GB.",
          f"- group_by_length: **{'true' if group_kept or not ng['runs'] else 'false'}**; tokens/s {tok_ref:,.0f} (true) "
          f"vs {tok_ng:,.0f} (false); Assistant /200 with false (seed 0) = {ng_a:.0f}, LoRA seed range {lo}–{hi}.", ""]
    out = ROOT / "results" / "ablations_tier_s.md"
    out.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
