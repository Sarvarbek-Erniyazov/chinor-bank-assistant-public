"""Write results/results.md and results/per_category.md from scored arms.

Usage: python eval/summarize.py [--arms a b c]   (default: every arm with scores.jsonl)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from stats import BLOCKS, load_blocks, summarise, wilson

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval" / "outputs"
RESULTS = ROOT / "results"


def rubric_version() -> str:
    m = re.search(r"^Version:\s*(v[\d.]+)", (ROOT / "eval" / "rubric.md").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "v1"


RUBRIC_VERSION = rubric_version()


def fmt_rate(e: dict) -> str:
    if e["n"] == 0:
        return "–"
    return f"{100 * e['rate']:.0f} % [{100 * e['wilson_lo']:.0f}, {100 * e['wilson_hi']:.0f}]"


def fmt_count(e: dict) -> str:
    if e["n"] == 0:
        return "–"
    return f"**{e['k']}** · {fmt_rate(e)}"


def load_answers(arm: str) -> list[dict]:
    p = OUT_DIR / arm / "answers.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def load_run(arm: str) -> dict:
    p = OUT_DIR / arm / "run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def eval_protocol(run: dict) -> str:
    # Protocol A = H200 bf16, Protocol B = T4 fp16 (4-bit arms in 4-bit); see eval/FROZEN.md.
    if run.get("protocol"):
        return run["protocol"]
    gpu = run.get("gpu") or ""
    if "T4" in gpu and (run.get("dtype") == "fp16" or run.get("quant") == "4bit"):
        return "B"
    if "H200" in gpu and run.get("dtype") == "bf16":
        return "A"
    return "?"


def train_gpu_dtype(run: dict) -> str:
    t = run.get("train") or {}
    return f"{t['gpu']} / {t['dtype']}" if t else "—"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=None)
    args = ap.parse_args()
    arms = args.arms or sorted(p.parent.name for p in OUT_DIR.glob("*/scores.jsonl"))
    RESULTS.mkdir(exist_ok=True)

    head = "| Arm | Train GPU/dtype | Eval protocol | Seeds (n) | Assistant /200 | T-seen | T-held | B1 ask | B2 scope | B3 safety | B4 persona | Retention /20 | Hard viol. | Over-refusal | Inj. success | VRAM (GB) | Latency (ms) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    rows, stop_rows, detail = [], [], []
    for arm in arms:
        s = summarise(arm)
        run = load_run(arm)
        answers = load_answers(arm)
        vram = run.get("peak_vram_gb")
        lat = run.get("mean_latency_ms") or (sum(a["latency_ms"] for a in answers) / len(answers) if answers else None)
        asst, ret = s["assistant"], s["retention"]
        rows.append(f"| {arm} | {train_gpu_dtype(run)} | {eval_protocol(run)} | {run.get('seeds', 1)} | {fmt_count(asst)} | {fmt_rate(s['T-seen'])} | {fmt_rate(s['T-held'])} | {fmt_rate(s['B1'])} | {fmt_rate(s['B2'])} | {fmt_rate(s['B3'])} | {fmt_rate(s['B4'])} | {fmt_count(ret)} | {asst['hard_violation']} | {asst['over_refusal']} | {asst['injection_success']} | {vram if vram is None else f'{vram:.1f}'} | {'' if lat is None else f'{lat:.0f}'} |")
        sr = Counter(a.get("stop_reason") for a in answers)
        n = max(1, len(answers))
        stop_rows.append(f"| {arm} | {sr.get('im_end', 0)} ({100 * sr.get('im_end', 0) / n:.0f} %) | {sr.get('endoftext', 0)} ({100 * sr.get('endoftext', 0) / n:.0f} %) | {sr.get('length', 0)} ({100 * sr.get('length', 0) / n:.0f} %) | {run.get('model', '')} | {run.get('git_commit', '')[:8]} |")
        detail.append((arm, s, run))

    md = ["# Results", "",
          "**Assistant score** = passes over the 200 items of T-seen, T-held and B1–B4 (system prompt `handbook/system_prompt.txt`). "
          "**Retention** = passes over the 20 block-R items (no system prompt) and is reported separately; the two are never added. "
          "Rates are shown with Wilson 95 % CI. Flags are counts over the 200 assistant items. "
          "Decoding: greedy, max_new_tokens 200, stop on `<|im_end|>` / `<|endoftext|>`. "
          "Eval protocol A = H200 bf16, B = T4 fp16 (4-bit arms in 4-bit); rows from different protocols are not tested against each other. "
          "Eval set `eval-v1` (see `eval/FROZEN.md`); "
          f"scoring rules `eval/rubric.md` {RUBRIC_VERSION}.", "",
          head + "\n".join(rows), "", "## Stop reasons", "", "| Arm | im_end | endoftext | length | model | commit |", "|---|---|---|---|---|---|", *stop_rows, "",
          "## Assistant score and retention", "",
          "| Arm | assistant pass / 200 | Wilson 95 % | bootstrap 95 % | retention pass / 20 | Wilson 95 % | fabricated numbers (T) |",
          "|---|---|---|---|---|---|---|"]
    for arm, s, run in detail:
        a, r = s["assistant"], s["retention"]
        md.append(f"| {arm} | {a['k']} / {a['n']} | [{100 * a['wilson_lo']:.0f}, {100 * a['wilson_hi']:.0f}] | [{100 * a['boot_lo']:.0f}, {100 * a['boot_hi']:.0f}] | {r['k']} / {r['n']} | [{100 * r['wilson_lo']:.0f}, {100 * r['wilson_hi']:.0f}] | {s['T-seen']['fabricated_number'] + s['T-held']['fabricated_number']} |")
    (RESULTS / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")

    # per category: per block and per intent section / attack type
    blocks = load_blocks()
    items = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "eval" / "eval_set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    pc = ["# Per-category results", ""]
    for arm, s, run in detail:
        scores = {r["id"]: r for r in (json.loads(l) for l in (OUT_DIR / arm / "scores.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
        pc += [f"## {arm}", "", "| Category | pass | n | rate [Wilson 95 %] |", "|---|---|---|---|"]
        cats: dict[str, list[bool]] = {}
        for i, sc in scores.items():
            it = items[i]
            if it["block"].startswith("T"):
                sec = it["notes"].split(";")[0]
                key = f"{it['block']} · {sec}"
            elif it["block"] == "B3":
                key = f"B3 · {it['attack_type']}"
            else:
                key = it["block"]
            cats.setdefault(key, []).append(sc["pass"])
        for key in sorted(cats):
            v = cats[key]
            p, lo, hi = wilson(sum(v), len(v))
            pc.append(f"| {key} | {sum(v)} | {len(v)} | {100 * p:.0f} % [{100 * lo:.0f}, {100 * hi:.0f}] |")
        fails = [f"- `{i}`: {sc['reason']}" for i, sc in scores.items() if not sc["pass"]]
        pc += ["", f"<details><summary>{len(fails)} failing items</summary>", "", *fails, "", "</details>", ""]
    (RESULTS / "per_category.md").write_text("\n".join(pc) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
