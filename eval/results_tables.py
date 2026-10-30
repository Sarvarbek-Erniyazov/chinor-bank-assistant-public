"""Seed-aggregated results tables: results/seeds.md (every training run) and one table per arm group.

python eval/results_tables.py
Per group: one row per seed and a mean ± std row for Assistant /200, every block, retention /20 and the four scorer
flags (hard violations, fabricated numbers, over-refusal, injection success; counted on the 200 assistant items),
plus exact McNemar of each seed vs the base model of the same size (0-shot, Protocol A). Groups whose runs do not
exist yet are skipped. Scores are the official ones (eval/score.py, rubric v1.3). Every run also gets its stop
reasons (share of the 220 answers ending on <|im_end|>; acceptance for the fixed arms: >= 95 %) and, as a diagnostic
only, "Assistant /200 if cut at the intended end" (eval/turn_cut.py). results/lora_no_token_rows.md is the ablation
row "LoRA without trainable special-token rows" (ADR-023 amendment).
"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter
from pathlib import Path

from score import Scorer
from stats import BLOCKS, in_group, load_blocks, load_scores, mcnemar_exact
from turn_cut import turn_text

ROOT = Path(__file__).resolve().parents[1]
FLAGS = [("hard_violation", "HV"), ("fabricated_number", "NUM"), ("over_refusal", "OR"), ("injection_success", "INJ")]
GROUPS = {  # results file: (title, run prefix, seeds, base arm); *_tok = trainable special-token rows (fixed)
    "tier_s_main_tok.md": ("Tier-S main (fixed): 1.7B SFT rsLoRA + trainable special-token rows", "tier_s_main_rslora_tok", 3, "base-1.7B-0shot-A"),
    "l14b_sft_tok.md": ("Tier-L (fixed): 14B SFT rsLoRA lr 1e-4 + trainable special-token rows", "l14b_sft_rslora_tok", 3, "base-14B-0shot-A"),
    "l14b_qlora_tok.md": ("Tier-L (fixed): 14B QLoRA rsLoRA + trainable special-token rows (eval on the NF4 base)", "l14b_qlora_rslora_tok", 3, "base-14B-0shot-A"),
    "l14b_full.md": ("Tier-L: Qwen3-14B-Base full fine-tuning", "l14b_full", 2, "base-14B-0shot-A"),
    "tier_s_main.md": ("Tier-S main without trainable special-token rows: 1.7B SFT rsLoRA (ADR-025)", "tier_s_main_rslora", 3, "base-1.7B-0shot-A"),
    "l14b_sft.md": ("Tier-L without trainable special-token rows: 14B SFT rsLoRA, lr 1e-4", "l14b_sft_rslora", 3, "base-14B-0shot-A"),
}
SEED_PREFIXES = ["tier_s_main_rslora_tok", "l14b_sft_rslora_tok", "l14b_qlora_rslora_tok", "size_4b_rslora_tok",
                 "size_8b_rslora_tok", "l14b_full", "tier_s_pilot_lora", "tier_s_pilot_rslora", "tier_s_pilot_dora",
                 "tier_s_pilot_lora_paged8", "tier_s_pilot_lora_nogroup", "tier_s_main_rslora", "l14b_sft_rslora"]
NO_ROWS = [("0.6B plain LoRA (pilot)", "tier_s_pilot_lora", 3), ("0.6B rsLoRA (pilot)", "tier_s_pilot_rslora", 3),
           ("0.6B DoRA (pilot)", "tier_s_pilot_dora", 3), ("0.6B LoRA paged 8-bit (pilot)", "tier_s_pilot_lora_paged8", 3),
           ("0.6B LoRA group_by_length false (pilot)", "tier_s_pilot_lora_nogroup", 1),
           ("1.7B rsLoRA (Tier-S main)", "tier_s_main_rslora", 3), ("14B rsLoRA lr 1e-4", "l14b_sft_rslora", 3)]
FIXED_OF = {"tier_s_main_rslora": "tier_s_main_rslora_tok", "l14b_sft_rslora": "l14b_sft_rslora_tok"}
SCORER = Scorer()


def exists(run: str) -> bool:
    return (ROOT / "eval" / "outputs" / run / "scores.jsonl").exists()


def counts(run: str, blocks: dict[str, str]) -> dict:
    sc = load_scores(run)
    c = {b: sum(r["pass"] for i, r in sc.items() if blocks[i] == b) for b in BLOCKS}
    asst = [i for i in sc if in_group("assistant", blocks[i])]
    c["assistant"] = sum(sc[i]["pass"] for i in asst)
    for f, _ in FLAGS:
        c[f] = sum(sc[i]["flags"][f] for i in asst)
    p = ROOT / "eval" / "outputs" / run / "answers.jsonl"
    ans = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    c["stops"] = Counter(a["stop_reason"] for a in ans)
    c["im_end"] = round(100 * c["stops"].get("im_end", 0) / len(ans), 1)
    c["cut"] = sum(SCORER.score(a["id"], turn_text(a["raw"]))["pass"] for a in ans if in_group("assistant", blocks[a["id"]]))
    return c


def stops(c: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(c["stops"].items(), key=lambda x: -x[1]))


def train_run(run: str) -> dict:
    p = ROOT / "results" / "runs" / run / "train" / "run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def mean_std(xs: list[float]) -> str:
    return f"{st.mean(xs):.1f}" if len(xs) < 2 else f"{st.mean(xs):.1f} ± {st.stdev(xs):.1f}"


def group_table(title: str, prefix: str, n: int, base: str, blocks: dict[str, str]) -> list[str] | None:
    runs = [f"{prefix}-s{s}" for s in range(n) if exists(f"{prefix}-s{s}")]
    if not runs:
        return None
    ids = [i for i in blocks if in_group("assistant", blocks[i])]
    cols = ["assistant"] + BLOCKS + [f for f, _ in FLAGS] + ["im_end", "cut"]
    head = (["Assistant /200"] + BLOCKS + [short for _, short in FLAGS]
            + ["<|im_end|> stops %", "diagnostic: Assistant if cut at intended end"])
    L = [f"# {title}", "", "`eval/results_tables.py`. Protocol A, rubric v1.3, SFT v1 (canonical, ADR-024). Flags "
         "counted on the 200 assistant items: HV hard violation, NUM fabricated number, OR over-refusal, INJ injection "
         "success. McNemar: exact, 200 assistant items, run vs base. Stop reasons per run below the table; the "
         "diagnostic cut column is never the official score.", "",
         "| Arm | " + " | ".join(head) + " | McNemar vs base (run-only / base-only, p) |",
         "|---|" + "---|" * (len(head) + 1)]
    bsc = load_scores(base)
    bc = counts(base, blocks)
    L.append(f"| `{base}` (base) | " + " | ".join(str(bc[c]) for c in cols) + " | — |")
    per = []
    for r in runs:
        c = counts(r, blocks)
        per.append(c)
        sc = load_scores(r)
        m = mcnemar_exact([sc[i]["pass"] for i in ids], [bsc[i]["pass"] for i in ids])
        L.append(f"| `{r}` | " + " | ".join(str(c[k]) for k in cols) + f" | {m['a_only']} / {m['b_only']}, p = {m['p_value']:.1e} |")
    L.append(f"| **mean ± std (n = {len(runs)})** | " + " | ".join(mean_std([c[k] for c in per]) for k in cols) + " | |")
    L += ["", "Stop reasons (220 answers): " + "; ".join(f"`{r}` {stops(c)}" for r, c in zip(runs, per)) + "."]
    if prefix.endswith("_tok"):
        ok = all(c["im_end"] >= 95 for c in per)
        L.append(f"Acceptance (>= 95 % of answers stop on <|im_end|>, every run): **{'pass' if ok else 'FAIL'}**.")
    return L + [""]


def ablation_no_rows(blocks: dict[str, str]) -> None:
    L = ["# Ablation: LoRA without trainable special-token rows", "",
         "`eval/results_tables.py`. Runs trained before the ADR-023 amendment: `<|im_start|>` / `<|im_end|>` rows "
         "frozen, so the models never emit `<|im_end|>` and run on to the 200-token limit (`docs/limitations.md`). "
         "Official score = rubric v1.3 on the whole answer; the diagnostic cut column (`eval/turn_cut.py`) is never "
         "official. The 0.6B pilot matrix is not rerun: all its arms share the flaw, and the rsLoRA decision "
         "(ADR-025) holds after the cut. Fixed counterpart = same config + trainable rows, where it exists.", "",
         "| Arm | n | Official Assistant /200 | Diagnostic: cut at intended end | <|im_end|> stops % | "
         "Fixed counterpart: official Assistant /200 | Fixed: <|im_end|> stops % |",
         "|---|---|---|---|---|---|---|"]
    for name, prefix, n in NO_ROWS:
        per = [counts(f"{prefix}-s{s}", blocks) for s in range(n) if exists(f"{prefix}-s{s}")]
        if not per:
            continue
        fx = [counts(f"{FIXED_OF[prefix]}-s{s}", blocks) for s in range(3)
              if prefix in FIXED_OF and exists(f"{FIXED_OF[prefix]}-s{s}")]
        L.append(f"| {name} | {len(per)} | {mean_std([c['assistant'] for c in per])} | {mean_std([c['cut'] for c in per])} | "
                 f"{mean_std([c['im_end'] for c in per])} | {mean_std([c['assistant'] for c in fx]) if fx else '—'} | "
                 f"{mean_std([c['im_end'] for c in fx]) if fx else '—'} |")
    (ROOT / "results" / "lora_no_token_rows.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L))


def main():
    blocks = load_blocks()
    for fname, (title, prefix, n, base) in GROUPS.items():
        L = group_table(title, prefix, n, base, blocks)
        if L:
            (ROOT / "results" / fname).write_text("\n".join(L), encoding="utf-8", newline="\n")
    ablation_no_rows(blocks)
    S = ["# Seeds — every training run", "", "`eval/results_tables.py`. Official scores (rubric v1.3); flags on the "
         "200 assistant items; diagnostic cut column never official.", "",
         "| Run | Config | Seed | Assistant /200 | Retention /20 | HV | NUM | OR | INJ | <|im_end|> stops % | "
         "diag. cut Assistant | Final train loss | Final val loss | Peak VRAM (GB) | Tokens/s |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for prefix in SEED_PREFIXES:
        for s in range(3):
            r = f"{prefix}-s{s}"
            if not exists(r):
                continue
            c, t = counts(r, blocks), train_run(r)
            fl = lambda k, d=4: f"{t[k]:.{d}f}" if t.get(k) is not None else "—"
            S.append(f"| `{r}` | `{t.get('config', '—')}` | {s} | {c['assistant']} | {c['R']} | "
                     + " | ".join(str(c[f]) for f, _ in FLAGS) + f" | {c['im_end']} | {c['cut']}"
                     + f" | {fl('final_train_loss')} | {fl('final_val_loss')} | {t.get('peak_vram_gb', '—')} | "
                     + (f"{t['tokens_per_s']:,.0f}" if t.get("tokens_per_s") else "—") + " |")
    (ROOT / "results" / "seeds.md").write_text("\n".join(S) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
