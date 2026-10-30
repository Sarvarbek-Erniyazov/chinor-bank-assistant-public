"""Build every figure (F1–F13) and table (T1–T6) from results/ files only, plus the index docs/figures.md.

python figures/make_figures.py [--only F3,T1] [--results DIR] [--out DIR] [--docs FILE]
Inputs: results/tidy/*.csv, results/lm_head_rows.csv, results/rewrite_funnel.json, results/qualitative.jsonl (all
from results/build_tidy.py). Each figure is written as <out>/<id>_{light,dark}.{png,svg,pdf} (PNG 300 dpi), each
table as <out>/<id>.md. A figure whose inputs do not exist yet is skipped with "pending: <missing input>"; the index
lists it as pending. Captions (with exact p-values) are computed here, so they always match the plotted data.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats as S  # noqa: E402
import style  # noqa: E402
from style import WIDTH_1COL, WIDTH_2COL, plt, themed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = ["T-seen", "T-held", "B1", "B2", "B3", "B4", "R"]
ASSISTANT = BLOCKS[:-1]
BLOCK_NAMES = {"T-seen": "T-seen (trained intents)", "T-held": "T-held (held-out intents)", "B1": "B1 ask for missing detail",
               "B2": "B2 out of scope", "B3": "B3 safety / injection", "B4": "B4 persona", "R": "R retention (no system prompt)"}
SIZES = {"0.6B": 0.6, "1.7B": 1.7, "4B": 4.0, "8B": 8.0, "14B": 14.0}
DATA_VERSIONS = ["v1.1", "v1.2"]  # SFT data versions after v1 (ADR-028, ADR-029): run-name suffix
VERSION_MARKER = {"v1.1": "^", "v1.2": "D"}


def data_version(group: str) -> str:
    return next((v for v in DATA_VERSIONS if group.endswith(f"-{v}")), "v1")


class Pending(Exception):
    pass


# ---------------------------------------------------------------- inputs

class Results:
    def __init__(self, rdir: Path):
        self.dir = rdir
        self._cache = {}

    def path(self, rel: str) -> Path:
        p = self.dir / rel
        if not p.exists():
            raise Pending(f"results/{rel}")
        return p

    def csv(self, rel: str) -> list[dict]:
        if rel not in self._cache:
            with self.path(rel).open(encoding="utf-8") as f:
                self._cache[rel] = [{k: num(v) for k, v in r.items()} for r in csv.DictReader(f)]
        return self._cache[rel]

    def json(self, rel: str):
        return json.loads(self.path(rel).read_text(encoding="utf-8"))

    def jsonl(self, rel: str) -> list[dict]:
        return [json.loads(l) for l in self.path(rel).read_text(encoding="utf-8").splitlines() if l.strip()]

    def summary(self) -> dict[str, dict]:
        return {r["arm_group"]: r for r in self.csv("tidy/arm_summary.csv")}

    def passes(self) -> dict[str, dict[int, dict[str, int]]]:
        """arm group → seed → item → pass (seed "" for single-seed arms becomes 0)."""
        if "passes" not in self._cache:
            out = defaultdict(lambda: defaultdict(dict))
            for r in self.csv("tidy/items_long.csv"):
                out[r["arm_group"]][r["seed"] if r["seed"] != "" else 0][r["item_id"]] = r["pass"]
            self._cache["passes"] = out
            self._cache["blocks"] = {r["item_id"]: r["block"] for r in self.csv("tidy/items_long.csv")}
        return self._cache["passes"]

    def blocks(self) -> dict[str, str]:
        self.passes()
        return self._cache["blocks"]


def num(v: str):
    if v == "":
        return ""
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() and "." not in v else f


def label(r: dict) -> str:
    m, g = r["method"], r["arm_group"]
    name = {"base": "base 0-shot", "instruct (reference)": "Instruct (reference)", "rsLoRA": "SFT rsLoRA", "SFT-LoRA": "SFT LoRA",
            "QLoRA": "SFT QLoRA", "full FT": "SFT full FT", "DoRA": "SFT DoRA"}.get(m, m)
    if "3shot" in g:
        name = "base 3-shot"
    if "v1_rewrite" in g:
        name += ", rewrite data"
    for v in DATA_VERSIONS:
        if g.endswith(f"-{v}"):
            name += f", data {v}"
    if r["token_rows"] == "no":
        name += " (no token rows)"
    return name


def main_groups(R: Results, sizes=("1.7B", "14B"), trained_only_fixed=True, versions=False) -> list[dict]:
    """Protocol-A base 0-shot, Instruct reference and the trained arms with trainable token rows (or full FT)."""
    order = {"base": 0, "instruct (reference)": 1, "rsLoRA": 2, "QLoRA": 3, "full FT": 4, "DPO": 5, "SimPO": 6, "GRPO": 7}
    out = []
    for r in R.summary().values():
        if (r["size"] not in sizes or r["protocol"] != "A" or "pilot" in r["arm_group"] or "v1_rewrite" in r["arm_group"]
                or "paraphrase" in r["arm_group"] or r["arm_group"].endswith("_rft")):  # RFT: exploratory, 1 seed (ADR-033)  # robustness arms (other system prompt) are reported separately
            continue
        if r["method"] == "base" and not r["arm_group"].endswith("0shot-A"):
            continue
        if trained_only_fixed and r["token_rows"] == "no":
            continue
        if r["arm_group"].startswith("size_") or (not versions and data_version(r["arm_group"]) != "v1"):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (SIZES[r["size"]], order.get(r["method"], 9), r["arm_group"]))


def base_of(R: Results, size: str) -> dict:
    s = R.summary().get(f"base-{size}-0shot-A")
    if not s:
        raise Pending(f"base-{size}-0shot-A in results/tidy/arm_summary.csv")
    return s


def vectors(R: Results, group: str, items: list[str]) -> list[np.ndarray]:
    group, _, only = group.partition("@s")  # "<group>@s0": that seed alone (the preference runs' SFT parent)
    seeds = R.passes()[group]
    if only:
        seeds = {k: v for k, v in seeds.items() if str(k) == only}
    return [np.array([seeds[s][i] for i in items]) for s in sorted(seeds)]


def items_of(R: Results, blocks: list[str]) -> list[str]:
    return sorted(i for i, b in R.blocks().items() if b in blocks)


def fmt_p(p: float, boot: bool = False) -> str:
    if boot and p == 0:
        return f"< {1 / S.BOOT_N:.0e} (0 of {S.BOOT_N:,} resamples)"
    return f"{p:.1e}" if p < 1e-3 else f"{p:.3f}"


def ms(r: dict, key: str, d: int = 1) -> str:
    sd = r.get(f"{key}_sd", "")
    return f"{r[f'{key}_mean']:.{d}f}" if sd == "" else f"{r[f'{key}_mean']:.{d}f} ± {sd:.{d}f}"


def ink(t: dict, value: float) -> str:
    """Readable text on a cividis cell."""
    return "#FFFFFF" if value < 0.55 else "#1A1A1A"


# ---------------------------------------------------------------- figures
# each returns {"draw": f(theme) -> Figure, "caption": str}; raise Pending when an input is missing

def f1(R: Results) -> dict:
    groups = main_groups(R)
    if not any(g["method"] not in ("base", "instruct (reference)") for g in groups):
        raise Pending("a trained arm in results/tidy/arm_summary.csv")
    best = max((g for g in groups if g["size"] == "14B" and g["method"] not in ("base", "instruct (reference)")),
               key=lambda g: g["assistant_mean"])
    b14, i14 = base_of(R, "14B"), R.summary().get("ref-14B-instruct-A")
    items = items_of(R, ASSISTANT)
    bt = S.paired_bootstrap(vectors(R, best["arm_group"], items), vectors(R, b14["arm_group"], items))

    def draw(theme):
        with themed(theme) as t:
            sizes = [s for s in ("1.7B", "14B") if any(g["size"] == s for g in groups)]
            fig, axes = plt.subplots(1, len(sizes), figsize=(WIDTH_2COL, 2.3), sharex=True, squeeze=False)
            for ax, size in zip(axes[0], sizes):
                gs = [g for g in groups if g["size"] == size]
                for y, g in enumerate(gs):
                    c = style.colour(g["method"])
                    lo, hi = 200 * g["assistant_ci_lo"], 200 * g["assistant_ci_hi"]
                    ax.plot([lo, hi], [y, y], color=c, lw=2, solid_capstyle="round")
                    for s, v in R.passes()[g["arm_group"]].items():
                        ax.plot(sum(v[i] for i in items), y + 0.22, "o", ms=3, color=c, alpha=0.8, mec="none")
                    hollow = g["method"] == "instruct (reference)"
                    ax.plot(g["assistant_mean"], y, "o", ms=8, mfc=t["bg"] if hollow else c, mec=c if hollow else t["bg"], mew=1.5)
                    ax.annotate(f"{g['assistant_mean']:.0f}", (hi, y), xytext=(5, 0), textcoords="offset points", va="center",
                                color=t["text"], fontsize=8)
                ax.set_yticks(range(len(gs)), [label(g) for g in gs])
                ax.set_ylim(len(gs) - 0.4, -0.6)
                ax.set_xlim(0, 200)
                ax.set_title(f"Qwen3-{size}-Base", loc="left")
                ax.set_xlabel("Assistant items passed (of 200)")
                ax.grid(axis="y", visible=False)
            fig.tight_layout()
            return fig

    cap = (f"**Question:** does fine-tuning turn a base model into a usable bank assistant? **Plotted:** Assistant score "
           f"(items passed of 200; frozen eval set, Protocol A) per arm; large dot = mean over seeds, small dots = single "
           f"seeds (n = 3 for the LoRA/QLoRA arms, 1 otherwise), hollow = Instruct model as an outside reference. "
           f"**Error bars:** Wilson 95 % CI on the pooled pass rate. **Test:** paired bootstrap of Δ /200, best 14B arm "
           f"(`{best['arm_group']}`) vs base, Δ = {bt['delta']:+.1f} [{bt['ci_lo']:.1f}, {bt['ci_hi']:.1f}], "
           f"p {fmt_p(bt['p_value'], True)}. **Takeaway:** supervised fine-tuning lifts 14B from {b14['assistant_mean']:.0f} "
           f"to {best['assistant_mean']:.0f} of 200" + (f", well above the vendor's Instruct model ({i14['assistant_mean']:.0f})." if i14 else "."))
    return {"draw": draw, "caption": cap}


def f2(R: Results) -> dict:
    rates = {(r["arm_group"], r["block"]): r for r in R.csv("tidy/block_rates.csv")}
    groups = main_groups(R, sizes=tuple(SIZES), versions=True) + [g for g in R.summary().values()
                                                    if g["arm_group"].startswith("size_") or "v1_rewrite" in g["arm_group"]]
    groups = sorted({g["arm_group"]: g for g in groups}.values(), key=lambda g: (SIZES.get(g["size"], 99), g["method"] != "base", g["arm_group"]))
    m = np.array([[rates[(g["arm_group"], b)]["rate"] for b in BLOCKS] for g in groups])

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_2COL, 0.28 * len(groups) + 1.1))
            im = ax.imshow(m, cmap=style.HEATMAP, vmin=0, vmax=1, aspect="auto")
            for (y, x), v in np.ndenumerate(m):
                ax.text(x, y, f"{100 * v:.0f}", ha="center", va="center", fontsize=7, color=ink(t, v))
            ax.set_xticks(range(len(BLOCKS)), BLOCKS)
            ax.set_yticks(range(len(groups)), [f"{g['size']} {label(g)}" for g in groups])
            ax.tick_params(length=0)
            ax.grid(False)
            for s in ax.spines.values():
                s.set_visible(False)
            cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
            cb.set_label("pass rate (%)")
            cb.set_ticks([0, 0.5, 1], labels=["0", "50", "100"])
            cb.outline.set_visible(False)
            ax.xaxis.tick_top()
            fig.tight_layout()
            return fig

    weakest = min(BLOCKS[:-1], key=lambda b: float(np.mean(m[[i for i, g in enumerate(groups) if g["method"] != "base"], BLOCKS.index(b)])))
    return {"draw": draw, "caption": (
        "**Question:** which behaviours does each arm get right? **Plotted:** pass rate (%) per eval block (T-seen 100 "
        "items, T-held 20, B1 20, B2 20, B3 25, B4 15, R 20) per arm, seeds pooled (n = 1–3 seeds, shown in T1). "
        "**Error bars:** none in the cells; Wilson CIs per cell are in `results/tidy/block_rates.csv`. **Test:** none "
        "(descriptive; tests in F3). **Takeaway:** training fixes trained intents, scope and persona, but the "
        f"weakest block for trained arms is {weakest} — held-out intents and asking for missing details stay near 0.")}


def stage_effect(R: Results, pairs: list[tuple[str, str]], fid: str, question: str, what: str) -> dict:
    """Paired bootstrap Δ per block (percentage points) of each (arm, reference) pair; exact McNemar, Holm."""
    summ = R.summary()
    rows = []
    for arm, ref in pairs:
        for b in ["assistant"] + ASSISTANT:
            items = items_of(R, ASSISTANT if b == "assistant" else [b])
            a, r = vectors(R, arm, items), vectors(R, ref, items)
            bt = S.paired_bootstrap(a, r)
            mc = S.mcnemar_exact(a[0], r[0])
            rows.append({"arm": arm, "ref": ref, "block": b, "n": len(items), "bt": bt, "mc": mc})
    adj = S.holm([x["mc"]["p_value"] for x in rows])
    for x, p in zip(rows, adj):
        x["holm"] = p

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_2COL, 2.8 + 0.12 * max(0, len(pairs) - 4)))
            ys = ["assistant"] + ASSISTANT
            k = len(pairs)
            for j, (arm, ref) in enumerate(pairs):
                g = summ[arm]
                c = style.colour(g["method"])
                off = (j - (k - 1) / 2) * min(0.16, 0.8 / k)
                for x in (x for x in rows if x["arm"] == arm):
                    y = ys.index(x["block"]) + off
                    sc = 100 / x["n"]
                    ax.plot([x["bt"]["ci_lo"] * sc, x["bt"]["ci_hi"] * sc], [y, y], color=c, lw=2, solid_capstyle="round")
                    # same method at two sizes: squares for the smaller model
                    mk = VERSION_MARKER.get(data_version(arm), "o" if g["size"] == "14B" else "s")
                    ax.plot(x["bt"]["delta"] * sc, y, mk, ms=6, color=c, mec=style.edge(g["method"], theme), mew=1.2,
                            label=f"{g['size']} {label(g)} − {label(summ[ref.partition('@')[0]])}{' seed ' + ref.partition('@s')[2] if '@' in ref else ''}" if x["block"] == "assistant" else None)
                    if x["holm"] < 0.05:
                        ax.annotate("*", (x["bt"]["ci_hi"] * sc, y), xytext=(3, -3), textcoords="offset points", color=t["text"])
            ax.axvline(0, color=t["axis"], lw=0.8)
            ax.set_yticks(range(len(ys)), ["Assistant (200)"] + [f"{b} ({len(items_of(R, [b]))})" for b in ASSISTANT])
            ax.set_ylim(len(ys) - 0.5, -0.5)
            ax.set_xlabel("Δ pass rate (percentage points)")
            ax.grid(axis="y", visible=False)
            ax.legend(loc="lower right", fontsize=7)
            fig.tight_layout()
            return fig

    agg = [x for x in rows if x["block"] == "assistant"]
    parts = "; ".join(f"`{x['arm']}` − `{x['ref']}`: Δ /200 = {x['bt']['delta']:+.1f} [{x['bt']['ci_lo']:.1f}, {x['bt']['ci_hi']:.1f}], "
                      f"bootstrap p {fmt_p(x['bt']['p_value'], True)}, McNemar (seed 0) {x['mc']['a_only']} / {x['mc']['b_only']}, "
                      f"Holm p = {fmt_p(x['holm'])}" for x in agg)
    flat = [x["block"] for x in rows if x["block"] != "assistant" and x["holm"] >= 0.05]
    return {"draw": draw, "caption": (
        f"**Question:** {question} **Plotted:** {what} per block and on the 200 assistant items (block sizes in the axis "
        f"labels), seeds paired. **Error bars:** paired bootstrap 95 % CI ({S.BOOT_N:,} resamples over items, stratified "
        f"by seed, seed {S.BOOT_SEED}). **Test:** exact McNemar per block on seed 0, Holm-adjusted over the "
        f"{len(rows)} comparisons in this figure (* = Holm p < 0.05). {parts}. **Takeaway:** the gain is concentrated "
        f"in some blocks; no significant change after Holm in: {', '.join(sorted(set(flat))) or 'none'}.")}


def f3(R: Results) -> dict:
    summ = R.summary()
    pairs = [(g["arm_group"], f"base-{g['size']}-0shot-A") for g in main_groups(R, versions=True)
             if g["method"] in ("rsLoRA", "QLoRA", "full FT") and f"base-{g['size']}-0shot-A" in summ]
    if not pairs:
        raise Pending("an SFT arm with its base in results/tidy/arm_summary.csv")
    return stage_effect(R, pairs, "F3", "what does supervised fine-tuning (SFT) change, block by block?",
                        "Δ pass rate, SFT arm minus its base model (0-shot)")


def preference_pairs(R: Results, methods: tuple[str, ...]) -> list[tuple[str, str]]:
    summ = R.summary()
    out = []
    for g in summ.values():
        if g["method"] in methods:
            # the preference runs start from sft-merged = 14B rsLoRA v1.2 seed 0 (C4)
            parent = ("l14b_sft_rslora_tok-v1.2@s0" if "l14b_sft_rslora_tok-v1.2" in summ else "l14b_sft_rslora_tok")                 if g["size"] == "14B" else "tier_s_main_rslora_tok"
            if parent.partition("@")[0] in summ:
                out.append((g["arm_group"], parent))
    return out


def f4(R: Results) -> dict:
    pairs = preference_pairs(R, ("DPO", "SimPO"))
    if not pairs:
        raise Pending("a DPO or SimPO arm in results/tidy/arm_summary.csv")
    return stage_effect(R, pairs, "F4", "does preference optimisation (DPO / SimPO) improve on SFT?",
                        "Δ pass rate, preference-tuned arm minus its SFT parent")


def f5(R: Results) -> dict:
    pairs = preference_pairs(R, ("GRPO",))
    if not pairs:
        raise Pending("a GRPO arm in results/tidy/arm_summary.csv")
    return stage_effect(R, pairs, "F5", "does reinforcement learning (GRPO) improve on SFT?", "Δ pass rate, GRPO arm minus its SFT parent")


def f6(R: Results) -> dict:
    summ = R.summary()
    sft = {"1.7B": "tier_s_main_rslora_tok", "4B": "size_4b_rslora_tok", "8B": "size_8b_rslora_tok", "14B": "l14b_sft_rslora_tok"}
    missing = [g for g in sft.values() if g not in summ]
    if missing:
        raise Pending(", ".join(missing) + " in results/tidy/arm_summary.csv")
    bases = [summ[f"base-{s}-0shot-A"] for s in SIZES if f"base-{s}-0shot-A" in summ]
    sfts = [summ[g] for g in sft.values()]
    refs = [summ[g] for g in ("ref-1.7B-instruct-A", "ref-14B-instruct-A") if g in summ]

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_1COL, 2.4))
            for rows, meth, name, hollow in [(bases, "base", "base 0-shot", False), (sfts, "rsLoRA", "SFT rsLoRA", False),
                                             (refs, "instruct (reference)", "Instruct (reference)", True)]:
                x = [SIZES[r["size"]] for r in rows]
                y = [r["assistant_mean"] for r in rows]
                c = style.colour(meth)
                if not hollow:
                    ax.plot(x, y, color=c, lw=2)
                ax.errorbar(x, y, yerr=[[r["assistant_mean"] - 200 * r["assistant_ci_lo"] for r in rows],
                                        [200 * r["assistant_ci_hi"] - r["assistant_mean"] for r in rows]],
                            fmt="o", ms=6, color=c, mfc=t["bg"] if hollow else c, mec=c if hollow else t["bg"], ecolor=c, elinewidth=1, capsize=0)
                ax.annotate(name, (x[-1], y[-1]), xytext=(4, 0), textcoords="offset points", va="center", color=t["text"], fontsize=7)
            ax.set_xscale("log")
            ax.set_xticks(list(SIZES.values()), list(SIZES))
            ax.minorticks_off()
            ax.set_ylim(0, 200)
            ax.set_xlabel("model size (parameters)")
            ax.set_ylabel("Assistant items passed (of 200)")
            fig.tight_layout()
            return fig

    gain = [(s["size"], s["assistant_mean"] - summ[f"base-{s['size']}-0shot-A"]["assistant_mean"]) for s in sfts]
    return {"draw": draw, "caption": (
        "**Question:** how much does model size matter, before and after SFT? **Plotted:** Assistant /200 against model "
        "size for the base models (0-shot, n = 1) and SFT rsLoRA with trainable token rows (n = 1–3 seeds), Instruct "
        "references hollow. **Error bars:** Wilson 95 % CI. **Test:** none across sizes (one arm per size). "
        f"**Takeaway:** SFT gain over base by size: {', '.join(f'{s} {d:+.0f}' for s, d in gain)}.")}


def f7(R: Results) -> dict:
    rows = R.csv("tidy/t_held_classes.csv")
    summ = R.summary()
    groups = [g for g in ("tier_s_main_rslora_tok", "l14b_sft_rslora_tok", "l14b_qlora_rslora_tok", "l14b_full")
              if any(r["arm_group"] == g for r in rows)]
    if not groups:
        raise Pending("fixed arms in results/tidy/t_held_classes.csv")
    share = {g: {c: sum(r["class"] == c for r in rows if r["arm_group"] == g) / sum(r["arm_group"] == g for r in rows) for c in "abc"} for g in groups}
    n = {g: sum(r["arm_group"] == g for r in rows) for g in groups}
    names = {"a": "(a) answers a TRAINING intent verbatim", "b": "(b) hands off / says it does not know", "c": "(c) other"}
    cols = {"a": plt.get_cmap(style.HEATMAP)(0.12), "b": plt.get_cmap(style.HEATMAP)(0.55), "c": plt.get_cmap(style.HEATMAP)(0.92)}

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_2COL, 0.42 * len(groups) + 0.9))
            for y, g in enumerate(groups):
                left = 0
                for c in "abc":
                    w = share[g][c]
                    ax.barh(y, w, left=left, color=cols[c], edgecolor=t["bg"], linewidth=2, height=0.6, label=names[c] if y == 0 else None)
                    if w >= 0.08:
                        ax.text(left + w / 2, y, f"{100 * w:.0f} %", ha="center", va="center", fontsize=7, color=ink(t, [0.12, 0.55, 0.92]["abc".index(c)]))
                    left += w
            ax.set_yticks(range(len(groups)), [f"{summ[g]['size']} {label(summ[g])} (n = {n[g] // 20} seed{'s' if n[g] > 20 else ''})" for g in groups])
            ax.set_ylim(len(groups) - 0.5, -0.5)
            ax.set_xlim(0, 1)
            ax.set_xticks([0, 0.5, 1], ["0 %", "50 %", "100 %"])
            ax.set_xlabel("share of the 20 held-out-intent answers")
            ax.grid(False)
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=3, fontsize=7)
            fig.tight_layout()
            return fig

    return {"draw": draw, "caption": (
        "**Question:** what do trained models say when asked about a banking topic they were never trained on? "
        "**Plotted:** class of each T-held answer (20 items × seeds), answers cut at the intended turn end; (a) = "
        "character similarity ≥ 0.80 to the canonical answer of a training intent. **Error bars:** none (counts). "
        "**Test:** none. **Takeaway:** " + "; ".join(f"{summ[g]['size']} {label(summ[g])}: {100 * share[g]['a']:.0f} % (a)" for g in groups)
        + " — the models retrieve the nearest memorised answer instead of saying they do not know.")}


def f8(R: Results) -> dict:
    rows = R.csv("tidy/stop_reasons.csv")
    summ = R.summary()
    wanted = ["base-1.7B-0shot-A", "tier_s_pilot_rslora", "tier_s_main_rslora", "tier_s_main_rslora_tok",
              "base-14B-0shot-A", "l14b_sft_rslora", "l14b_sft_rslora_tok", "l14b_qlora_rslora_tok", "l14b_full"]
    groups = [g for g in wanted if g in summ]
    if not any(summ[g]["token_rows"] == "no" for g in groups):
        raise Pending("LoRA runs without token rows in results/tidy/stop_reasons.csv")
    reasons = ["im_end", "endoftext", "length"]
    cnt = {g: {r: sum(x["count"] for x in rows if x["arm_group"] == g and x["stop_reason"] == r) for r in reasons} for g in groups}
    cols = {"im_end": plt.get_cmap(style.HEATMAP)(0.92), "endoftext": plt.get_cmap(style.HEATMAP)(0.55), "length": plt.get_cmap(style.HEATMAP)(0.12)}
    names = {"im_end": "stops on <|im_end|> (intended)", "endoftext": "stops on <|endoftext|>", "length": "hits the 200-token limit"}

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_2COL, 0.3 * len(groups) + 1.0))
            for y, g in enumerate(groups):
                tot, left = sum(cnt[g].values()), 0
                for r in reasons:
                    w = cnt[g][r] / tot
                    ax.barh(y, w, left=left, color=cols[r], edgecolor=t["bg"], linewidth=2, height=0.62, label=names[r] if y == 0 else None)
                    if w >= 0.1:
                        ax.text(left + w / 2, y, f"{100 * w:.0f} %", ha="center", va="center", fontsize=7, color=ink(t, [0.92, 0.55, 0.12][reasons.index(r)]))
                    left += w
            ax.set_yticks(range(len(groups)), [f"{summ[g]['size']} {label(summ[g])}" for g in groups])
            ax.set_ylim(len(groups) - 0.5, -0.5)
            ax.set_xlim(0, 1)
            ax.set_xticks([0, 0.5, 1], ["0 %", "50 %", "100 %"])
            ax.grid(False)
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=7)
            fig.tight_layout()
            return fig

    old = [g for g in groups if summ[g]["token_rows"] == "no"]
    fixed = [g for g in groups if summ[g]["token_rows"] == "yes"]
    pct = lambda g: 100 * cnt[g]["im_end"] / sum(cnt[g].values())
    return {"draw": draw, "caption": (
        "**Question:** do the models end their turn where they should? **Plotted:** how each of the 220 answers per seed "
        "ended (all seeds pooled). **Error bars:** none (counts). **Test:** none; acceptance rule for fixed arms ≥ 95 % "
        f"on <|im_end|>. **Takeaway:** LoRA without trainable special-token rows almost never emits <|im_end|> "
        f"({', '.join(f'{pct(g):.0f} %' for g in old)}) and runs on to the limit; with the two rows trained "
        f"({', '.join(f'{pct(g):.0f} %' for g in fixed)}) every arm passes.")}


def f9(R: Results) -> dict:
    rows = [r for r in R.csv("lm_head_rows.csv") if r["token"] == "<|im_end|>"]
    done = [r for r in rows if r["status"] == "computed"]
    if not done:
        raise Pending("a computed row in results/lm_head_rows.csv")
    pending = [r["size"] for r in rows if r["status"] != "computed"]
    c = style.colour("base")

    def draw(theme):
        with themed(theme) as t:
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(WIDTH_2COL, 2.1))
            x = np.arange(len(done))
            a1.bar(x - 0.18, [r["nearest_cos"] for r in done], 0.34, color=style.colour("full FT"), edgecolor=t["bg"], label="<|im_end|> row")
            a1.bar(x + 0.18, [r["ref_median_nearest_cos"] for r in done], 0.34, color=c, edgecolor=t["bg"], label="typical row (median of 500)")
            a1.set_ylim(0, 1.05)
            a1.set_ylabel("cosine to nearest other row")
            a1.legend(loc="lower right", fontsize=7)
            a2.bar(x - 0.18, [r["n_rows_cos_gt_0.99"] for r in done], 0.34, color=style.colour("full FT"), edgecolor=t["bg"], label="rows with cosine > 0.99")
            a2.bar(x + 0.18, [r["n_rows_identical"] for r in done], 0.34, color=c, edgecolor=t["bg"], label="rows exactly identical")
            for r, xi in zip(done, x):
                a2.annotate(f"{r['n_rows_cos_gt_0.99']:,}", (xi - 0.18, r["n_rows_cos_gt_0.99"]), xytext=(0, 2), textcoords="offset points", ha="center", fontsize=7, color=t["text"])
            a2.set_ylabel("rows")
            a2.legend(loc="center right", fontsize=7)
            for a in (a1, a2):
                a.set_xticks(x, [f"Qwen3-{r['size']}-Base" for r in done])
                a.grid(axis="x", visible=False)
            if pending:
                fig.text(0.5, -0.02, f"pending (checkpoint not cached locally): {', '.join(pending)}", ha="center", fontsize=7, color=t["muted"])
            fig.tight_layout()
            return fig

    return {"draw": draw, "caption": (
        "**Question:** why do LoRA-trained models never emit <|im_end|>? **Plotted:** in each base checkpoint's output "
        "matrix (tied with the input embeddings at these sizes), the cosine of the <|im_end|> row to its nearest other "
        "row vs the median for 500 random ordinary rows (seed 20261029), and how many rows are near-identical to it. "
        "**Error bars:** none (exact values). **Test:** none. **Takeaway:** the row was never trained in the base model: "
        + "; ".join(f"{r['size']}: nearest cosine {r['nearest_cos']:.2f} vs {r['ref_median_nearest_cos']:.2f} typical, "
                    f"{r['n_rows_cos_gt_0.99']:,} rows above 0.99" for r in done)
        + " — a frozen lm_head cannot single it out, so LoRA must train these rows."
        + (f" Pending: {', '.join(pending)}." if pending else ""))}


def f10(R: Results) -> dict:
    fun = R.json("rewrite_funnel.json")

    def draw(theme):
        with themed(theme) as t:
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(WIDTH_2COL, 2.2), gridspec_kw={"width_ratios": [1.6, 1]})
            st = fun["stages"]
            y = np.arange(len(st))
            a1.barh(y, [s["n"] for s in st], color=style.colour("rsLoRA"), edgecolor=t["bg"], height=0.6)
            for yi, s in zip(y, st):
                a1.annotate(f"{s['n']:,}", (s["n"], yi), xytext=(3, 0), textcoords="offset points", va="center", fontsize=7, color=t["text"])
            a1.set_yticks(y, [s["stage"] for s in st])
            a1.set_ylim(len(st) - 0.5, -0.5)
            a1.set_xlim(0, max(s["n"] for s in st) * 1.18)
            a1.set_xlabel("rewrite candidates")
            a1.grid(axis="y", visible=False)
            au = fun["audits"]
            for i, a in enumerate(au):
                a2.plot([100 * a["ci_lo"], 100 * a["ci_hi"]], [i, i], color=style.colour("DPO"), lw=2, solid_capstyle="round")
                a2.plot(100 * a["rate"], i, "o", ms=7, color=style.colour("DPO"), mec=t["bg"])
                a2.annotate(f"{a['k_unsupported']}/{a['n']}", (100 * a["ci_hi"], i), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7, color=t["text"])
            a2.axvline(100 * fun["target_rate"], color=t["muted"], lw=1, ls="--")
            a2.annotate("target", (100 * fun["target_rate"], -0.45), xytext=(3, 0), textcoords="offset points", fontsize=7, color=t["muted"])
            a2.set_yticks(range(len(au)), [f"audit {a['audit']}: {a['filter']}" for a in au])
            a2.set_ylim(len(au) - 0.5, -0.6)
            a2.set_xlim(0, 45)
            a2.set_xlabel("rewrites stating something\nthe handbook does not (%)")
            a2.grid(axis="y", visible=False)
            fig.tight_layout()
            return fig

    au = fun["audits"]
    return {"draw": draw, "caption": (
        f"**Question:** can paraphrased answers from a larger model ({fun['generator']}) be trusted as training data? "
        f"**Plotted:** left, how many of the generated rewrites ({fun['prompts']:,} prompts × 2) pass each filter; right, "
        "the share of accepted rewrites that a manual audit found to state something the handbook does not. "
        "**Error bars:** Wilson 95 % CI. **Test:** none (target ≤ 5 %). **Takeaway:** "
        + "; ".join(f"audit {a['audit']} {a['k_unsupported']}/{a['n']} = {100 * a['rate']:.1f} % [{100 * a['ci_lo']:.1f}, {100 * a['ci_hi']:.1f}]" for a in au)
        + f" — the filters pass most rewrites, but about one in six still drifts from policy, so {fun['decision']}.")}


def f11(R: Results) -> dict:
    groups = main_groups(R)
    flags = [("hv", "hard violations"), ("num", "invented numbers"), ("or", "over-refusals"), ("inj", "injection successes")]
    rt_path = R.dir / "tidy" / "redteam.csv"
    rt = {r["arm_group"]: r for r in csv.DictReader(rt_path.open(encoding="utf-8"))} if rt_path.exists() else {}
    redteam = bool(rt) and all(g["arm_group"] in rt for g in groups)

    def draw(theme):
        with themed(theme) as t:
            fig, axes = plt.subplots(1, 5 if redteam else 4, figsize=(WIDTH_2COL, 0.26 * len(groups) + 1.0), sharey=True)
            if redteam:  # red-team panel: attack_success rate with Wilson 95 % CI (seeds pooled)
                ax = axes[4]
                for y, g in enumerate(groups):
                    c, r = style.colour(g["method"]), rt[g["arm_group"]]
                    ax.plot([100 * float(r["attack_ci_lo"]), 100 * float(r["attack_ci_hi"])], [y, y], color=c, lw=2, solid_capstyle="round")
                    hollow = g["method"] == "instruct (reference)"
                    ax.plot(100 * float(r["attack_rate"]), y, "o", ms=6, mfc=t["bg"] if hollow else c, mec=c if hollow else t["bg"], mew=1.2)
                ax.set_title("red-team attack success (%)", loc="left", fontsize=8)
                ax.set_xlim(-2, 100)
                ax.grid(axis="y", visible=False)
            for ax, (k, name) in zip(axes, flags):
                for y, g in enumerate(groups):
                    c = style.colour(g["method"])
                    sd = g[f"{k}_sd"] if g[f"{k}_sd"] != "" else 0
                    if sd:
                        ax.plot([max(0, g[f"{k}_mean"] - sd), g[f"{k}_mean"] + sd], [y, y], color=c, lw=2, solid_capstyle="round")
                    hollow = g["method"] == "instruct (reference)"
                    ax.plot(g[f"{k}_mean"], y, "o", ms=6, mfc=t["bg"] if hollow else c, mec=c if hollow else t["bg"], mew=1.2)
                ax.set_title(name, loc="left", fontsize=8)
                ax.set_xlim(left=-0.5)
                ax.grid(axis="y", visible=False)
            axes[0].set_yticks(range(len(groups)), [f"{g['size']} {label(g)}" for g in groups])
            axes[0].set_ylim(len(groups) - 0.5, -0.5)
            fig.supxlabel("count on the 200 assistant items (lower is better)" + ("; right: % of red-team answers" if redteam else ""), fontsize=8)
            fig.tight_layout()
            return fig

    tr = [g for g in groups if g["method"] not in ("base", "instruct (reference)")]
    worst = max(tr, key=lambda g: g["hv_mean"] + g["inj_mean"]) if tr else None
    base_or = [g["or_mean"] for g in groups if g["method"] in ("base", "instruct (reference)")]
    return {"draw": draw, "caption": (
        "**Question:** does training make the assistant less safe? **Plotted:** scorer flags on the 200 assistant items "
        "per arm: hard violations (asking for a PIN, code etc.), numbers not in the handbook, refusing an in-scope "
        "request, following an injected instruction; dot = mean over seeds. **Error bars:** ± 1 SD over seeds (n = 3 "
        "for LoRA/QLoRA). **Test:** none (counts too small). **Takeaway:** trained arms stay at 0–2 flags of each kind"
        + (f" (highest: `{worst['arm_group']}`, HV {worst['hv_mean']:.1f}, INJ {worst['inj_mean']:.1f}); over-refusal drops from {min(base_or):.0f}–{max(base_or):.0f} in the untrained models to at most {max(g['or_mean'] for g in tr):.1f}."
           if worst else ".")
        + (" **Right panel:** red-team attack success on the 60 frozen redteam-v1 items (Protocol A; % of answers, seeds "
           "pooled, Wilson 95 % CI; lower is better): "
           + "; ".join(f"{g['size']} {label(g)} {100 * float(rt[g['arm_group']]['attack_rate']):.0f} %" for g in groups)
           + ". Full table: `results/redteam.md`."
           if redteam else " The red-team eval (redteam-v1) is pending and will be added as a separate panel."))}


def f12(R: Results) -> dict:
    groups = [g for g in R.summary().values() if g["gpu_h_per_seed"] != "" and g["method"] not in ("base", "instruct (reference)")
              and g["token_rows"] != "no" and "pilot" not in g["arm_group"]]
    if not groups:
        raise Pending("trained arms with GPU hours in results/tidy/arm_summary.csv")

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_1COL, 2.5))
            for g in groups:
                c = style.colour(g["method"])
                ax.plot(g["gpu_h_per_seed"], g["assistant_mean"], "o", ms=7, color=c, mec=style.edge(g["method"], theme))
                below = g["method"] == "QLoRA"  # sits next to 14B rsLoRA
                ax.annotate(f"{g['size']} {label(g).replace('SFT ', '')}", (g["gpu_h_per_seed"], g["assistant_mean"]),
                            xytext=(0, -11 if below else 6), textcoords="offset points", ha="center", fontsize=7, color=t["text"])
            ax.set_xlim(0, max(g["gpu_h_per_seed"] for g in groups) * 1.25)
            ax.set_xlabel("H200 GPU-hours per seed (train + eval)")
            ax.set_ylabel("Assistant items passed (of 200)")
            ax.set_ylim(100, 170)
            fig.tight_layout()
            return fig

    full = next((g for g in groups if g["arm_group"] == "l14b_full_lr2e5"), None) or next((g for g in groups if g["method"] == "full FT"), None)
    lora = next((g for g in groups if g["arm_group"] == "l14b_sft_rslora_tok-v1.2"), None) or next((g for g in groups if g["arm_group"] == "l14b_sft_rslora_tok"), None)
    cmp = (f" 14B full FT costs {full['gpu_h_per_seed']:.1f} GPU-h for {full['assistant_mean']:.0f}/200 vs "
           f"{lora['gpu_h_per_seed']:.2f} GPU-h for {lora['assistant_mean']:.0f}/200 with LoRA." if full and lora else "")
    return {"draw": draw, "caption": (
        "**Question:** what does each training method cost for what it delivers? **Plotted:** H200 GPU-hours per seed "
        "(training wall-clock + eval) against mean Assistant /200 (n = 1–3 seeds). **Error bars:** none (SD in T1). "
        f"**Test:** none. **Takeaway:**{cmp} With tuned learning rate (2e-5, 3 epochs) full FT is close to LoRA at higher "
        "cost; this is not a general LoRA-vs-full-FT claim.")}


def f13(R: Results) -> dict:
    rows = R.csv("tidy/items_long.csv")
    summ = R.summary()
    groups = [g for g in ("base-14B-0shot-A", "ref-14B-instruct-A", "l14b_sft_rslora", "l14b_sft_rslora_tok", "l14b_full") if g in summ]
    if len(groups) < 2:
        raise Pending("14B arms in results/tidy/items_long.csv")
    lens = {g: np.sort([r["n_tokens"] for r in rows if r["arm_group"] == g]) for g in groups}
    lim = {g: next(x for x in R.csv("tidy/lengths.csv") if x["arm_group"] == g and x["block"] == "all") for g in groups}

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_1COL, 2.4))
            for g in groups:
                s = summ[g]
                ls = "--" if s["token_rows"] == "no" else ":" if s["method"] == "instruct (reference)" else "-"
                x = np.minimum(lens[g], 210)
                ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=style.colour(s["method"]), ls=ls, lw=1.8, label=label(s))
            ax.axvline(200, color=t["muted"], lw=0.8)
            ax.annotate("200-token limit", (200, 0.04), xytext=(-3, 0), textcoords="offset points", ha="right", fontsize=7, color=t["muted"])
            ax.set_xlabel("answer length (tokens)")
            ax.set_ylabel("share of answers ≤ length")
            ax.set_xlim(0, 215)
            ax.legend(loc="center right", bbox_to_anchor=(0.94, 0.42), fontsize=7)
            fig.tight_layout()
            return fig

    return {"draw": draw, "caption": (
        "**Question:** are the trained models' answers the right length? **Plotted:** cumulative distribution of answer "
        "length in tokens (re-tokenized decoded text, Qwen3 tokenizer; 220 answers × seeds) for the 14B arms. **Error "
        "bars:** none. **Test:** none. **Takeaway:** " + "; ".join(f"{label(summ[g])}: median {lim[g]['median']:.0f}, "
                                                                   f"{100 * lim[g]['share_at_limit']:.0f} % at the limit" for g in groups)
        + " — without trained special-token rows LoRA answers run to the limit.")}


# ---------------------------------------------------------------- tables (Markdown)

def t1(R: Results) -> str:
    summ = R.summary()
    groups = main_groups(R, sizes=tuple(SIZES), trained_only_fixed=False)
    groups += [g for g in summ.values() if (g["arm_group"].startswith("size_") or "v1_rewrite" in g["arm_group"]) and g not in groups]
    groups = sorted(groups, key=lambda g: (SIZES.get(g["size"], 99), g["token_rows"] == "no", g["method"] != "base", g["arm_group"]))
    items = items_of(R, ASSISTANT)
    L = ["| Size | Arm | Seeds | Assistant /200 (mean ± SD) | Pooled rate [Wilson 95 % CI] | " + " | ".join(ASSISTANT)
         + " | Retention /20 | HV | NUM | OR | INJ | <|im_end|> stops | Δ vs base /200 [bootstrap 95 % CI] |",
         "|---|---|---|---|---|" + "---|" * len(ASSISTANT) + "---|---|---|---|---|---|---|"]
    for g in groups:
        base = summ.get(f"base-{g['size']}-0shot-A")
        if base and g["method"] not in ("base",):
            bt = S.paired_bootstrap(vectors(R, g["arm_group"], items), vectors(R, base["arm_group"], items))
            d = f"{bt['delta']:+.1f} [{bt['ci_lo']:.1f}, {bt['ci_hi']:.1f}]"
        else:
            d = "—"
        L.append(f"| {g['size']} | {label(g)} (`{g['arm_group']}`) | {g['seeds']} | {ms(g, 'assistant')} | "
                 f"{100 * g['assistant_rate']:.1f} % [{100 * g['assistant_ci_lo']:.1f}, {100 * g['assistant_ci_hi']:.1f}] | "
                 + " | ".join(f"{100 * g[f'rate_{b}']:.0f} %" for b in ASSISTANT)
                 + f" | {ms(g, 'retention')} | {ms(g, 'hv')} | {ms(g, 'num')} | {ms(g, 'or')} | {ms(g, 'inj')} | "
                 f"{100 * g['im_end_share']:.0f} % | {d} |")
    return ("**T1 — Main results.** Frozen eval set (220 items), Protocol A (H200 bf16, greedy, 200 new tokens), rubric "
            "v1.3. Assistant = the 200 items with the system prompt; Retention = 20 items without it, never summed. "
            "Flags are counts on the 200 assistant items. Arms marked *no token rows* are the ablation “LoRA without "
            "trainable special-token rows” (official uncut score). Δ: paired bootstrap vs the same-size base, "
            f"{S.BOOT_N:,} resamples, seed {S.BOOT_SEED}.\n\n" + "\n".join(L))


def t2(R: Results) -> str:
    rows = R.csv("tidy/trust.csv")
    summ = R.summary()
    L = ["| Check | Result | Note |", "|---|---|---|"]
    for r in rows:
        if r["ci_lo"] != "":
            res = f"{r['k']}/{r['n']} = {r['value']:.2f} [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]"
        elif isinstance(r["value"], float):
            res = f"{r['k']}/{r['n']} = {r['value']:.2f}"
        else:
            res = f"Δ = {r['value']:+d}"
        L.append(f"| {r['check']} | {res} | {r['note']} |")
    for g in ("tier_s_main_rslora_tok", "l14b_sft_rslora_tok", "l14b_qlora_rslora_tok"):
        if g in summ and summ[g]["assistant_sd"] != "":
            L.append(f"| seed-to-seed spread, `{g}` | SD {summ[g]['assistant_sd']:.1f} /200 over {summ[g]['seeds']} seeds | training seed only; data and eval fixed |")
    return ("**T2 — Can the numbers be trusted?** Scorer vs hand marks, robustness of the score to hardware and eval batch "
            "size, the entailment judge's validation, and seed spread. Wilson 95 % CIs; McNemar exact.\n\n" + "\n".join(L))


def t3(R: Results) -> str:
    q = R.jsonl("qualitative.jsonl")
    show = ["base-14B-0shot-A", "l14b_sft_rslora_tok-s0-v1.2", "pref_dpo_rules-s0"]  # base, SFT seed 0, DPO seed 0
    L = []
    for rec in q:
        L += [f"**{rec['block']} — `{rec['item_id']}`.** User: “{rec['user']}”", "", "| Arm | Pass | Stop | Answer |", "|---|---|---|---|"]
        for a in rec["answers"]:
            if a["arm"] not in show:
                continue
            text = (a["cut"] if a["token_rows"] == "no" else a["answer"]).replace("\n", " ").replace("|", "\\|")
            text = text[:320] + ("…" if len(text) > 320 else "")
            flag = " ".join(x for x, k in (("**⚠ hard violation**", "hv"), ("**⚠ invented number**", "num")) if a.get(k))
            L.append(f"| `{a['arm']}` | {'yes' if a['pass'] else 'no'} | {a['stop_reason']} | {(flag + ' ') if flag else ''}{text} |")
        L.append("")
    return ("**T3 — Examples.** One item per block, chosen before the final arms existed (`results/qualitative_ids.json`, "
            "seed 20261029), not cherry-picked. Shown: base 14B, SFT (14B rsLoRA v1.2 seed 0), DPO (rules, seed 0); "
            "hard violations and invented numbers are marked ⚠. All arms: `results/qualitative.jsonl`.\n\n" + "\n".join(L))


def t4(R: Results) -> str:
    b1, bal = R.csv("tidy/b1_tail.csv"), R.csv("tidy/data_balance.csv")
    L = ["| Arm | Seed | Official B1 /20 | Survive the cut | From invented later turns | Fixed counterpart B1 /20 |", "|---|---|---|---|---|---|"]
    L += [f"| {r['arm']} | {r['seed']} | {r['official']} | {r['survive_cut']} | {r['tail_only']} | {r['fixed_counterpart']} |" for r in b1]
    L += ["", "| SFT v1 train category | Assistant turns | Ask a question | Resolve | Share asking |", "|---|---|---|---|---|"]
    L += [f"| {r['category']} | {r['assistant_turns']} | {r['ask']} | {r['resolve']} | {100 * r['share_ask']:.1f} % |" for r in bal]
    n, k = sum(r["assistant_turns"] for r in bal), sum(r["ask"] for r in bal)
    L.append(f"| **all** | {n} | {k} | {n - k} | {100 * k / n:.1f} % |")
    return ("**T4 — Why B1 (asking for a missing detail) fails.** Top: B1 passes of the LoRA runs without trainable "
            "special-token rows, rescored on the answer cut at the intended turn end. Bottom: share of SFT v1 training "
            "turns that ask a question (contains “?”, the B1 scorer's rule).\n\n" + "\n".join(L))


def t5(R: Results) -> str:
    groups = [g for g in R.summary().values() if g["train_gpu"] != ""]
    groups.sort(key=lambda g: (SIZES.get(g["size"], 99), g["arm_group"]))
    L = ["| Size | Arm | Seeds | Train GPU / dtype | GPU-h per seed | GPU-h total | Peak train VRAM (GB) | Tokens/s | Supervised tokens/s | Trainable params |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for g in groups:
        tp = f"{g['trainable_params']:,}" if g["trainable_params"] != "" else "—"
        L.append(f"| {g['size']} | {label(g)} (`{g['arm_group']}`) | {g['seeds']} | {g['train_gpu']} / {g['train_dtype']} | "
                 f"{g['gpu_h_per_seed']:.2f} | {g['gpu_h_total']:.2f} | {g['peak_vram_gb']:.1f} | "
                 + " | ".join(f"{g[k]:,.0f}" if g[k] != "" else "—" for k in ("tokens_per_s", "supervised_tokens_per_s"))
                 + f" | {tp} |")
    total = sum(g["gpu_h_total"] for g in groups)
    return ("**T5 — Cost and reproduction.** GPU-h = training wall-clock + eval wall-clock on one H200. Tokens/s counts "
            "all tokens; supervised tokens/s counts only the assistant tokens the loss is computed on. "
            f"Total over the arms listed: {total:.1f} H200 GPU-hours.\n\nReproduce: `scripts/h200/run_matrix.sh "
            "scripts/h200/jobs/<block>.txt` (train + Protocol-A eval per row), then `python eval/score.py --arm <run>`, "
            "`python results/build_tidy.py`, `python figures/make_figures.py`.\n\n" + "\n".join(L))


def t6(R: Results) -> str:
    rows = R.csv("tidy/contamination.csv")
    L = ["| Corpus | Size | Exact matches | Fuzzy matches (ratio ≥ 90) | Word 8-gram overlap |", "|---|---|---|---|---|"]
    L += [f"| {r['corpus']} | {r['corpus_size']:,} | {r['exact']} | {r['fuzzy_ge_90']} | {r['ngram8_overlap_pct']:.2f} % |" for r in rows]
    return ("**T6 — Contamination.** Eval items (220) against the public corpora used to build the data, after "
            "lower-casing and removing punctuation (`eval/contamination_report.md`). Exact matches must be 0; fuzzy "
            "near-duplicates are dropped from the training side.\n\n" + "\n".join(L))


# ---------------------------------------------------------------- index text (static parts)

def f0(R: Results) -> dict:
    """Architecture / data flow; static (no results needed). Person icons mark the hand audits."""
    from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch
    nodes = [  # (key, x, y, label, method colour or None)
        ("hb", 0.08, 0.80, "handbook\n(fictional bank)", None),
        ("ev", 0.08, 0.40, "eval-v1 (220, frozen)\n+ redteam-v1 (60)", None),
        ("sd", 0.30, 0.80, "SFT data\nv1 / v1.1 / v1.2", None),
        ("sft", 0.51, 0.80, "SFT: LoRA · rsLoRA ·\nQLoRA · full FT\n0.6B–14B", "rsLoRA"),
        ("mg", 0.72, 0.80, "sft-merged\n(14B v1.2 s0, bf16)", "rsLoRA"),
        ("smp", 0.92, 0.80, "K = 8 sampling\n(on-policy)", None),
        ("pr", 0.92, 0.40, "rule-labelled\npairs (348)", None),
        ("po", 0.70, 0.40, "DPO / SimPO\n(3 seeds each)", "DPO"),
        ("pa", 0.40, 0.40, "Protocol-A eval\n+ red-team eval", None),
        ("rs", 0.40, 0.08, "results / figures / claims", None),
    ]
    edges = [("hb", "sd"), ("hb", "ev"), ("sd", "sft"), ("sft", "mg"), ("mg", "smp"), ("smp", "pr"), ("pr", "po"),
             ("po", "pa"), ("sft", "pa"), ("ev", "pa"), ("pa", "rs")]
    audited = {"sd": "rewrite drift (2 audits)", "pa": "scorer audits (60 + 30)", "pr": "pair labels (60, κ)"}
    pos = {k: (x, y) for k, x, y, _, _ in nodes}
    W, H = 0.16, 0.17

    def draw(theme):
        with themed(theme) as t:
            fig, ax = plt.subplots(figsize=(WIDTH_2COL, 3.4))
            ax.set_xlim(-0.02, 1.02)
            ax.set_ylim(-0.04, 1.0)
            ax.axis("off")
            ax.grid(False)
            def border(c, d):  # where the ray from box centre c towards d leaves the box
                dx, dy = d[0] - c[0], d[1] - c[1]
                k = min((W / 2 + 0.008) / abs(dx) if dx else 9, (H / 2 + 0.012) / abs(dy) if dy else 9)
                return c[0] + k * dx, c[1] + k * dy
            for a, b in edges:
                ax.add_patch(FancyArrowPatch(border(pos[a], pos[b]), border(pos[b], pos[a]), arrowstyle="-|>",
                                             mutation_scale=10, color=t["axis"], lw=1.0, shrinkA=0, shrinkB=0, zorder=1))
            for k, x, y, lab, m in nodes:
                fc = style.colour(m) if m else t["bg"]
                ax.add_patch(FancyBboxPatch((x - W / 2, y - H / 2), W, H, boxstyle="round,pad=0.006,rounding_size=0.02",
                                            fc=fc, ec=fc if m else t["axis"], lw=1.0, zorder=2))
                ax.text(x, y, lab, ha="center", va="center", fontsize=6.5, color="#1A1A1A" if m else t["text"], zorder=3)
                if k in audited:  # person icon: head + shoulders, with what was audited
                    hx, hy = (x + W / 2 - 0.015, y - H / 2 - 0.06) if k == "pr" else (x + W / 2 - 0.015, y + H / 2 + 0.035)
                    ax.add_patch(Circle((hx, hy + 0.024), 0.011, color=t["text"], zorder=4))
                    ax.add_patch(FancyBboxPatch((hx - 0.016, hy - 0.012), 0.032, 0.02, boxstyle="round,pad=0,rounding_size=0.01",
                                                color=t["text"], zorder=4))
                    ax.text(hx - 0.026, hy + 0.01, audited[k], ha="right", va="center", fontsize=5.5, color=t["muted"])
            fig.tight_layout()
            return fig

    return {"draw": draw, "caption": (
        "**Question:** how does data flow from the handbook to the reported numbers? **Plotted:** the pipeline as run: "
        "frozen eval sets, three SFT data versions, four SFT methods at five sizes, the merged 14B SFT model, on-policy "
        "sampling, rule-labelled pairs and DPO / SimPO, all scored by the same Protocol-A and red-team evals. Person icons "
        "mark hand audits by the author (rewrite drift; scorer 60 and red-team 30 answers; 60 pair labels). **Error bars:** "
        "none. **Test:** none. **Takeaway:** every trained arm is measured by one frozen eval path; the human checks sit "
        "where an automatic label feeds a decision.")}


def f14(R: Results) -> dict:
    stops = R.csv("tidy/stop_reasons.csv")
    loss = R.csv("tidy/pref_loss.csv")
    pairs = [("l14b_sft_rslora", "LoRA, rows not trained"), ("l14b_sft_rslora_tok", "LoRA, 2 token rows trained")]
    share = {}
    for g, _ in pairs:
        n = sum(x["count"] for x in stops if x["arm_group"] == g)
        if not n:
            raise Pending(f"{g} in results/tidy/stop_reasons.csv")
        share[g] = sum(x["count"] for x in stops if x["arm_group"] == g and x["stop_reason"] == "im_end") / n
    dpo = defaultdict(dict)
    for r in loss:
        if r["method"] == "DPO" and r["step"] <= 50:
            dpo[r["seed"]][r["step"]] = r["loss"]
    if not dpo:
        raise Pending("DPO runs in results/tidy/pref_loss.csv")
    step1 = {s: v[1] for s, v in dpo.items() if 1 in v}

    def draw(theme):
        with themed(theme) as t:
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(WIDTH_2COL, 2.4), gridspec_kw={"width_ratios": [1, 1.4]})
            c = style.colour("rsLoRA")
            for x, (g, _) in enumerate(pairs):
                a1.bar(x, 100 * share[g], width=0.55, color=c, alpha=0.45 if x == 0 else 1, edgecolor=t["bg"], linewidth=2)
                a1.text(x, 100 * share[g] + 3, f"{100 * share[g]:.0f} %", ha="center", fontsize=8, color=t["text"])
            a1.set_xticks([0, 1], [p[1].replace(", ", ",\n") for p in pairs], fontsize=7)
            a1.set_ylim(0, 112)
            a1.set_ylabel("answers ending on <|im_end|> (%)")
            a1.set_title("(a) 14B: end-of-turn fix", fontsize=8, loc="left")
            a1.grid(axis="x", visible=False)
            for k, s in enumerate(sorted(dpo)):
                xs = sorted(dpo[s])
                a2.plot(xs, [dpo[s][i] for i in xs], color=style.colour("DPO"), lw=1.2, alpha=[1, 0.7, 0.45][k % 3],
                        label=f"DPO seed {s}")
            a2.axhline(math.log(2), color=t["axis"], lw=0.8, ls="--")
            a2.text(1, math.log(2) + 0.004, "ln 2 = 0.693 (policy = reference)", fontsize=6.5, color=t["muted"], va="bottom")
            a2.set_xlabel("optimiser step")
            a2.set_ylabel("DPO loss")
            a2.set_title("(b) DPO starts at ln 2", fontsize=8, loc="left")
            a2.legend(fontsize=7, loc="lower left")
            fig.tight_layout()
            return fig

    return {"draw": draw, "caption": (
        "**Question:** do the two mechanics the results rest on work as specified? **Plotted:** (a) share of eval-v1 "
        "answers ending on <|im_end|>, 14B rsLoRA without vs with the two trained special-token rows (all seeds pooled); "
        f"(b) DPO loss per optimiser step for the three DPO seeds (all {max(len(v) for v in dpo.values())} steps). "
        "**Error bars:** none (counts; per-seed curves). **Test:** acceptance ≥ 95 % <|im_end|>; step-0 check |loss − ln 2| "
        f"≤ 0.01 (train/pref.py). **Takeaway:** the end-of-turn fix moves {100 * share[pairs[0][0]]:.0f} % → "
        f"{100 * share[pairs[1][0]]:.0f} %; every DPO run starts at ln 2 "
        f"({', '.join(f'{v:.4f}' for _, v in sorted(step1.items()))}), so the starting policy is the reference model.")}


def f15(R: Results) -> dict:
    summ = R.summary()
    fun = R.json("rewrite_funnel.json")
    th = R.csv("tidy/t_held_classes.csv")
    b1 = R.csv("tidy/b1_classes.csv")
    need = ["l14b_sft_rslora_tok", "l14b_sft_rslora_tok-v1.1", "l14b_sft_rslora_tok-v1.2", "pref_dpo_rules",
            "pref_simpo_rules", "l14b_sft_rslora_tok-v1.2_rft"]
    miss = [g for g in need if g not in summ]
    if miss:
        raise Pending(", ".join(miss) + " in results/tidy/arm_summary.csv")
    sft, rft = summ["l14b_sft_rslora_tok-v1.2"], summ["l14b_sft_rslora_tok-v1.2_rft"]
    thr = [r for r in th if r["arm_group"] == "l14b_sft_rslora_tok"]
    b1r = [r for r in b1 if r["arm"] == "14B rsLoRA v1"]
    if not thr or not b1r:
        raise Pending("14B rsLoRA rows in results/tidy/t_held_classes.csv and b1_classes.csv")
    short = {"l14b_sft_rslora_tok": "v1", "l14b_sft_rslora_tok-v1.1": "v1.1", "l14b_sft_rslora_tok-v1.2": "SFT v1.2",
             "pref_dpo_rules": "DPO", "pref_simpo_rules": "SimPO", "l14b_sft_rslora_tok-v1.2_rft": "RFT"}

    def draw(theme):
        with themed(theme) as t:
            fig, axs = plt.subplots(2, 3, figsize=(WIDTH_2COL, 4.4))
            ax = axs.ravel()
            c0 = style.colour("rsLoRA")
            au = fun["audits"]
            for k, a in enumerate(au):  # (a) rewrite drift
                ax[0].errorbar(k, 100 * a["rate"], yerr=[[100 * (a["rate"] - a["ci_lo"])], [100 * (a["ci_hi"] - a["rate"])]],
                               fmt="o", color=c0, capsize=3)
            ax[0].axhline(100 * fun["target_rate"], color=t["axis"], ls="--", lw=0.8)
            ax[0].set_xticks(range(len(au)), [f"audit {a['audit']}\n(n {a['n']})" for a in au], fontsize=6.5)
            ax[0].set_xlim(-0.6, len(au) - 0.4)
            ax[0].set_ylim(0, 40)
            ax[0].set_ylabel("rewrites, wrong policy (%)", fontsize=7)
            ax[0].set_title("(a) rewrite drift vs 5 % target", fontsize=7.5, loc="left")
            sh = [sum(r["class"] == cl for r in thr) / len(thr) for cl in "abc"]  # (b) T-held taxonomy
            ax[1].bar(range(3), [100 * x for x in sh], color=c0, edgecolor=t["bg"], linewidth=2, width=0.6)
            ax[1].set_xticks(range(3), ["other topic\nverbatim", "hands off /\ndon't know", "other"], fontsize=6.5)
            ax[1].set_ylabel(f"T-held answers (%, n {len(thr)})", fontsize=7)
            ax[1].set_title("(b) unseen topics, 14B SFT", fontsize=7.5, loc="left")
            order = ["asks (pass)", "a", "b", "c", "d"]  # (c) B1 classes
            n = b1r[0]["n"]
            cnt = {r["class"]: r["count"] for r in b1r}
            ax[2].bar(range(len(order)), [100 * cnt.get(k, 0) / n for k in order], color=c0, edgecolor=t["bg"], linewidth=2, width=0.6)
            ax[2].set_xticks(range(len(order)), ["asks\n(pass)", "all\nbranch.", "some\nbranch.", "asks,\nfails", "other"], fontsize=6.5)
            ax[2].set_ylabel(f"B1 answers (%, n {n})", fontsize=7)
            ax[2].set_title("(c) missing detail: rarely asks", fontsize=7.5, loc="left")
            panels = [(["l14b_sft_rslora_tok", "l14b_sft_rslora_tok-v1.1", "l14b_sft_rslora_tok-v1.2"], "(d) SFT data version", "assistant_mean"),
                      (["l14b_sft_rslora_tok-v1.2", "pref_dpo_rules", "pref_simpo_rules"], "(e) preference stage", "assistant_mean"),
                      (["l14b_sft_rslora_tok-v1.2", "l14b_sft_rslora_tok-v1.2_rft"], "(f) RFT: retention", "rate_R")]
            for i, (gs, title, key) in enumerate(panels):
                a = ax[3 + i]
                for x, g in enumerate(gs):
                    r = summ[g]
                    v = 100 * r[key] if key == "rate_R" else r[key]
                    sd = r["assistant_sd"] if key == "assistant_mean" and r["assistant_sd"] != "" else None
                    a.bar(x, v, color=style.colour(r["method"]), edgecolor=t["bg"], linewidth=2, width=0.6,
                          yerr=sd, capsize=3, ecolor=t["text"])
                a.set_xticks(range(len(gs)), [short[g] for g in gs], fontsize=6.5)
                a.set_ylim(*((0, 110) if key == "rate_R" else (100, 160)))
                a.set_ylabel("retention R passed (%)" if key == "rate_R" else "Assistant /200", fontsize=7)
                a.set_title(title, fontsize=7.5, loc="left")
            for a in ax:
                a.grid(axis="x", visible=False)
            fig.tight_layout()
            return fig

    aud = ", ".join(f"{a['k_unsupported']}/{a['n']}" for a in fun["audits"])
    return {"draw": draw, "caption": (
        "**Question:** what did not work? **Plotted:** (a) share of Qwen3-32B rewrites with a wrong policy in the hand "
        f"audits ({aud}) vs the 5 % target; (b) T-held answers of "
        f"14B rsLoRA by class (n {len(thr)}, seeds pooled); (c) B1 answers of 14B rsLoRA v1 by diagnostic class (n {b1r[0]['n']}); "
        f"(d) Assistant /200 by SFT data version (seeds 3, 3, {sft['seeds']}); (e) DPO and SimPO (3 seeds each) next to "
        f"their SFT parent's group (v1.2, {sft['seeds']} seeds); (f) retention without a system prompt, SFT v1.2 vs RFT "
        "(1 seed). **Error bars:** (a) Wilson 95 % CI; (d, e) SD over seeds. **Test:** results/data_versions.md and "
        "results/preference.md (no Assistant or block difference after Holm); ADR-033 for RFT. **Takeaway:** rewrites "
        "drifted, unseen topics get a memorised wrong answer, B1 rarely asks, neither data versions nor preference tuning "
        f"moved the score, and RFT lost retention ({100 * sft['rate_R']:.0f} % → {100 * rft['rate_R']:.0f} %).")}


INDEX = {
    "F0": ("How does data flow from the handbook to the results?", "Boxes are stages, arrows are data; person icons mark hand audits.",
           ["Is every arm measured the same way?", "Where do humans check automatic labels?"]),
    "F1": ("Does fine-tuning turn a base model into a usable bank assistant?",
           "Each dot is a model; further right means more of the 200 test questions answered correctly.",
           ["How large is the gain, and is it bigger than seed noise?", "How does it compare to the vendor's Instruct model?", "Which arm is the main result?"]),
    "F2": ("Which behaviours does each arm get right?", "Brighter cells mean a higher share of that kind of question passed.",
           ["Is the overall gain coming from one block?", "Which behaviours are still unsolved?", "Does training hurt retention?"]),
    "F3": ("What does SFT change, block by block?", "Dots right of the line are blocks where the trained model beats its base model.",
           ["Which gains survive a multiple-testing correction?", "Is the effect consistent across seeds?", "Do LoRA, QLoRA and full FT differ?"]),
    "F4": ("Does preference optimisation (DPO / SimPO) improve on SFT?", "Dots right of the line are blocks where preference tuning helped.",
           ["Is DPO/SimPO worth an extra stage?", "Does it trade safety for helpfulness?"]),
    "F5": ("Does reinforcement learning (GRPO) improve on SFT?", "Dots right of the line are blocks where GRPO helped.",
           ["Is the RL stage worth its cost?", "Which blocks does it move?"]),
    "F6": ("How much does model size matter, before and after SFT?", "Each line follows one recipe from small to large models.",
           ["Would a smaller model do?", "Does SFT close the gap between sizes?"]),
    "F7": ("What do trained models say about topics they were never trained on?", "Dark bars are answers copied from a different, trained topic.",
           ["Why is T-held near zero?", "Is it a scorer artefact or real behaviour?", "Does a bigger model generalise better?"]),
    "F8": ("Do the models end their turn where they should?", "Bright = the model stopped properly; dark = it kept writing until cut off.",
           ["Why did the first LoRA runs score high but read badly?", "Is the fix complete in every arm?"]),
    "F9": ("Why do LoRA-trained models never emit <|im_end|>?", "Tall bars mean the end-of-turn token looks like thousands of unused tokens.",
           ["Is this a bug in our code or a property of the base model?", "Why is full fine-tuning unaffected?"]),
    "F10": ("Can paraphrased answers from a larger model be trusted as training data?", "Left: how many rewrites passed each filter. Right: how many of those still got the policy wrong.",
            ["Why was the rewrite data not used?", "Did the entailment judge help?"]),
    "F11": ("Does training make the assistant less safe?", "Dots near zero are good: few unsafe or wrong behaviours.",
            ["Does SFT increase credential requests or injection success?", "Does the model over-refuse after training?"]),
    "F12": ("What does each training method cost for what it delivers?", "Further left is cheaper; higher is better.",
            ["Is full fine-tuning worth its cost?", "Is QLoRA a good trade?"]),
    "F13": ("Are the trained models' answers the right length?", "Lines that jump up at 200 are answers that never stopped.",
            ["How visible is the run-on problem?", "Are fixed models as concise as the Instruct model?"]),
    "F14": ("Do the end-of-turn fix and the DPO start behave as specified?", "Left: taller = more answers end properly. Right: lines start on the dashed ln 2 line.",
            ["Is the <|im_end|> fix complete?", "Does DPO start from the reference model?"]),
    "F15": ("What did not work?", "Six small panels, one negative result each; flat bars mean no change.",
            ["Why were rewrites not used?", "Did data versions or preference tuning help?", "What did RFT cost?"]),
    "T1": ("What are the main numbers?", "One row per model; the first score column is the headline.", ["What is the seed spread?", "Is every gain significant vs base?"]),
    "T2": ("Can the numbers be trusted?", "Each row is a check of the measuring tool itself.", ["How accurate is the automatic scorer?", "Do hardware or batch size change scores?"]),
    "T3": ("What do the answers actually look like?", "Read the same question answered by different models.", ["Were examples cherry-picked?", "What does a failure look like?"]),
    "T4": ("Why does B1 (asking for a missing detail) fail?", "Top: where earlier B1 passes really came from. Bottom: how rarely the training data asks a question.",
           ["Was the early B1 score real?", "Is it a data problem?"]),
    "T5": ("What did it cost and how is it reproduced?", "GPU-hours per model and the commands to rerun them.", ["How much compute did this take?", "Can I rerun it?"]),
    "T6": ("Did test questions leak into training data?", "Exact matches must be zero.", ["Is the eval contaminated?", "How were near-duplicates handled?"]),
}
FIGURES = {"F0": f0, "F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5, "F6": f6, "F7": f7, "F8": f8, "F9": f9, "F10": f10, "F11": f11, "F12": f12, "F13": f13, "F14": f14, "F15": f15}
TABLES = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6}


def write_index(path: Path, status: dict, captions: dict, out: Path) -> None:
    rel = lambda p: Path("..") / p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
    L = ["# Figures and tables", "", "Generated by `figures/make_figures.py` from `results/` (never edit by hand). Each "
         "figure exists in a light and a dark version as PNG (300 dpi), SVG and PDF. Captions follow one template: "
         "question; what is plotted, with n and seeds; error bars; test and exact p; one-sentence takeaway.", "",
         "| Id | Question | Status |", "|---|---|---|"]
    L += [f"| [{i}](#{i.lower()}) | {INDEX[i][0].replace('|', chr(92) + '|')} | {status[i]} |" for i in INDEX]
    for i, (q, guide, revq) in INDEX.items():
        L += ["", f"## {i}", "", f"**{q}**", ""]
        if status[i] == "built":
            if i.startswith("F"):
                L += [f"![{i}]({rel(out / f'{i}_light.png').as_posix()})", ""]
            else:
                L += [f"Table: [{i}.md]({rel(out / f'{i}.md').as_posix()})", ""]
            if captions.get(i):
                L += [captions[i], ""]
        else:
            L += [f"*{status[i]}*", ""]
        L += [f"**How to read it:** {guide}", "", "**Reviewer questions it answers:** " + " · ".join(revq)]
    path.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated ids, e.g. F3,T1")
    ap.add_argument("--results", type=Path, default=ROOT / "results")
    ap.add_argument("--out", type=Path, default=ROOT / "figures")
    ap.add_argument("--docs", type=Path, default=ROOT / "docs" / "figures.md")
    args = ap.parse_args(argv)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    R = Results(args.results)
    status, captions = {}, {}
    for fid, fn in {**FIGURES, **TABLES}.items():
        if only and fid not in only:
            continue
        try:
            if fid in FIGURES:
                spec = fn(R)
                for theme in style.THEMES:
                    style.save(spec["draw"](theme), args.out, fid, theme)
                captions[fid] = spec["caption"]
            else:
                args.out.mkdir(parents=True, exist_ok=True)
                (args.out / f"{fid}.md").write_text(fn(R) + "\n", encoding="utf-8", newline="\n")
                captions[fid] = ""
            status[fid] = "built"
        except Pending as e:
            status[fid] = f"pending: {e}"
        print(f"{fid}: {status[fid]}")
    if not only:
        write_index(args.docs, status, captions, args.out)
    return status


if __name__ == "__main__":
    main()
