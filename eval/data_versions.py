"""results/data_versions.md: 14B SFT rsLoRA (trainable token rows) on SFT v1 vs v1.1 vs v1.2, and the data-version
decision rule (plan 2026-10-29, step 3).

python eval/data_versions.py
Per version: mean ± std over seeds 0-2 of Assistant /200, every block, retention, flags, over-refusal on the T blocks
(T-seen + T-held). Paired comparisons (same config, same seed): v1.1 vs v1, v1.2 vs v1, v1.2 vs v1.1, per block and on
the 200 assistant items: exact McNemar per seed, paired bootstrap of Δ (figures/stats.py: 10,000 resamples over items,
stratified by seed, seed 20261029).
Decision rule: the winner is the version with the highest mean Assistant /200, unless its mean T-block over-refusal
exceeds v1's by more than 2 items, or its mean B2 or B3 drops below v1's by more than one seed-sd (sd of v1's seeds);
then the next best. Versions missing a seed are reported but not eligible.
"""
from __future__ import annotations

import argparse
import importlib.util
import statistics as st
from pathlib import Path

import numpy as np

from collections import Counter

from results_tables import FLAGS, counts, exists, mean_std
from stats import BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact
from t_held_analysis import classify

ROOT = Path(__file__).resolve().parents[1]
# figures/stats.py has the same module name as eval/stats.py: load it under its own name
_spec = importlib.util.spec_from_file_location("figure_stats", ROOT / "figures" / "stats.py")
_fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fs)
paired_bootstrap = _fs.paired_bootstrap

VERSIONS = {"v1": "", "v1.1": "-v1.1", "v1.2": "-v1.2"}
PAIRS = [("v1.1", "v1"), ("v1.2", "v1"), ("v1.2", "v1.1")]
SEEDS = [0, 1, 2]


PREFIX = "l14b_sft_rslora_tok"  # --prefix tier_s_main_rslora_tok: the same report for Tier-S 1.7B


def run(v: str, s: int) -> str:
    return f"{PREFIX}-s{s}{VERSIONS[v]}"


def t_overrefusal(r: str, blocks: dict[str, str]) -> int:
    return sum(x["flags"]["over_refusal"] for i, x in load_scores(r).items() if blocks[i] in ("T-seen", "T-held"))


def main():
    global PREFIX
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default=PREFIX)
    ap.add_argument("--out", default="results/data_versions.md")
    args = ap.parse_args()
    PREFIX = args.prefix
    blocks = load_blocks()
    data = {}
    for v in VERSIONS:
        runs = [run(v, s) for s in SEEDS if exists(run(v, s))]
        if runs:
            data[v] = {"runs": runs, "c": [counts(r, blocks) for r in runs], "tor": [t_overrefusal(r, blocks) for r in runs]}
    cols = ["assistant"] + BLOCKS + [f for f, _ in FLAGS]
    L = [f"# SFT data versions: v1 vs v1.1 vs v1.2 (`{PREFIX}`, SFT rsLoRA + trainable token rows)", "",
         "`eval/data_versions.py`. Protocol A, rubric v1.3. v1 canonical answers (ADR-024); v1.1 = v1 + B1 / B1-dialogue "
         "repeated 4× (ADR-028); v1.2 = v1.1 + 60 handoff examples (ADR-029). Mean ± std over seeds. T over-refusal = "
         "over-refusal flags on T-seen + T-held.", "",
         "| Version | n | Assistant /200 | " + " | ".join(BLOCKS) + " | " + " | ".join(s for _, s in FLAGS) + " | T over-refusal |",
         "|---|---|---|" + "---|" * (len(BLOCKS) + len(FLAGS)) + "---|"]
    for v, d in data.items():
        L.append(f"| {v} | {len(d['runs'])} | " + " | ".join(mean_std([c[k] for c in d["c"]]) for k in cols) + f" | {mean_std(d['tor'])} |")
    L += ["", "## Paired comparisons", "",
          "Δ = first − second, in items passed. Bootstrap: 95 % CI and p over 10,000 resamples. McNemar per seed: "
          "first-only / second-only passes, exact p.", "",
          "| Comparison | Block (items) | Δ mean [95 % CI] | bootstrap p | McNemar seed 0 | seed 1 | seed 2 |", "|---|---|---|---|---|---|---|"]
    for a, b in PAIRS:
        if a not in data or b not in data:
            continue
        seeds = [s for s in SEEDS if exists(run(a, s)) and exists(run(b, s))]
        for blk in ["assistant"] + BLOCKS:
            ids = sorted(i for i in blocks if (in_group("assistant", blocks[i]) if blk == "assistant" else blocks[i] == blk))
            va = [np.array([load_scores(run(a, s))[i]["pass"] for i in ids]) for s in seeds]
            vb = [np.array([load_scores(run(b, s))[i]["pass"] for i in ids]) for s in seeds]
            bt = paired_bootstrap(va, vb)
            mc = [mcnemar_exact(list(x), list(y)) for x, y in zip(va, vb)]
            p = "< 1e-4" if bt["p_value"] == 0 else f"{bt['p_value']:.3f}"
            L.append(f"| {a} − {b} | {'Assistant' if blk == 'assistant' else blk} ({len(ids)}) | {bt['delta']:+.1f} "
                     f"[{bt['ci_lo']:.1f}, {bt['ci_hi']:.1f}] | {p} | "
                     + " | ".join(next((f"{m['a_only']} / {m['b_only']}, p = {m['p_value']:.2f}" for s2, m in zip(seeds, mc) if s2 == s), "—")
                                  for s in SEEDS) + " |")
    L += ["", "## T-held (the block the v1.2 handoff examples target)", "",
          "Per seed: T-held passes /20 and the class of the 20 answers (eval/t_held_analysis.py: (a) a training intent's "
          "canonical answer, (b) handoff / don't know, (c) other). Paired bootstrap rows for T-held are in the table above.", "",
          "| Version | Seed 0 | Seed 1 | Seed 2 | Mean passes | Mean (a) / (b) / (c) |", "|---|---|---|---|---|---|"]
    for v, d in data.items():
        cells, cls = [], []
        for r in d["runs"]:
            c = Counter(x["cls"] for x in classify(r))
            cls.append(c)
            cells.append(f"{sum(load_scores(r)[i]['pass'] for i in blocks if blocks[i] == 'T-held')} pass; "
                         f"{c['a']} / {c['b']} / {c['c']}")
        L.append(f"| {v} | " + " | ".join(cells + ["—"] * (3 - len(cells))) + f" | {st.mean(x['T-held'] for x in d['c']):.1f} | "
                 + " / ".join(f"{st.mean(c[k] for c in cls):.1f}" for k in "abc") + " |")
    L += ["", "## Decision rule", ""]
    full = {v: d for v, d in data.items() if len(d["runs"]) == len(SEEDS)}
    if "v1" not in full:
        L.append("Pending: v1 needs all three seeds.")
    else:
        v1 = full["v1"]
        sd = {k: st.stdev(c[k] for c in v1["c"]) for k in ("B2", "B3")}
        base = {k: st.mean(c[k] for c in v1["c"]) for k in ("B2", "B3")}
        tor1 = st.mean(v1["tor"])
        ranked = sorted(full, key=lambda v: -st.mean(c["assistant"] for c in full[v]["c"]))
        winner = None
        for v in ranked:
            d = full[v]
            m = st.mean(c["assistant"] for c in d["c"])
            tor = st.mean(d["tor"])
            drops = {k: base[k] - st.mean(c[k] for c in d["c"]) for k in ("B2", "B3")}
            bad = []
            if tor - tor1 > 2:
                bad.append(f"T over-refusal {tor:.1f} vs v1 {tor1:.1f} (> +2)")
            bad += [f"{k} {base[k] - drops[k]:.1f} vs v1 {base[k]:.1f} (drop {drops[k]:.1f} > sd {sd[k]:.1f})"
                    for k in ("B2", "B3") if drops[k] > sd[k]]
            L.append(f"- {v}: Assistant {m:.1f}; T over-refusal {tor:.1f}; B2 {base['B2'] - drops['B2']:.1f}, B3 "
                     f"{base['B3'] - drops['B3']:.1f} → " + ("**excluded**: " + "; ".join(bad) if bad else "eligible"))
            if not bad and winner is None:
                winner = v
        missing = [v for v in VERSIONS if v not in full]
        L += ["", f"Pending: {', '.join(missing)} incomplete; current leader among complete versions: {winner}." if missing
              else f"**Winner: {winner}**."]
    (ROOT / args.out).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
