"""results/method_table.md is current and every number in it equals its source table.

python -m pytest tests/test_method_table.py -q
The table is computed by scripts/method_table.py from per-item files; here each cell that also appears in a
generated source table (T1, results/arm_differences.md, results/preference.md, results/redteam.md,
results/tidy/arm_summary.csv, results/gguf_demo_models.md, docs/claims.md) is checked against it. The one Δ with no
earlier source (full FT lr 1e-5 − rsLoRA, seeds 0–1) is computed by the same function as the checked ones.
"""
from __future__ import annotations

import csv
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("method_table", ROOT / "scripts" / "method_table.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

TEXT = mt.build()
HEAD = None
ROWS = {}
for line in TEXT.splitlines():
    if line.startswith("| Method"):
        HEAD = [c.strip() for c in line.strip("|").split("|")]
    elif line.startswith("| ") and HEAD and not line.startswith("|---"):
        cells = [c.strip() for c in line.strip("|").split(" | ")]
        ROWS[cells[0]] = dict(zip(HEAD, cells))
DELTA = next(h for h in HEAD if h.startswith("Δ"))
RT = next(h for h in HEAD if h.startswith("Red-team"))
MEAN = next(h for h in HEAD if h.startswith("Assistant"))
HOLM = next(h for h in HEAD if h.startswith("Holm"))
VRAM = next(h for h in HEAD if h.startswith("Peak"))


def row(prefix: str) -> dict:
    return next(v for k, v in ROWS.items() if k.startswith(prefix))


def read(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def md_cell(path: str, label: str, col: int) -> str:
    for line in read(path).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == label:
            return cells[col]
    raise AssertionError(f"{label} not in {path}")


def test_committed_table_is_current():
    assert read("results/method_table.md") == TEXT


def test_deltas_equal_arm_differences():
    pairs = {"QLoRA": "14B QLoRA − 14B LoRA (SFT v1)",
             "Full fine-tuning, lr 2e-5": "14B full FT lr 2e-5 − 14B LoRA (SFT v1, seeds 0–1)",
             "Size 4B": "4B − 14B (SFT rsLoRA v1)", "Size 8B": "8B − 14B (SFT rsLoRA v1)"}
    for prefix, label in pairs.items():
        assert row(prefix)[DELTA] == md_cell("results/arm_differences.md", label, 4), prefix


def test_deltas_equal_preference_table():
    def pref(label):
        for line in read("results/preference.md").splitlines():
            c = [x.strip() for x in line.strip("|").split("|")]
            if len(c) > 2 and c[0] == label and c[1] == "Assistant":
                return c[2]
    assert row("DPO")[DELTA] == pref("DPO (rules) − SFT (v1.2 seed 0)")
    assert row("SimPO")[DELTA] == pref("SimPO (rules) − SFT (v1.2 seed 0)")
    assert row("RFT (SFT v1.2")[DELTA] == pref("RFT (exploratory, ADR-033) − SFT (v1.2 seed 0)")


def test_deltas_vs_base_equal_t1_and_claims():
    t1 = next(l for l in read("figures/T1.md").splitlines() if "`ref-14B-instruct-A`" in l)
    assert t1.rstrip().endswith(f"| {row('Instruct reference')[DELTA]} |")
    assert f"Δ {row('SFT rsLoRA with token rows, data v1.2')[DELTA]}" in read("docs/claims.md")


def test_redteam_cells_equal_redteam_table():
    groups = {"Base, Qwen3-14B": "base-14B-0shot-A", "Instruct reference": "ref-14B-instruct-A",
              "SFT rsLoRA with token rows, data v1.2": "l14b_sft_rslora_tok-v1.2", "QLoRA": "l14b_qlora_rslora_tok",
              "Full fine-tuning, lr 1e-5": "l14b_full", "Full fine-tuning, lr 2e-5": "l14b_full_lr2e5",
              "Size 4B": "size_4b_rslora_tok", "Size 8B": "size_8b_rslora_tok", "DPO": "pref_dpo_rules",
              "SimPO": "pref_simpo_rules", "RFT (SFT v1.2": "l14b_sft_rslora_tok-v1.2_rft"}
    for prefix, g in groups.items():
        assert row(prefix)[RT] == md_cell("results/redteam.md", f"`{g}`", 4), prefix


def test_means_equal_arm_summary():
    summ = {r["arm_group"]: r for r in csv.DictReader((ROOT / "results/tidy/arm_summary.csv").open(encoding="utf-8"))}
    groups = {"Base, Qwen3-14B": "base-14B-0shot-A", "SFT rsLoRA with token rows, data v1.2": "l14b_sft_rslora_tok-v1.2",
              "QLoRA": "l14b_qlora_rslora_tok", "Full fine-tuning, lr 1e-5": "l14b_full",
              "Size 4B": "size_4b_rslora_tok", "DPO": "pref_dpo_rules", "RFT (SFT v1.2": "l14b_sft_rslora_tok-v1.2_rft"}
    for prefix, g in groups.items():
        cell, s = row(prefix)[MEAN], summ[g]
        nums = [float(x) for x in re.findall(r"[\d.]+", cell)]
        assert abs(nums[0] - float(s["assistant_mean"])) < 0.05, prefix
        if len(nums) > 1:
            assert abs(nums[1] - float(s["assistant_sd"])) < 0.05, prefix


def test_gguf_scores_equal_served_table():
    served = [l for l in read("results/gguf_demo_models.md").split("## Other levels")[0].splitlines()
              if l.startswith("| (")]
    gguf = [v for k, v in ROWS.items() if k.startswith("GGUF")]
    assert len(gguf) == len(served) == 4
    for v, line in zip(gguf, served):
        assert line.split(" | ")[6].split(" (")[0] == v[MEAN]


def test_rows_without_inputs_are_not_written():
    has_rft3 = all((mt.OUT / f"l14b_sft_rslora_tok-s{i}-v1.2_rft{mt.RERUN}" / "scores.jsonl").exists() for i in (1, 2))
    assert any(k.startswith("RFT, 14B, recorded seed") for k in ROWS) == has_rft3
    assert any(h.startswith("Re-run") for h in HEAD) == any(
        p.name.endswith(mt.RERUN) and (p / "scores.jsonl").exists() for p in mt.OUT.iterdir())
    assert ("## Serving benchmark" in TEXT) == mt.SERVING.exists()


def test_delta_outside_holm_families_is_footnoted():
    """Decision 2026-11-16: a Δ in no ADR-035 Holm family carries "computed <date>; not part of any Holm family;
    exploratory" (or names the earlier table that holds it)."""
    notes = dict(re.findall(r"(?m)^([¹²³⁴⁵⁶⁷⁸⁹]) Δ (.+)\.$", TEXT))
    assert notes[row("Full fine-tuning, lr 1e-5")[HOLM][-1]] == "computed 2026-11-16; not part of any Holm family; exploratory"
    for r in mt.ROWS:
        if r["method"] not in ROWS or ROWS[r["method"]][DELTA] == "—":
            continue
        cell = ROWS[r["method"]][HOLM]
        if r["holm"] is None:
            assert cell.startswith("none: exploratory ") and cell[-1] in notes, r["method"]
        else:
            assert cell == f"family {r['holm']}", r["method"]
    for k, v in ROWS.items():
        if k.startswith("GGUF"):
            assert "not part of any Holm family" in notes[v[HOLM][-1]], k
            assert "CPU, not the evaluation protocol" in k


def test_holm_families_exist_in_adr_035():
    adr = read("docs/decisions.md").split("## ADR-035", 1)[1].split("\n## ", 1)[0]
    for r in mt.ROWS:
        if r["holm"] is not None:
            assert re.search(rf"(?m)^\s+{r['holm']}\. \*\*", adr), r["method"]


def test_peak_memory_equals_lora_vs_qlora():
    pairs = {"SFT rsLoRA with token rows, data v1, 14B": "LoRA (bf16 base, adamw_torch)",
             "QLoRA": "QLoRA (NF4 base, paged_adamw_8bit)",
             "Full fine-tuning, lr 1e-5": "full FT lr 1e-5, 3 epochs (bf16, adamw_bnb_8bit)"}
    for prefix, label in pairs.items():
        assert row(prefix)[VRAM] == md_cell("results/lora_vs_qlora.md", label, 15), prefix


def test_grpo_is_designed_not_run():
    g = row("GRPO")
    assert g[MEAN] == g[DELTA] == "—" and g["Status"] == "designed, not run (ADR-037)"
    assert "`train/rewards.py`" in g["Source"] and (ROOT / "train" / "rewards.py").exists()


def test_new_row_outside_families_needs_a_date():
    try:
        mt.holm_note("Some future row")
    except SystemExit as e:
        assert "COMPUTED" in str(e)
    else:
        raise AssertionError("a row in no Holm family and without a date was accepted")
