"""results/preference.md: DPO vs SimPO vs SFT (C4, closing plan 2026-10-29).

python eval/pref_results.py          (after results/build_tidy.py and eval/redteam_results.py)
Arms: SFT = l14b_sft_rslora_tok-s0-v1.2 (the parent: sft-merged is this run merged), DPO = pref_dpo_rules-s*,
SimPO = pref_simpo_rules-s*. Assistant /200 and pass rate per block (mean ± SD over seeds). Δ vs SFT and DPO vs SimPO:
paired bootstrap over items, stratified by seed (figures/stats.py; the single SFT seed is paired with every seed),
exact McNemar on seed 0, Holm-adjusted over all comparisons in the table. Red-team attack_success and
safe_and_helpful from results/tidy/redteam.csv; output length in tokens (eval-v1 assistant items); training reward
accuracy and margin from results/runs/<run>/train/loss.csv (last 10 steps) and the final step.
"""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "figures"))
import stats as S  # noqa: E402

TIDY = ROOT / "results" / "tidy"
BLOCKS = ["T-seen", "T-held", "B1", "B2", "B3", "B4"]
SFT = "l14b_sft_rslora_tok-s0-v1.2"
ARMS = {"SFT (v1.2 seed 0)": "sft", "DPO (rules)": "pref_dpo_rules", "SimPO (rules)": "pref_simpo_rules",
        "RFT (exploratory, ADR-033)": "l14b_sft_rslora_tok-v1.2_rft"}


def rows(name: str) -> list[dict]:
    with (TIDY / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt_p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def ms(xs: list[float], d: int = 1) -> str:
    return f"{st.mean(xs):.{d}f}" + (f" ± {st.stdev(xs):.{d}f}" if len(xs) > 1 else "")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    long = rows("items_long.csv")
    passes, lens = defaultdict(lambda: defaultdict(dict)), defaultdict(list)  # arm key -> seed -> item -> pass
    block_of = {}
    for r in long:
        key = "sft" if r["arm"] == SFT else r["arm_group"] if r["arm_group"] in ARMS.values() else None
        if key is None or r["block"] not in BLOCKS:
            continue
        passes[key][r["arm"]][r["item_id"]] = int(r["pass"])
        lens[key].append(int(r["n_tokens"]))
        block_of[r["item_id"]] = r["block"]
    have = [k for k in ARMS.values() if k in passes]
    if len(have) < 2:
        sys.exit(f"need SFT and at least one preference arm in {TIDY / 'items_long.csv'}; have {have}")
    items = {b: sorted(i for i, x in block_of.items() if x == b) for b in BLOCKS}
    items["Assistant"] = sorted(block_of)
    vec = lambda k, its: [[passes[k][a][i] for i in its] for a in sorted(passes[k])]
    name = {v: n for n, v in ARMS.items()}
    L = ["# Preference optimisation: DPO vs SimPO vs SFT (14B)", "",
         "`eval/pref_results.py`. All runs start from sft-merged (14B rsLoRA v1.2 seed 0 merged in bf16; manifest "
         "e4d24cc5…, docs/compute.md) with a fresh rsLoRA (r 16, α 32), lr 1e-5, 2 epochs, effective batch 16, on the "
         "rule-labelled pairs (`data/pref/v1/pairs_rules.jsonl`, DATA_CARD). DPO β 0.1 (reference = sft-merged); SimPO "
         "β 2.0, γ 1.0. Eval-v1 under Protocol A; red-team = redteam-v1 (60 items). Labels were not checked by the judge "
         "(dropped this session); κ(rules, author) on 60 blind pairs follows in `results/judge_calibration.md`.", "",
         "## Eval-v1 (pass counts; mean ± SD over seeds)", "",
         "| Arm | Seeds | Assistant /200 | " + " | ".join(f"{b} /{len(items[b])}" for b in BLOCKS) + " |",
         "|---|---|---|" + "---|" * len(BLOCKS)]
    for k in have:
        seeds = sorted(passes[k])
        cell = lambda its: ms([sum(passes[k][a][i] for i in its) for a in seeds])
        L.append(f"| {name[k]} | {len(seeds)} | {cell(items['Assistant'])} | " + " | ".join(cell(items[b]) for b in BLOCKS) + " |")
    comps = [(a, "sft") for a in have if a != "sft"] + ([("pref_dpo_rules", "pref_simpo_rules")] if {"pref_dpo_rules", "pref_simpo_rules"} <= set(have) else [])
    res = []
    for a, b in comps:
        for blk in ["Assistant"] + BLOCKS:
            va, vb = vec(a, items[blk]), vec(b, items[blk])
            bt = S.paired_bootstrap(va, vb)
            mc = S.mcnemar_exact(va[0], vb[0])
            res.append({"a": a, "b": b, "blk": blk, "bt": bt, "mc": mc})
    for x, p in zip(res, S.holm([x["mc"]["p_value"] for x in res])):
        x["holm"] = p
    L += ["", f"## Differences (Δ passes; Holm over the {len(res)} comparisons)", "",
          "| Comparison | Block | Δ [95 % CI] | Bootstrap p | McNemar seed 0 (A only / B only) | Holm p |", "|---|---|---|---|---|---|"]
    for x in res:
        L.append(f"| {name[x['a']]} − {name[x['b']]} | {x['blk']} | {x['bt']['delta']:+.1f} [{x['bt']['ci_lo']:.1f}, "
                 f"{x['bt']['ci_hi']:.1f}] | {fmt_p(x['bt']['p_value'])} | {x['mc']['a_only']} / {x['mc']['b_only']} | {fmt_p(x['holm'])} |")
    rt = {r["arm_group"]: r for r in rows("redteam.csv")}
    rt_key = {"sft": "l14b_sft_rslora_tok-v1.2"}
    L += ["", "## Red-team, output length, stops", "",
          "| Arm | attack_success (lower better) | safe_and_helpful | Mean tokens (assistant items) | p90 tokens |", "|---|---|---|---|---|"]
    for k in have:
        r = rt.get(rt_key.get(k, k))
        a = (f"{r['attack_k']}/{r['n']} = {float(r['attack_rate']):.1%} [{float(r['attack_ci_lo']):.1%}, {float(r['attack_ci_hi']):.1%}]"
             if r else "pending")
        h = f"{r['sh_k']}/{r['n']} = {float(r['sh_rate']):.1%}" if r else "pending"
        q = sorted(lens[k])
        L.append(f"| {name[k]} | {a} | {h} | {st.mean(q):.0f} | {q[int(0.9 * (len(q) - 1))]} |")
    if rt.get("l14b_sft_rslora_tok-v1.2"):
        L.append("\nThe SFT red-team row pools the 5 seeds of 14B rsLoRA v1.2 (seed 0 alone is in `results/redteam.md` per seed).")
    L += ["", "## Training: reward accuracy and margin", "",
          "| Run | Pairs | Steps | Final loss | Reward accuracy (last 10 steps) | Margin (last 10 steps) | Chosen / rejected length |",
          "|---|---|---|---|---|---|---|"]
    import json
    for k in have:
        if k in ("sft", "l14b_sft_rslora_tok-v1.2_rft"):  # no preference loss
            continue
        for run in sorted(passes[k]):
            lc, rj = ROOT / "results" / "runs" / run / "train" / "loss.csv", ROOT / "results" / "runs" / run / "train" / "run.json"
            if not lc.exists() or "reward_acc" not in lc.read_text(encoding="utf-8").splitlines()[0]:
                L.append(f"| `{run}` | | | | pending | | |")
                continue
            with lc.open(encoding="utf-8") as f:
                lr = list(csv.DictReader(f))
            tail = lr[-10:]
            meta = json.loads(rj.read_text(encoding="utf-8")) if rj.exists() else {}
            L.append(f"| `{run}` | {meta.get('pairs_used', '')} | {len(lr)} | {float(lr[-1]['loss']):.3f} | "
                     f"{st.mean(float(t['reward_acc']) for t in tail):.2f} | {st.mean(float(t['margin']) for t in tail):.2f} | "
                     f"{st.mean(float(t['chosen_len']) for t in tail):.0f} / {st.mean(float(t['rejected_len']) for t in tail):.0f} |")
    out = ROOT / "results" / "preference.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
