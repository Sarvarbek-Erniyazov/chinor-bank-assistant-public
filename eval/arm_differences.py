"""results/arm_differences.md: Δ Assistant /200 with a 95 % CI for every pair of arms the write-up compares.

python eval/arm_differences.py          (after results/build_tidy.py; CPU only, existing outputs)
Δ = A − B in assistant items passed (200 items). Paired bootstrap over items, stratified by seed (figures/stats.py;
seed strata matched by seed index: arms of different sizes or methods are independent runs, so the index only fixes
the resampling layout). Exact McNemar on seed 0. Holm over the comparisons in this table (one family, m = number of
rows). A non-significant row is reported as "no significant difference detected; Δ = x [95 % CI]", never as
equivalence: the CI says how large a difference the data still allow.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "figures"))
import stats as S  # noqa: E402

ASSISTANT = {"T-seen", "T-held", "B1", "B2", "B3", "B4"}
# (label, arm A, arm B, seeds used or None for all common/available seeds)
COMPARISONS = [
    ("14B QLoRA − 14B LoRA (SFT v1)", "l14b_qlora_rslora_tok", "l14b_sft_rslora_tok", None),
    ("14B full FT lr 2e-5 − 14B LoRA (SFT v1, seeds 0–1)", "l14b_full_lr2e5", "l14b_sft_rslora_tok", ["0", "1"]),
    ("4B − 14B (SFT rsLoRA v1)", "size_4b_rslora_tok", "l14b_sft_rslora_tok", None),
    ("8B − 14B (SFT rsLoRA v1)", "size_8b_rslora_tok", "l14b_sft_rslora_tok", None),
    ("4B − 8B (SFT rsLoRA v1)", "size_4b_rslora_tok", "size_8b_rslora_tok", None),
    ("data v1.1 − v1 (14B rsLoRA, seeds 0–2)", "l14b_sft_rslora_tok-v1.1", "l14b_sft_rslora_tok", ["0", "1", "2"]),
    ("data v1.2 − v1 (14B rsLoRA, seeds 0–2)", "l14b_sft_rslora_tok-v1.2", "l14b_sft_rslora_tok", ["0", "1", "2"]),
    ("data v1.2 − v1.1 (14B rsLoRA, seeds 0–2)", "l14b_sft_rslora_tok-v1.2", "l14b_sft_rslora_tok-v1.1", ["0", "1", "2"]),
]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    passes = defaultdict(lambda: defaultdict(dict))  # arm group -> seed -> item -> pass
    with (ROOT / "results" / "tidy" / "items_long.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["block"] in ASSISTANT:
                passes[r["arm_group"]][r["seed"]][r["item_id"]] = int(r["pass"])
    rows = []
    for name, a, b, seeds in COMPARISONS:
        sa = seeds or sorted(set(passes[a]) & set(passes[b]))
        items = sorted(passes[a][sa[0]])
        va = [[passes[a][s][i] for i in items] for s in sa]
        vb = [[passes[b][s][i] for i in items] for s in sa]
        bt, mc = S.paired_bootstrap(va, vb), S.mcnemar_exact(va[0], vb[0])
        mean = lambda v: sum(map(sum, v)) / len(v)
        rows.append({"name": name, "a": mean(va), "b": mean(vb), "seeds": len(sa), "bt": bt, "mc": mc})
    for x, p in zip(rows, S.holm([x["mc"]["p_value"] for x in rows])):
        x["holm"] = p
    L = ["# Arm differences: Δ Assistant /200 with 95 % CI", "",
         "`eval/arm_differences.py`. Protocol A, rubric v1.3. Δ = A − B in assistant items passed (of 200); paired "
         f"bootstrap over items stratified by seed ({S.BOOT_N:,} resamples, seed {S.BOOT_SEED}; strata matched by seed "
         "index), exact McNemar on seed 0. **Holm family:** the "
         f"{len(rows)} Assistant-level comparisons in this table (m = {len(rows)}). Preference arms (DPO / SimPO − SFT "
         "seed 0) are in `results/preference.md` (their own family). A row without a significant difference is worded "
         "\"no significant difference detected; Δ = x [95 % CI]\"; it is not evidence of equivalence.", "",
         "| Comparison | Seeds | A /200 | B /200 | Δ [95 % CI] | Bootstrap p | McNemar seed 0 (A only / B only, p) | Holm p (m = "
         f"{len(rows)}) |", "|---|---|---|---|---|---|---|---|"]
    for x in rows:
        L.append(f"| {x['name']} | {x['seeds']} | {x['a']:.1f} | {x['b']:.1f} | {x['bt']['delta']:+.1f} "
                 f"[{x['bt']['ci_lo']:.1f}, {x['bt']['ci_hi']:.1f}] | {x['bt']['p_value']:.3f} | {x['mc']['a_only']} / "
                 f"{x['mc']['b_only']}, {x['mc']['p_value']:.2f} | {x['holm']:.3f} |")
    out = ROOT / "results" / "arm_differences.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
