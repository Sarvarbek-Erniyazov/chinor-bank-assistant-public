"""results/method_table.md: one row per method, what it answers and what it scored, from committed results files only.

python scripts/method_table.py          (after results/build_tidy.py, eval/redteam_results.py, results/gguf_report.py)

Inputs (all committed):
- results/tidy/items_long.csv: per-item eval-v1 pass/fail of every recorded arm (Protocol A, rubric v1.3);
- eval/outputs/rt-<arm>/redteam_scores.jsonl: per-attack red-team verdicts (redteam-v1, eval/redteam_results.py);
- results/runs/gguf-<name>-Q8_0/{scores.jsonl, run.json}: the four served GGUF files (results/gguf_report.py).
Every cell is computed here with the functions of figures/stats.py that the source tables use: Assistant /200 =
passes on the 200 non-R items, mean ± SD over seeds; Δ = paired bootstrap over items stratified by seed (10,000
resamples, seed 20261029), as results/arm_differences.md and results/preference.md; red-team attack success with the
attack as the unit (redteam_interval / fmt_rt), as results/redteam.md. tests/test_method_table.py checks every Δ and
red-team cell that also appears in those files against them.

Rows whose inputs do not exist yet are not written; they appear by themselves once the files exist:
- RFT with 3 seeds: eval/outputs/l14b_sft_rslora_tok-s{1,2}-v1.2_rft-r2611/ (J3; seed 0 is the recorded run);
- re-run column: any eval/outputs/<recorded arm>-r2611/ (J0, J2), shown next to the recorded value of that seed;
- serving benchmark: results/tidy/serving.csv (J4), one row per configuration, written as its own table.
GRPO is listed as designed, not run (ADR-037), with no score. table() returns the rows as data for
scripts/build_readme.py.

Holm families: each row names the ADR-035 family (docs/decisions.md) its Δ belongs to, or None. A Δ in no family gets
the footnote "computed <date>; not part of any Holm family; exploratory" (or, when the Δ is already in an earlier
generated table, "not part of any Holm family; exploratory; also in <table>"). A new row outside every family must
state the date its Δ was first computed (COMPUTED): build() refuses a row without it, so none appears unlabelled.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "outputs"
RUNS = ROOT / "results" / "runs"
ITEMS = ROOT / "results" / "tidy" / "items_long.csv"
SERVING = ROOT / "results" / "tidy" / "serving.csv"
SUMMARY = ROOT / "results" / "tidy" / "arm_summary.csv"
TARGET = ROOT / "results" / "method_table.md"
RERUN = "-r2611"
N_ATTACKS = sum(1 for l in (ROOT / "eval" / "redteam_set.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip() and "_meta" not in json.loads(l))
ASSISTANT = {"T-seen", "T-held", "B1", "B2", "B3", "B4"}
GGUF_QUANT = "Q8_0"  # ADR-036


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _load("figure_stats", ROOT / "figures" / "stats.py")

SFT_V1 = [f"l14b_sft_rslora_tok-s{i}" for i in range(3)]
SFT_V12_S0 = ["l14b_sft_rslora_tok-s0-v1.2"]
BASE14 = ["base-14B-0shot-A"]
V1_LABEL = "14B rsLoRA, data v1 (3 seeds)"
TRAINED = "done"


def row(method, question, arms, comp, comp_label, sources, holm, status=TRAINED, trained=True):
    """One method row. holm: the ADR-035 Holm family (1-5) of the Δ, or None. trained: show the peak training memory."""
    return {"method": method, "question": question, "arms": arms, "comp": comp, "comp_label": comp_label,
            "sources": sources, "holm": holm, "status": status, "trained": trained}


ROWS = [
    row("Base, Qwen3-14B-Base, 0-shot", "What does the untuned base model do with the system prompt alone?",
        BASE14, None, "reference row", ["results/results.md", "results/redteam.md"], None, "reference", False),
    row("Instruct reference, Qwen3-14B (vendor chat model, not trained here)",
        "How far does a general chat model get without domain training?",
        ["ref-14B-instruct-A"], BASE14, "Qwen3-14B-Base 0-shot", ["results/results.md", "results/redteam.md"], None,
        "reference, not trained here", False),
    row("SFT rsLoRA with token rows, data v1.2, 14B (main result)",
        "Does SFT on the handbook data turn the base model into the assistant?",
        [f"l14b_sft_rslora_tok-s{i}-v1.2" for i in range(5)], BASE14, "Qwen3-14B-Base 0-shot",
        ["results/results.md", "results/redteam.md"], 1, "main result"),
    row("SFT rsLoRA with token rows, data v1, 14B", "The comparison row for QLoRA, full FT, size and data versions.",
        SFT_V1, BASE14, "Qwen3-14B-Base 0-shot", ["results/results.md", "results/redteam.md"], 1),
    row("QLoRA (4-bit base) rsLoRA with token rows, data v1, 14B",
        "Does a 4-bit base during training cost score, and how much memory does it save?",
        [f"l14b_qlora_rslora_tok-s{i}" for i in range(3)], SFT_V1, V1_LABEL,
        ["results/arm_differences.md", "results/lora_vs_qlora.md", "results/redteam.md"], 5),
    row("Full fine-tuning, lr 1e-5, data v1, 14B", "Does training all weights beat an adapter (first learning rate)?",
        ["l14b_full-s0", "l14b_full-s1"], SFT_V1[:2], "14B rsLoRA, data v1, seeds 0–1",
        ["results/full_ft_analysis.md", "results/lora_vs_qlora.md", "results/redteam.md"], None),
    row("Full fine-tuning, lr 2e-5, data v1, 14B", "Does training all weights beat an adapter (second learning rate)?",
        ["l14b_full_lr2e5-s0", "l14b_full_lr2e5-s1"], SFT_V1[:2], "14B rsLoRA, data v1, seeds 0–1",
        ["results/arm_differences.md", "results/lora_vs_qlora.md", "results/redteam.md"], 5),
    row("Size 1.7B: SFT rsLoRA with token rows, data v1", "Is a much smaller model enough after SFT?",
        [f"tier_s_main_rslora_tok-s{i}" for i in range(3)], SFT_V1,
        V1_LABEL + "; the two sizes were trained at different learning rates (ADR-026), so the difference is not an effect of size alone", ["results/results.md"], None),
    row("Size 4B: SFT rsLoRA with token rows, data v1", "Is a smaller model enough after SFT?",
        [f"size_4b_rslora_tok-s{i}" for i in range(3)], SFT_V1, V1_LABEL + "; the two sizes were trained at different learning rates (ADR-026), so the difference is not an effect of size alone",
        ["results/arm_differences.md", "results/redteam.md"], 5),
    row("Size 8B: SFT rsLoRA with token rows, data v1", "Is a smaller model enough after SFT?",
        [f"size_8b_rslora_tok-s{i}" for i in range(3)], SFT_V1, V1_LABEL,
        ["results/arm_differences.md", "results/redteam.md"], 5),
    row("SFT data v1.1 (more asking turns, ADR-028), 14B", "Do more asking examples change the score?",
        [f"l14b_sft_rslora_tok-s{i}-v1.1" for i in range(3)], SFT_V1, V1_LABEL,
        ["results/data_versions.md", "results/arm_differences.md"], 5),
    row("SFT data v1.2 (handoff examples, ADR-029), 14B, seeds 0–2", "Do handoff examples change the score?",
        [f"l14b_sft_rslora_tok-s{i}-v1.2" for i in range(3)], SFT_V1, V1_LABEL,
        ["results/data_versions.md", "results/arm_differences.md"], 5),
    row("DPO on the rule-labelled on-policy pairs, from SFT v1.2 seed 0, 14B",
        "Does preference tuning add to SFT?",
        [f"pref_dpo_rules-s{i}" for i in range(3)], SFT_V12_S0, "its one SFT parent, 14B v1.2 seed 0",
        ["results/preference.md", "results/redteam.md"], 3),
    row("SimPO on the same pairs, from SFT v1.2 seed 0, 14B",
        "Does preference tuning without a reference model add to SFT?",
        [f"pref_simpo_rules-s{i}" for i in range(3)], SFT_V12_S0, "its one SFT parent, 14B v1.2 seed 0",
        ["results/preference.md", "results/redteam.md"], 3),
    row("RFT (SFT v1.2 plus verified on-policy samples), 14B, exploratory",
        "Does SFT on the model's own verified samples add to SFT?",
        ["l14b_sft_rslora_tok-s0-v1.2_rft"], SFT_V12_S0, "SFT v1.2 seed 0 (same seed and config)",
        ["results/preference.md", "results/redteam.md"], 4, "exploratory, 1 seed, not recommended (ADR-033)"),
    row("RFT, 14B, recorded seed plus the new seeds of run " + RERUN[1:],
        "Does the RFT result hold over seeds?",
        ["l14b_sft_rslora_tok-s0-v1.2_rft"] + [f"l14b_sft_rslora_tok-s{i}-v1.2_rft{RERUN}" for i in (1, 2)],
        SFT_V12_S0, "SFT v1.2 seed 0", ["results/redteam.md"], None, "exploratory"),
]
GRPO = row("GRPO with the rule reward, 14B", "Does online RL with the rule reward add to SFT?", [], None, "—",
           ["train/rewards.py", "docs/decisions.md"], None, "designed, not run (ADR-037)", False)

# A Δ outside every Holm family: the date it was first computed, or the earlier generated table that already holds it.
# A row outside every family that is in neither dict stops build(): its date is stated when the row is added.
COMPUTED = {"Full fine-tuning, lr 1e-5, data v1, 14B": "2026-11-16", "GGUF": "2026-11-16",
            "Size 1.7B: SFT rsLoRA with token rows, data v1": "2026-11-16"}
EARLIER = {"Instruct reference, Qwen3-14B (vendor chat model, not trained here)": "figures/T1.md"}
SUPERSCRIPT = "¹²³⁴⁵⁶⁷⁸⁹"


def holm_note(method: str) -> str:
    """Footnote text for a Δ that is in no ADR-035 Holm family."""
    key = "GGUF" if method.startswith("GGUF") else method
    if key in EARLIER:
        return f"not part of any Holm family; exploratory; also in `{EARLIER[key]}`"
    if key not in COMPUTED:
        raise SystemExit(f"row {method!r}: its Δ is in no ADR-035 Holm family; add the date it was first computed to "
                         "COMPUTED in scripts/method_table.py")
    return f"computed {COMPUTED[key]}; not part of any Holm family; exploratory"


GGUF = [("(a) Qwen3-1.7B-Base, no fine-tuning", "base-1.7b"),
        ("(b) SFT rsLoRA without token rows, data v1, seed 0", "sft-1.7b-notok-s0"),
        ("(c1) SFT rsLoRA with token rows, data v1, seed 0", "sft-1.7b-tok-s0"),
        ("(c) SFT rsLoRA with token rows, data v1.2, seed 0", "sft-1.7b-tok-v1.2-s0")]
GGUF_STATUS = "served in the local demo; CPU, not the evaluation protocol"


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_items() -> tuple[dict, dict]:
    passes, block = defaultdict(dict), {}
    with ITEMS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            passes[r["arm"]][r["item_id"]] = int(r["pass"])
            block[r["item_id"]] = r["block"]
    return passes, block


def arm_groups() -> dict[str, str]:
    with ITEMS.open(encoding="utf-8") as f:
        return {r["arm"]: r["arm_group"] for r in csv.DictReader(f)}


def peak_vram() -> dict[str, float]:
    with SUMMARY.open(encoding="utf-8") as f:
        return {r["arm_group"]: float(r["peak_vram_gb"]) for r in csv.DictReader(f) if r["peak_vram_gb"]}


def vectors(passes: dict, arms: list[str], items: list[str]) -> list[list[int]]:
    return [[passes[a][i] for i in items] for a in arms]


def mean_sd(v: list[list[int]]) -> str:
    totals = [sum(x) for x in v]
    if len(totals) == 1:
        return str(totals[0])
    return f"{st.mean(totals):.1f} ± {st.stdev(totals):.1f}"


def delta(va: list, vb: list) -> str:
    b = S.paired_bootstrap(va, vb)
    return f"{b['delta']:+.1f} [{b['ci_lo']:.1f}, {b['ci_hi']:.1f}]"


def redteam(arms: list[str]) -> str | None:
    dirs = [OUT / f"rt-{a}" / "redteam_scores.jsonl" for a in arms]
    if not all(d.exists() for d in dirs):
        return None
    v = [[int(r["attack_success"]) for r in sorted(jsonl(d), key=lambda r: r["id"])] for d in dirs]
    return S.fmt_rt(S.redteam_interval(v), sum(map(sum, v)), len(v[0]) * len(v))


def seeds_cell(eval_arms: list[str], rt: str | None, rt_n: int) -> str:
    n = len(eval_arms)
    return f"{n} (red-team {rt_n})" if rt is not None and rt_n != n else str(n)


def rerun_cell(passes: dict, arms: list[str], items: list[str]) -> str:
    out = []
    for a in arms:
        if a.endswith(RERUN) or f"{a}{RERUN}" not in passes:
            continue
        new, old = sum(vectors(passes, [f"{a}{RERUN}"], items)[0]), sum(vectors(passes, [a], items)[0])
        out.append(f"`{a}`: {new} (recorded {old})")
    return "; ".join(out)


COLUMNS = ["method", "question", "seeds", "mean", "delta", "comp", "holm", "redteam", "vram", "status", "source"]


def table() -> dict:
    """Every row as {column: cell}, the header names, the footnotes and the item counts (README reuses these)."""
    passes, block = load_items()
    items = sorted(i for i, b in block.items() if b in ASSISTANT)
    groups, vram = arm_groups(), peak_vram()
    rows, notes, any_rerun = [], [], False

    def holm_cell(method: str, holm: int | None, d: str) -> str:
        if d == "—":
            return "—"
        if holm is not None:
            return f"family {holm}"
        n = holm_note(method)
        if n not in notes:
            notes.append(n)
        return f"none: exploratory {SUPERSCRIPT[notes.index(n)]}"

    def src(paths: list[str]) -> str:
        return ", ".join(f"`{s}`" for s in paths)

    for r in ROWS:
        arms = r["arms"]
        if not all(a in passes for a in arms):
            continue  # inputs not there yet: the row is not written
        va = vectors(passes, arms, items)
        # red-team: the seeds that have a red-team run (full FT lr 1e-5: seed 0 only)
        rt_arms = [a for a in arms if (OUT / f"rt-{a}" / "redteam_scores.jsonl").exists()]
        rt = redteam(rt_arms) if rt_arms else None
        d = delta(va, vectors(passes, r["comp"], items)) if r["comp"] else "—"
        g = {groups[a] for a in arms}  # peak training memory of the arm group, when the row is one trained group
        mem = f"{vram[next(iter(g))]:.1f}" if r["trained"] and len(g) == 1 and next(iter(g)) in vram else "—"
        rr = rerun_cell(passes, arms, items)
        any_rerun |= bool(rr)
        rows.append({"method": r["method"], "question": r["question"], "seeds": seeds_cell(arms, rt, len(rt_arms)),
                     "mean": mean_sd(va), "delta": d, "comp": r["comp_label"] if r["comp"] else "—",
                     "holm": holm_cell(r["method"], r["holm"], d), "redteam": rt or "not run", "vram": mem,
                     "status": r["status"], "source": src(["results/tidy/items_long.csv"] + r["sources"]),
                     "sources": ["results/tidy/items_long.csv"] + r["sources"], "rerun": rr})
    for label, name in GGUF:
        run_dir = RUNS / f"gguf-{name}-{GGUF_QUANT}"
        if not (run_dir / "scores.jsonl").exists():
            continue
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        sc = {r["id"]: int(r["pass"]) for r in jsonl(run_dir / "scores.jsonl")}
        va = [[sc[i] for i in items]]
        method = f"GGUF {GGUF_QUANT} served in the local demo: {label} (CPU, not the evaluation protocol)"
        d = delta(va, vectors(passes, [run["compare_arm"]], items))
        sources = [f"results/runs/gguf-{name}-{GGUF_QUANT}/", "results/gguf_demo_models.md"]
        rows.append({"method": method, "question": "Does the served file score like the recorded bf16 model?",
                     "seeds": "1", "mean": mean_sd(va), "delta": d,
                     "comp": f"the recorded bf16 run `{run['compare_arm']}` (different runtime, precision and machine)",
                     "holm": holm_cell(method, None, d), "redteam": "not run (eval-v1 only)", "vram": "—",
                     "status": GGUF_STATUS, "source": src(sources), "sources": sources, "rerun": ""})
    rows.append({"method": GRPO["method"], "question": GRPO["question"], "seeds": "—", "mean": "—", "delta": "—",
                 "comp": "—", "holm": "—", "redteam": "—", "vram": "—", "status": GRPO["status"],
                 "source": src(GRPO["sources"]), "sources": GRPO["sources"], "rerun": ""})
    head = {"method": "Method", "question": "Question the row answers", "seeds": "Seeds",
            "mean": f"Assistant /{len(items)} (mean ± SD over seeds)", "delta": "Δ Assistant [95 % CI]",
            "comp": "Compared with", "holm": "Holm family (ADR-035)",
            "redteam": "Red-team attack success (95 % interval; k/N; method)",
            "vram": "Peak training memory, GB", "status": "Status", "source": "Source"}
    cols = list(COLUMNS)
    if any_rerun:
        head["rerun"] = f"Re-run ({RERUN[1:]}): Assistant /{len(items)} per seed"
        cols.append("rerun")
    return {"rows": rows, "head": head, "cols": cols, "notes": notes, "n_items": len(block), "n_assistant": len(items)}


def build() -> str:
    t = table()
    n, na = t["n_items"], t["n_assistant"]
    L = ["# Method → result", "",
         f"`scripts/method_table.py`, from committed results files only. Eval-v1 ({n} frozen items), rubric "
         f"v1.3; Assistant /{na} = passes on the {na} non-retention items, mean ± SD over seeds. Δ = row "
         f"− comparison, paired bootstrap over items stratified by seed ({S.BOOT_N:,} resamples, seed {S.BOOT_SEED}; a "
         "one-seed side is reused for every seed of the other); Δ not Holm-adjusted here: the adjusted families "
         "(ADR-035) are in `docs/figures.md`, `results/arm_differences.md` and `results/preference.md`; a Δ in no "
         "family is footnoted. A CI that includes 0 means no significant difference detected, not equivalence. "
         f"Red-team: redteam-v1, {N_ATTACKS} attacks, the attack is the unit; one seed exact Clopper–Pearson, several "
         "seeds BCa cluster bootstrap over attacks (`results/redteam.md`). Peak training memory: "
         "`results/tidy/arm_summary.csv` (H200). 14B rows: Protocol A (H200, bf16, greedy). GGUF rows: llama.cpp on a "
         "laptop CPU, not the evaluation protocol.", "",
         "| " + " | ".join(t["head"][c] for c in t["cols"]) + " |", "|" + "---|" * len(t["cols"])]
    for r in t["rows"]:
        L.append("| " + " | ".join(r[c] for c in t["cols"]) + " |")
    for i, note in enumerate(t["notes"]):
        L += ["", f"{SUPERSCRIPT[i]} Δ {note}."]
    if SERVING.exists():
        with SERVING.open(encoding="utf-8") as f:
            srows = list(csv.reader(f))
        L += ["", "## Serving benchmark", "", f"`{SERVING.relative_to(ROOT).as_posix()}`, as written by its script.", "",
              "| " + " | ".join(srows[0]) + " |", "|" + "---|" * len(srows[0])]
        L += ["| " + " | ".join(r) + " |" for r in srows[1:]]
    return "\n".join(L) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = build()
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(text)


if __name__ == "__main__":
    main()
