"""figures/make_figures.py on a small synthetic results/ tree: every figure and table builds, every output file
exists, and SVGs are byte-identical across two runs. CPU only.

python -m pytest tests/test_figures.py -q
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "figures"))
import make_figures as mf  # noqa: E402
from stats import wilson  # noqa: E402

SIZES = {"T-seen": 100, "T-held": 20, "B1": 20, "B2": 20, "B3": 25, "B4": 15, "R": 20}
# group, method, size, token_rows, seeds, pass probability
GROUPS = [("base-1.7B-0shot-A", "base", "1.7B", "n/a", 1, 0.2), ("ref-1.7B-instruct-A", "instruct (reference)", "1.7B", "n/a", 1, 0.25),
          ("tier_s_main_rslora_tok", "rsLoRA", "1.7B", "yes", 3, 0.65), ("base-4B-0shot-A", "base", "4B", "n/a", 1, 0.2),
          ("size_4b_rslora_tok", "rsLoRA", "4B", "yes", 1, 0.68), ("base-8B-0shot-A", "base", "8B", "n/a", 1, 0.22),
          ("size_8b_rslora_tok", "rsLoRA", "8B", "yes", 1, 0.7), ("base-14B-0shot-A", "base", "14B", "n/a", 1, 0.23),
          ("ref-14B-instruct-A", "instruct (reference)", "14B", "n/a", 1, 0.3), ("l14b_sft_rslora", "rsLoRA", "14B", "no", 3, 0.75),
          ("l14b_sft_rslora_tok", "rsLoRA", "14B", "yes", 3, 0.72), ("l14b_qlora_rslora_tok", "QLoRA", "14B", "yes", 3, 0.71),
          ("l14b_full", "full FT", "14B", "n/a", 1, 0.62), ("l14b_dpo", "DPO", "14B", "yes", 1, 0.75),
          ("l14b_grpo", "GRPO", "14B", "yes", 1, 0.76), ("l14b_sft_rslora_tok-v1.1", "rsLoRA", "14B", "yes", 3, 0.71),
          ("l14b_sft_rslora_tok-v1.2", "rsLoRA", "14B", "yes", 3, 0.72), ("pref_dpo_rules", "DPO", "14B", "yes", 3, 0.72),
          ("pref_simpo_rules", "SimPO", "14B", "yes", 3, 0.72), ("l14b_sft_rslora_tok-v1.2_rft", "rsLoRA", "14B", "yes", 1, 0.7)]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def fixture(rdir: Path) -> None:
    rng = np.random.default_rng(0)
    ids = [(b, f"{b}-{i:03d}") for b, n in SIZES.items() for i in range(1, n + 1)]
    long, summ, rates, stops, lens = [], [], [], [], []
    for g, method, size, rows, seeds, p in GROUPS:
        per = []
        for s in range(seeds):
            run = [{"arm": f"{g}-s{s}", "arm_group": g, "method": method, "size": size, "seed": s, "protocol": "A",
                    "token_rows": rows, "item_id": i, "block": b, "pass": int(rng.random() < p), "pass_cut": 0, "hv": 0,
                    "num": int(rng.random() < 0.005), "or": 0, "inj": 0, "stop_reason": "length" if rows == "no" else "im_end",
                    "n_tokens": 200 if rows == "no" else int(rng.integers(20, 120))} for b, i in ids]
            long += run
            per.append(run)
            stops.append({"arm": f"{g}-s{s}", "arm_group": g, "method": method, "token_rows": rows,
                          "stop_reason": run[0]["stop_reason"], "count": len(run)})
        asst = [sum(r["pass"] for r in run if r["block"] != "R") for run in per]
        k = sum(asst)
        _, lo, hi = wilson(k, 200 * seeds)
        sd = lambda xs: round(st.stdev(xs), 4) if len(xs) > 1 else ""
        row = {"arm_group": g, "method": method, "size": size, "protocol": "A", "token_rows": rows, "seeds": seeds,
               "assistant_mean": round(st.mean(asst), 4), "assistant_sd": sd(asst), "assistant_rate": round(k / (200 * seeds), 4),
               "assistant_ci_lo": round(lo, 4), "assistant_ci_hi": round(hi, 4), "assistant_cut_mean": round(st.mean(asst), 4),
               "retention_mean": 18.0, "retention_sd": ""}
        for b in SIZES:
            kb = sum(r["pass"] for run in per for r in run if r["block"] == b)
            pb, blo, bhi = wilson(kb, SIZES[b] * seeds)
            row[f"rate_{b}"] = round(pb, 4)
            rates.append({"arm_group": g, "method": method, "size": size, "block": b, "k": kb, "n": SIZES[b] * seeds,
                          "rate": round(pb, 4), "ci_lo": round(blo, 4), "ci_hi": round(bhi, 4)})
        for f in ("hv", "num", "or", "inj"):
            xs = [sum(r[f] for r in run) for run in per]
            row[f"{f}_mean"], row[f"{f}_sd"] = round(st.mean(xs), 4), sd(xs)
        trained = method not in ("base", "instruct (reference)")
        row.update({"im_end_share": 0.0 if rows == "no" else 1.0, "train_gpu": "NVIDIA H200" if trained else "",
                    "train_dtype": "bf16" if trained else "", "gpu_h_per_seed": 0.3 if trained else 0.02,
                    "gpu_h_total": 0.3 * seeds, "peak_vram_gb": 30.0, "tokens_per_s": 3000.0 if trained else "",
                    "supervised_tokens_per_s": 400.0 if trained else "", "trainable_params": 64245760 if trained else ""})
        summ.append(row)
        xs = sorted(r["n_tokens"] for run in per for r in run)
        lens.append({"arm_group": g, "method": method, "token_rows": rows, "block": "all", "n": len(xs), "mean": st.mean(xs),
                     "median": st.median(xs), "p90": xs[int(0.9 * len(xs))], "max": xs[-1],
                     "share_at_limit": sum(x >= 200 for x in xs) / len(xs)})
    t = rdir / "tidy"
    write_csv(t / "items_long.csv", long)
    write_csv(t / "arm_summary.csv", summ)
    write_csv(t / "block_rates.csv", rates)
    write_csv(t / "stop_reasons.csv", stops)
    write_csv(t / "lengths.csv", lens)
    write_csv(t / "t_held_classes.csv", [{"arm": f"{g}-s0", "arm_group": g, "item_id": f"T-held-{i:03d}", "held_out_intent": "x",
                                          "class": "abc"[i % 3], "nearest_training_intent": "y", "sim_nearest": 0.9, "sim_own": 0.1}
                                         for g in ("tier_s_main_rslora_tok", "l14b_sft_rslora_tok") for i in range(1, 21)])
    write_csv(t / "b1_tail.csv", [{"arm": "14B rsLoRA lr 1e-4", "run": "l14b_sft_rslora-s0", "seed": 0, "official": 16,
                                   "survive_cut": 0, "tail_only": 16, "cut_only": 0, "fixed_counterpart": 1}])
    write_csv(t / "data_balance.csv", [{"category": "task", "assistant_turns": 100, "ask": 0, "resolve": 100, "share_ask": 0.0},
                                       {"category": "B1", "assistant_turns": 10, "ask": 10, "resolve": 0, "share_ask": 1.0}])
    write_csv(t / "trust.csv", [{"check": "scorer accuracy", "k": 54, "n": 60, "value": 0.9, "ci_lo": 0.8, "ci_hi": 0.95, "note": "x"},
                                {"check": "batch 32 vs 1", "k": 45, "n": 47, "value": -2, "ci_lo": "", "ci_hi": "", "note": "p = 0.69"}])
    write_csv(t / "contamination.csv", [{"corpus": "banking77_train", "corpus_size": 10003, "exact": 0, "fuzzy_ge_90": 23, "ngram8_overlap_pct": 3.02}])
    write_csv(rdir / "lm_head_rows.csv", [{"size": "1.7B", "token": "<|im_end|>", "token_id": 151645, "status": "computed",
                                            "matrix": "embed_tokens (tied)", "nearest_id": 124, "nearest_cos": 1.0, "n_rows_cos_gt_0.99": 2263,
                                            "n_rows_identical": 93, "ref_median_nearest_cos": 0.56, "ref_rows": 500},
                                           {"size": "14B", "token": "<|im_end|>", "token_id": 151645, "status": "pending: not cached",
                                            "matrix": "", "nearest_id": "", "nearest_cos": "", "n_rows_cos_gt_0.99": "",
                                            "n_rows_identical": "", "ref_median_nearest_cos": "", "ref_rows": ""}])
    (rdir / "rewrite_funnel.json").write_text(json.dumps({
        "generator": "gen", "prompts": 10, "stages": [{"stage": "generated", "n": 20}, {"stage": "used", "n": 9}],
        "audits": [{"audit": 1, "filter": "v2", "k_unsupported": 8, "n": 50, "rate": 0.16, "ci_lo": 0.083, "ci_hi": 0.285}],
        "target_rate": 0.05, "decision": "canonical only"}), encoding="utf-8")
    ans = lambda arm, rows: {"arm": arm, "method": "rsLoRA", "token_rows": rows, "pass": 1, "stop_reason": "im_end", "answer": "a | b", "cut": "a"}
    (rdir / "qualitative.jsonl").write_text(json.dumps({"block": "B1", "item_id": "B1-001", "user": "q?", "answers": [
        ans("l14b_sft_rslora_tok-s0", "yes"), ans("l14b_sft_rslora-s0", "no")]}) + "\n", encoding="utf-8")


def fixture_pref(rdir: Path) -> None:
    """F14 (DPO loss per step) and F15 (B1 diagnostic classes)."""
    write_csv(rdir / "tidy" / "pref_loss.csv", [
        {"run": f"pref_dpo_rules-s{s}", "arm_group": "pref_dpo_rules", "method": "DPO", "seed": s, "step": i,
         "loss": round(0.6931 - 0.001 * (i - 1), 4), "chosen_reward": 0.0, "rejected_reward": 0.0, "reward_acc": 0.5}
        for s in range(3) for i in range(1, 43)])
    write_csv(rdir / "tidy" / "b1_classes.csv", [{"arm": "14B rsLoRA v1", "class": c, "count": k, "n": 60}
                                                  for c, k in (("a", 29), ("asks (pass)", 3), ("b", 18), ("c", 1), ("d", 9))])


def test_all_figures_build_and_svgs_are_deterministic(tmp_path):
    rdir = tmp_path / "results"
    fixture(rdir)
    fixture_pref(rdir)
    runs = []
    for k in (1, 2):
        out = tmp_path / f"out{k}"
        status = mf.main(["--results", str(rdir), "--out", str(out), "--docs", str(tmp_path / f"figures{k}.md")])
        assert all(v == "built" for v in status.values()), {k: v for k, v in status.items() if v != "built"}
        runs.append(out)
    for fid in mf.FIGURES:
        for theme in ("light", "dark"):
            for ext in ("png", "svg", "pdf"):
                assert (runs[0] / f"{fid}_{theme}.{ext}").stat().st_size > 0
            a, b = (r / f"{fid}_{theme}.svg" for r in runs)
            assert a.read_bytes() == b.read_bytes(), f"{fid}_{theme}.svg differs between runs"
    for tid in mf.TABLES:
        assert (runs[0] / f"{tid}.md").read_text(encoding="utf-8").strip()
    assert "| pending:" not in (tmp_path / "figures1.md").read_text(encoding="utf-8")


def test_missing_input_is_pending_not_an_error(tmp_path):
    rdir = tmp_path / "results"
    fixture(rdir)
    (rdir / "rewrite_funnel.json").unlink()
    status = mf.main(["--results", str(rdir), "--out", str(tmp_path / "out"), "--only", "F10,F1", "--docs", str(tmp_path / "f.md")])
    assert status["F10"] == "pending: results/rewrite_funnel.json"
    assert status["F1"] == "built"
