"""Derive the tidy evidence tables under results/tidy/ (and a few results/ files) from the run outputs. CPU only.

python results/build_tidy.py [--skip-lm-head]
Every file written here is generated; never edit one by hand. Inputs: eval/outputs/<arm>/ (answers, scores, eval
run.json), results/runs/<arm>/train/run.json, data/sft/, results/c1-rewrites/, eval/audit/, eval/contamination_report.md
and the locally cached base checkpoints (lm_head rows only).

results/tidy/items_long.csv   one row per (arm, item): arm, arm_group, method, size, seed, protocol, token_rows,
                              item_id, block, pass, pass_cut (diagnostic: answer cut at the intended turn end),
                              hv, num, or, inj, stop_reason, n_tokens (Qwen3 tokenizer, generated text)
results/tidy/arm_summary.csv  one row per arm group (seeds pooled; Wilson CI on the pooled k / 200·n)
results/tidy/block_rates.csv  arm group × block: k, n, rate, Wilson 95 % CI
results/tidy/stop_reasons.csv arm × stop reason: count
results/tidy/lengths.csv      arm group × block: n, mean / median / p90 / max n_tokens, share at the 200-token limit
results/tidy/t_held_classes.csv, b1_tail.csv, data_balance.csv, trust.csv, contamination.csv
results/lm_head_rows.csv      cosine of the <|im_start|> / <|im_end|> output rows to their nearest rows
results/rewrite_funnel.json   C1 rewrite generation → filters → used, plus the two manual drift audits
results/qualitative.jsonl     answers of the key arms on fixed items (results/qualitative_ids.json, chosen once)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from negative_results import FIXED as NEG_FIXED, OLD as NEG_OLD  # noqa: E402
from score import Scorer, clean_answer  # noqa: E402
from stats import BLOCKS, in_group, wilson  # noqa: E402
from t_held_analysis import classify  # noqa: E402
from turn_cut import turn_text  # noqa: E402

TIDY = ROOT / "results" / "tidy"
OUT = ROOT / "eval" / "outputs"
RUNS = ROOT / "results" / "runs"
EOS_LIMIT = 200
QUAL_SEED = 20261029
TOK = {151644: "<|im_start|>", 151645: "<|im_end|>"}
# arm group → (method, token_rows); first matching prefix wins
METHODS = [
    ("base-", "base", "n/a"), ("ref-", "instruct (reference)", "n/a"),
    ("tier_s_pilot_rslora", "rsLoRA", "no"), ("tier_s_pilot_dora", "DoRA", "no"), ("tier_s_pilot_lora", "SFT-LoRA", "no"),
    ("l14b_qlora_rslora_tok", "QLoRA", "yes"), ("l14b_qlora", "QLoRA", "no"), ("l14b_full", "full FT", "n/a"),
    ("pref_dpo", "DPO", "yes"), ("pref_simpo", "SimPO", "yes"), ("dpo", "DPO", "yes"), ("simpo", "SimPO", "yes"), ("grpo", "GRPO", "yes"),
]
# the arms whose answers are shown in results/qualitative.jsonl (those that exist)
QUAL_ARMS = ["base-14B-0shot-A", "ref-14B-instruct-A", "l14b_sft_rslora-s0", "l14b_sft_rslora_tok-s0",
             "l14b_qlora_rslora_tok-s0", "l14b_full-s0", "tier_s_main_rslora_tok-s0", "l14b_sft_rslora_tok-s0-v1.2",
             "pref_dpo_rules-s0"]


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["empty"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def r4(x: float) -> float | str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 4)


def arm_meta(arm: str) -> dict:
    m = re.match(r"^(.*?)-s(\d+)(?:-(.+))?$", arm)
    group, seed = (m.group(1) + (f"-{m.group(3)}" if m.group(3) else ""), int(m.group(2))) if m else (arm, "")
    method, rows = next(((me, tr) for p, me, tr in METHODS if group.startswith(p)),
                        ("rsLoRA", "yes" if "_tok" in group else "no"))
    ev = load_json(OUT / arm / "run.json")
    # full FT evaluates a local weights dir: the base model name is in the train run.json
    model = train_info(arm).get("config_values", {}).get("model") or ev.get("model", arm)
    size = re.search(r"(\d+(?:\.\d+)?)B", model) or re.search(r"l(14)b", model)  # pref_*: sft-merged-l14b-...
    # the C0 baselines predate the protocol field; Protocol B = T4 fp16 (plan v3 §2)
    protocol = ev.get("protocol") or ("B" if "T4" in ev.get("gpu", "") else "")
    return {"arm": arm, "arm_group": group, "method": method, "size": f"{size.group(1)}B" if size else "",
            "seed": seed, "protocol": protocol, "token_rows": rows}


def arms() -> list[str]:
    return sorted(p.name for p in OUT.iterdir() if (p / "scores.jsonl").exists() and (p / "answers.jsonl").exists())


def tokenizer():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B-Base", local_files_only=True)


def items_long(all_arms: list[str], blocks: dict[str, str], scorer: Scorer) -> list[dict]:
    tok, rows = tokenizer(), []
    for arm in all_arms:
        meta = arm_meta(arm)
        sc = {r["id"]: r for r in jsonl(OUT / arm / "scores.jsonl")}
        ans = jsonl(OUT / arm / "answers.jsonl")
        lens = [len(x) for x in tok([a["raw"] for a in ans], add_special_tokens=False)["input_ids"]]
        for a, n in zip(ans, lens):
            s = sc[a["id"]]
            f = s["flags"]
            rows.append({**meta, "item_id": a["id"], "block": blocks[a["id"]], "pass": int(s["pass"]),
                         "pass_cut": int(scorer.score(a["id"], turn_text(a["raw"]))["pass"]),
                         "hv": int(f["hard_violation"]), "num": int(f["fabricated_number"]), "or": int(f["over_refusal"]),
                         "inj": int(f["injection_success"]), "stop_reason": a["stop_reason"], "n_tokens": n})
    return rows


def train_info(arm: str) -> dict:
    return load_json(RUNS / arm / "train" / "run.json")


def summaries(long: list[dict]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    by_arm = defaultdict(list)
    for r in long:
        by_arm[r["arm"]].append(r)
    groups = defaultdict(list)
    for arm in by_arm:
        groups[arm_meta(arm)["arm_group"]].append(arm)
    summary, block_rows, stop_rows, len_rows = [], [], [], []
    for g, members in sorted(groups.items()):
        meta = arm_meta(members[0])
        per_seed = []
        for arm in members:
            rs = by_arm[arm]
            asst = [r for r in rs if in_group("assistant", r["block"])]
            per_seed.append({"assistant": sum(r["pass"] for r in asst), "cut": sum(r["pass_cut"] for r in asst),
                             "R": sum(r["pass"] for r in rs if r["block"] == "R"),
                             **{k: sum(r[k] for r in asst) for k in ("hv", "num", "or", "inj")},
                             "im_end": sum(r["stop_reason"] == "im_end" for r in rs) / len(rs)})
        n = len(members)
        k_tot = sum(p["assistant"] for p in per_seed)
        _, lo, hi = wilson(k_tot, 200 * n)
        ms = lambda key: (st.mean(p[key] for p in per_seed), st.stdev(p[key] for p in per_seed) if n > 1 else float("nan"))
        tr = [train_info(a) for a in members]
        ev = [load_json(OUT / a / "run.json") for a in members]
        gpu_h = [((t.get("wall_clock_s") or 0) + (e.get("wall_clock_s") or 0)) / 3600 for t, e in zip(tr, ev)]
        tmean = lambda key: r4(st.mean(t[key] for t in tr)) if tr and all(t.get(key) is not None for t in tr) else ""
        row = {**{k: meta[k] for k in ("arm_group", "method", "size", "protocol", "token_rows")}, "seeds": n,
               "assistant_mean": r4(ms("assistant")[0]), "assistant_sd": r4(ms("assistant")[1]),
               "assistant_rate": r4(k_tot / (200 * n)), "assistant_ci_lo": r4(lo), "assistant_ci_hi": r4(hi),
               "assistant_cut_mean": r4(ms("cut")[0]), "retention_mean": r4(ms("R")[0]), "retention_sd": r4(ms("R")[1])}
        for b in BLOCKS:
            k = sum(r["pass"] for a in members for r in by_arm[a] if r["block"] == b)
            nb = sum(1 for a in members for r in by_arm[a] if r["block"] == b)
            p, blo, bhi = wilson(k, nb)
            row[f"rate_{b}"] = r4(p)
            block_rows.append({"arm_group": g, "method": meta["method"], "size": meta["size"], "block": b, "k": k, "n": nb,
                               "rate": r4(p), "ci_lo": r4(blo), "ci_hi": r4(bhi)})
        for key in ("hv", "num", "or", "inj"):
            m, s = ms(key)
            row[f"{key}_mean"], row[f"{key}_sd"] = r4(m), r4(s)
        row["im_end_share"] = r4(ms("im_end")[0])
        row["train_gpu"] = tr[0].get("gpu", "") if tr and tr[0] else ""
        row["train_dtype"] = (tr[0].get("dtype", "") + (" + NF4 base" if meta["method"] == "QLoRA" else "")) if tr and tr[0] else ""
        row["gpu_h_per_seed"] = r4(st.mean(gpu_h))
        row["gpu_h_total"] = r4(sum(gpu_h))
        row["peak_vram_gb"] = tmean("peak_vram_gb") or r4(st.mean(e.get("peak_vram_gb") or 0 for e in ev))
        row["tokens_per_s"] = tmean("tokens_per_s")
        row["supervised_tokens_per_s"] = tmean("supervised_tokens_per_s")
        row["trainable_params"] = tr[0].get("trainable_parameters", {}).get("trainable", "") if tr and tr[0] else ""
        summary.append(row)
        for arm in members:
            for reason, c in sorted(Counter(r["stop_reason"] for r in by_arm[arm]).items()):
                stop_rows.append({"arm": arm, "arm_group": g, "method": meta["method"], "token_rows": meta["token_rows"],
                                  "stop_reason": reason, "count": c})
        for b in BLOCKS + ["all"]:
            xs = sorted(r["n_tokens"] for a in members for r in by_arm[a] if b == "all" or r["block"] == b)
            len_rows.append({"arm_group": g, "method": meta["method"], "token_rows": meta["token_rows"], "block": b,
                             "n": len(xs), "mean": r4(st.mean(xs)), "median": st.median(xs),
                             "p90": xs[min(len(xs) - 1, int(0.9 * len(xs)))], "max": xs[-1],
                             "share_at_limit": r4(sum(x >= EOS_LIMIT for x in xs) / len(xs))})
    return summary, block_rows, stop_rows, len_rows


def t_held_rows(all_arms: list[str]) -> list[dict]:
    keep = [a for a in all_arms if re.match(r"(tier_s_main_rslora|l14b_sft_rslora|l14b_qlora_rslora|l14b_full)", a)]
    return [{"arm": a, "arm_group": arm_meta(a)["arm_group"], "item_id": r["id"], "held_out_intent": r["intent"],
             "class": r["cls"], "nearest_training_intent": r["near"], "sim_nearest": r4(r["sim"]), "sim_own": r4(r["own"])}
            for a in keep for r in classify(a)]


def b1_tail(blocks: dict[str, str], scorer: Scorer) -> list[dict]:
    ids = [i for i, b in blocks.items() if b == "B1"]
    rows = []
    for name, prefix in NEG_OLD.items():
        for s in range(3):
            run = f"{prefix}-s{s}"
            if not (OUT / run / "scores.jsonl").exists():
                continue
            off = {r["id"]: r["pass"] for r in jsonl(OUT / run / "scores.jsonl")}
            ans = {a["id"]: a["raw"] for a in jsonl(OUT / run / "answers.jsonl")}
            cut = {i: scorer.score(i, turn_text(ans[i]))["pass"] for i in ids}
            fx = OUT / f"{NEG_FIXED[prefix]}-s{s}" / "scores.jsonl"
            fixed = sum(r["pass"] for r in jsonl(fx) if r["id"] in ids) if fx.exists() else ""
            rows.append({"arm": name, "run": run, "seed": s, "official": sum(off[i] for i in ids),
                         "survive_cut": sum(off[i] and cut[i] for i in ids), "tail_only": sum(off[i] and not cut[i] for i in ids),
                         "cut_only": sum(cut[i] and not off[i] for i in ids), "fixed_counterpart": fixed})
    return rows


def data_balance() -> list[dict]:
    per, q = Counter(), Counter()
    for ex in jsonl(ROOT / "data" / "sft" / "v1" / "train.jsonl"):
        for m in ex["messages"]:
            if m["role"] == "assistant":
                per[ex["category"]] += 1
                q[ex["category"]] += "?" in m["content"]
    return [{"category": c, "assistant_turns": per[c], "ask": q[c], "resolve": per[c] - q[c], "share_ask": r4(q[c] / per[c])}
            for c in sorted(per)]


def audit_rate(path: Path, col: str) -> tuple[int, int]:
    with path.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get(col, "").strip() != ""]
    return sum(int(r[col]) for r in rows), len(rows)


def trust(long: list[dict]) -> list[dict]:
    """Scorer accuracy (hand audit), protocol and batch robustness, judge validation."""
    rows = []
    with (ROOT / "eval" / "audit" / "base-1.7B-0shot.csv").open(encoding="utf-8-sig") as f:
        aud = [r for r in csv.DictReader(f) if r["in_sample"] == "1" and r["manual_pass"] != ""]
    k = sum(r["manual_pass"] == r["auto_pass"] for r in aud)
    p, lo, hi = wilson(k, len(aud))
    rows.append({"check": "scorer pass/fail accuracy vs hand marks (base-1.7B, rubric v1 sheet)", "k": k, "n": len(aud),
                 "value": r4(p), "ci_lo": r4(lo), "ci_hi": r4(hi), "note": "threshold >= 0.85"})
    by = defaultdict(dict)
    for r in long:
        by[r["arm"]][r["item_id"]] = r
    for a, b, what in [("base-1.7B-0shot-A", "base-1.7B-0shot", "Protocol A (H200 bf16) vs B (T4 fp16), base-1.7B"),
                       ("base-14B-0shot-A", "base-14B-0shot-A-bs1", "eval batch 32 vs 1, base-14B")]:
        if a in by and b in by:
            ids = [i for i in by[a] if in_group("assistant", by[a][i]["block"])]
            ka, kb = sum(by[a][i]["pass"] for i in ids), sum(by[b][i]["pass"] for i in ids)
            disc = (sum(by[a][i]["pass"] and not by[b][i]["pass"] for i in ids), sum(by[b][i]["pass"] and not by[a][i]["pass"] for i in ids))
            from scipy.stats import binomtest
            pv = binomtest(min(disc), sum(disc), 0.5).pvalue if sum(disc) else 1.0
            rows.append({"check": what, "k": ka, "n": kb, "value": ka - kb, "ci_lo": "", "ci_hi": "",
                         "note": f"Assistant /200 {ka} vs {kb}; discordant {disc[0]} / {disc[1]}; exact McNemar p = {pv:.2f}"})
    rows += audit_14b(long)
    j = load_json(ROOT / "results" / "runs" / "judge-validate-v1" / "summary_v1.json")
    if j:
        c = j["confusion"]
        rows.append({"check": f"entailment judge vs hand marks ({j['judge']})", "k": c["marked_flagged"],
                     "n": c["marked_flagged"] + c["marked_passed"], "value": r4(c["marked_flagged"] / (c["marked_flagged"] + c["marked_passed"])),
                     "ci_lo": "", "ci_hi": "", "note": f"false flags {c['unmarked_flagged']} / {c['unmarked_flagged'] + c['unmarked_passed']} unmarked; {j['thresholds']}"})
    return rows


def audit_14b(long: list[dict]) -> list[dict]:
    """The 14B audit (eval/audit/14b-lora-s0.csv marks, .auto.csv verdicts) and the audit-corrected Assistant /200 of the
    14B v1.2 seeds (exploratory): auto_pass x P(manual pass | auto pass) + auto_fail x P(manual pass | auto fail),
    95 % bootstrap CI over the 60 audit rows (10,000 resamples, seed 20261029)."""
    sheet, auto = ROOT / "eval" / "audit" / "14b-lora-s0.csv", ROOT / "eval" / "audit" / "14b-lora-s0.auto.csv"
    with sheet.open(encoding="utf-8-sig") as f:
        man = {r["id"]: r["manual_pass"].strip() for r in csv.DictReader(f)}
    if "" in man.values():
        return []
    with auto.open(encoding="utf-8-sig") as f:
        aut = {r["id"]: int(r["auto_pass"]) for r in csv.DictReader(f)}
    pairs = [(aut[i], int(m)) for i, m in man.items()]
    k = sum(a == m for a, m in pairs)
    p, lo, hi = wilson(k, len(pairs))
    ap = [m for a, m in pairs if a]
    af = [m for a, m in pairs if not a]
    p1, lo1, hi1 = wilson(sum(ap), len(ap))
    out = [{"check": "scorer pass/fail accuracy vs hand marks (14B rsLoRA seed 0, rubric v1.3)", "k": k, "n": len(pairs),
            "value": r4(p), "ci_lo": r4(lo), "ci_hi": r4(hi),
            "note": f"threshold >= 0.85 (met); {sum(a and not m for a, m in pairs)} of {len(pairs) - k} errors lenient "
                    f"(auto pass, manual fail): automatic scores are upper bounds. Marks made against rubric v1.3 and the "
                    f"handbook before the marking checklist existed; not re-marked."},
           {"check": "manual pass among auto passes (14B audit)", "k": sum(ap), "n": len(ap), "value": r4(p1), "ci_lo": r4(lo1),
            "ci_hi": r4(hi1), "note": f"manual pass among auto fails: {sum(af)}/{len(af)}"}]
    rng = np.random.default_rng(20261029)
    arr = np.array(pairs)
    boots = []
    for _ in range(10_000):
        b = arr[rng.integers(0, len(arr), len(arr))]
        pa, pf = b[b[:, 0] == 1, 1], b[b[:, 0] == 0, 1]
        if len(pa) and len(pf):
            boots.append((pa.mean(), pf.mean()))
    boots = np.array(boots)
    for s in range(5):
        arm = f"l14b_sft_rslora_tok-s{s}-v1.2"
        rs = [r for r in long if r["arm"] == arm and in_group("assistant", r["block"])]
        if not rs:
            continue
        P = sum(r["pass"] for r in rs)
        F = len(rs) - P
        est = P * sum(ap) / len(ap) + F * sum(af) / len(af)
        dist = P * boots[:, 0] + F * boots[:, 1]
        clo, chi = np.percentile(dist, [2.5, 97.5])
        out.append({"check": f"audit-corrected Assistant /200, `{arm}` (exploratory)", "k": P, "n": len(rs),
                    "value": r4(est / len(rs)), "ci_lo": r4(clo / len(rs)), "ci_hi": r4(chi / len(rs)),
                    "note": f"auto {P}/200 -> corrected {est:.1f} [{clo:.1f}, {chi:.1f}]; derived from a single 60-item audit "
                            f"(P(manual pass | auto pass) {sum(ap)}/{len(ap)}, | auto fail {sum(af)}/{len(af)}); rubric v1.3, no rescoring"})
    return out


def pref_loss() -> list[dict]:
    """Per-step preference loss and rewards of every pref_* run (results/runs/<run>/train/loss.csv), for F14."""
    rows = []
    for d in sorted(RUNS.glob("pref_*")):
        p = d / "train" / "loss.csv"
        if not p.exists():
            continue
        m = arm_meta(d.name)
        with p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append({"run": d.name, "arm_group": m["arm_group"], "method": m["method"], "seed": m["seed"],
                             "step": int(r["step"]), "loss": r4(float(r["loss"])), "chosen_reward": r4(float(r["chosen_reward"])),
                             "rejected_reward": r4(float(r["rejected_reward"])), "reward_acc": r4(float(r["reward_acc"]))})
    return rows


def contamination() -> list[dict]:
    text = (ROOT / "eval" / "contamination_report.md").read_text(encoding="utf-8")
    rows = []
    for sec in re.split(r"\n## ", text)[1:]:
        name = sec.split("\n", 1)[0].strip()
        ex = re.search(r"exact matches: \*\*(\d+)\*\*", sec)
        if not ex:
            continue
        rows.append({"corpus": name, "corpus_size": int(re.search(r"corpus size: (\d+)", sec).group(1)),
                     "exact": int(ex.group(1)), "fuzzy_ge_90": int(re.search(r"fuzzy matches \(ratio ≥ 90\): (\d+)", sec).group(1)),
                     "ngram8_overlap_pct": float(re.search(r"8-gram overlap rate: ([\d.]+) %", sec).group(1))})
    return rows


def lm_head_rows() -> list[dict]:
    """Nearest-row cosine of the two chat special tokens in each base checkpoint's output matrix (CPU, cached weights)."""
    import torch
    from safetensors import safe_open
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    rows = []
    for size in ["0.6B", "1.7B", "4B", "8B", "14B"]:
        snaps = sorted((hub / f"models--Qwen--Qwen3-{size}-Base" / "snapshots").glob("*"))
        if not snaps:
            rows += [{"size": size, "token": TOK[t], "token_id": t, "status": "pending: checkpoint not cached locally"} for t in TOK]
            continue
        snap = snaps[-1]
        cfg = load_json(snap / "config.json")
        name = "model.embed_tokens.weight" if cfg.get("tie_word_embeddings") else "lm_head.weight"
        shard = snap / "model.safetensors"
        if not shard.exists():
            idx = load_json(snap / "model.safetensors.index.json")
            shard = snap / idx["weight_map"][name]
        with safe_open(str(shard), framework="pt") as f:
            w = f.get_tensor(name).float()
        wn = torch.nn.functional.normalize(w, dim=1)
        ref_ids = random.Random(QUAL_SEED).sample(range(151643), 500)
        ref_nn = []
        for i in ref_ids:
            c = wn @ wn[i]
            c[i] = -2
            ref_nn.append(c.max().item())
        for t in TOK:
            c = wn @ wn[t]
            c[t] = -2
            nn = int(c.argmax())
            rows.append({"size": size, "token": TOK[t], "token_id": t, "status": "computed",
                         "matrix": "embed_tokens (tied)" if cfg.get("tie_word_embeddings") else "lm_head",
                         "nearest_id": nn, "nearest_cos": r4(c[nn].item()), "n_rows_cos_gt_0.99": int((c > 0.99).sum()),
                         "n_rows_identical": int((w == w[t]).all(dim=1).sum()) - 1,
                         "ref_median_nearest_cos": r4(st.median(ref_nn)), "ref_rows": len(ref_ids)})
        del w, wn
    return rows


def rewrite_funnel() -> dict:
    c1 = ROOT / "results" / "c1-rewrites"
    v1 = jsonl(c1 / "verdicts_v1.jsonl")
    v2 = jsonl(c1 / "verdicts_v2.jsonl")
    ent = jsonl(c1 / "entail_verdicts.jsonl")
    stats = load_json(ROOT / "data" / "sft" / "v1_rewrite" / "assemble_stats.json")
    a1, n1 = audit_rate(ROOT / "eval" / "audit" / "rewrites_sample.csv", "manual_unsupported_claim")
    a2, n2 = audit_rate(ROOT / "eval" / "audit" / "rewrites_sample_2.csv", "manual_unsupported_claim")
    w1, w2 = wilson(a1, n1), wilson(a2, n2)
    return {"generator": load_json(c1 / "run.json").get("model"), "prompts": load_json(c1 / "run.json").get("n_prompts"),
            "stages": [{"stage": "generated candidates", "n": len(v1)},
                       {"stage": "verifier v1 accept", "n": sum(r["accept"] for r in v1)},
                       {"stage": "verifier v2 accept", "n": sum(r["accept"] for r in v2)},
                       {"stage": "entailment judge: all sentences entailed", "n": sum(r["entailed"] for r in ent)},
                       {"stage": "used in SFT v1_rewrite (train + val)",
                        "n": stats["by_source"]["train"].get("rewrite", 0) + stats["by_source"]["val"].get("rewrite", 0)}],
            "audits": [{"audit": 1, "filter": "verifier v2", "k_unsupported": a1, "n": n1, "rate": r4(w1[0]), "ci_lo": r4(w1[1]), "ci_hi": r4(w1[2])},
                       {"audit": 2, "filter": "verifier v2 + entailment", "k_unsupported": a2, "n": n2, "rate": r4(w2[0]), "ci_lo": r4(w2[1]), "ci_hi": r4(w2[2])}],
            "target_rate": 0.05, "decision": "SFT v1 uses canonical answers only (ADR-024)"}


def qualitative(long: list[dict]) -> list[dict]:
    """Fixed items, one per block, drawn once (seed 20261029) and stored before the final arms exist."""
    ids_path = ROOT / "results" / "qualitative_ids.json"
    items = {it["id"]: it for it in jsonl(ROOT / "eval" / "eval_set.jsonl")}
    if not ids_path.exists():
        rng = random.Random(QUAL_SEED)
        chosen = {b: rng.choice(sorted(i for i, it in items.items() if it["block"] == b)) for b in BLOCKS}
        ids_path.write_text(json.dumps({"seed": QUAL_SEED, "chosen": chosen}, indent=2) + "\n", encoding="utf-8", newline="\n")
    chosen = json.loads(ids_path.read_text(encoding="utf-8"))["chosen"]
    passes = {(r["arm"], r["item_id"]): r for r in long}
    out = []
    for b, i in chosen.items():
        rec = {"block": b, "item_id": i, "user": [m["content"] for m in items[i]["messages"] if m["role"] == "user"][-1], "answers": []}
        for arm in QUAL_ARMS:
            p = OUT / arm / "answers.jsonl"
            if not p.exists():
                continue
            a = next(x for x in jsonl(p) if x["id"] == i)
            r = passes[(arm, i)]
            rec["answers"].append({"arm": arm, "method": r["method"], "token_rows": r["token_rows"], "pass": r["pass"],
                                   "hv": r["hv"], "num": r["num"], "stop_reason": a["stop_reason"], "answer": clean_answer(a["raw"]), "cut": turn_text(a["raw"])})
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-lm-head", action="store_true", help="keep the existing results/lm_head_rows.csv")
    args = ap.parse_args()
    blocks = {it["id"]: it["block"] for it in jsonl(ROOT / "eval" / "eval_set.jsonl")}
    scorer, all_arms = Scorer(), arms()
    long = items_long(all_arms, blocks, scorer)
    write_csv(TIDY / "items_long.csv", long)
    summary, block_rows, stop_rows, len_rows = summaries(long)
    for name, rows in [("arm_summary", summary), ("block_rates", block_rows), ("stop_reasons", stop_rows),
                       ("lengths", len_rows), ("t_held_classes", t_held_rows(all_arms)), ("b1_tail", b1_tail(blocks, scorer)),
                       ("data_balance", data_balance()), ("trust", trust(long)), ("pref_loss", pref_loss()), ("contamination", contamination())]:
        write_csv(TIDY / f"{name}.csv", rows)
    if not args.skip_lm_head or not (ROOT / "results" / "lm_head_rows.csv").exists():
        write_csv(ROOT / "results" / "lm_head_rows.csv", lm_head_rows())
    (ROOT / "results" / "rewrite_funnel.json").write_text(json.dumps(rewrite_funnel(), indent=2) + "\n", encoding="utf-8", newline="\n")
    with (ROOT / "results" / "qualitative.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for rec in qualitative(long):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"{len(all_arms)} arms, {len(long)} item rows, {len(summary)} arm groups -> {TIDY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
