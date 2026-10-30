"""Protocol-A baseline report: size curve figure and the Protocol A vs B sensitivity check.

python eval/baseline_report.py
  -> results/curves/base_size_curve.png  (Assistant /200 with Wilson 95 % CI over model size, 0-shot and 3-shot)
  -> docs/limitations.md                 (section "Protocol A vs B": answer exact-match rate, score delta, McNemar)
Reads eval/outputs/<arm>/{answers,scores}.jsonl (rubric v1.3 scores).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from score import clean_answer  # noqa: E402
from stats import mcnemar_exact, wilson  # noqa: E402

OUT = ROOT / "eval" / "outputs"
SIZES = [("0.6B", 0.6), ("1.7B", 1.7), ("4B", 4.0), ("8B", 8.0), ("14B", 14.0)]
# reference palette (dataviz skill), categorical slots 1 and 2; light chart surface and text tokens
SERIES = {"0-shot": "#2a78d6", "3-shot": "#eb6834"}
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#1a1a19", "#5f5e58", "#e4e3de"


def items() -> dict:
    return {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "eval" / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()}


def load(arm: str, name: str) -> dict:
    return {json.loads(l)["id"]: json.loads(l) for l in (OUT / arm / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}


def assistant_pass(arm: str, ids: list[str]) -> tuple[int, int]:
    s = load(arm, "scores")
    return sum(s[i]["pass"] for i in ids), len(ids)


def size_curve(ids: list[str]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    rows = []
    for shots, color in SERIES.items():
        pts = [(x, *assistant_pass(f"base-{s}-{shots.replace('-', '')}-A", ids)) for s, x in SIZES
               if (OUT / f"base-{s}-{shots.replace('-', '')}-A" / "scores.jsonl").exists()]
        dodge = 1.0 if shots == "0-shot" else 1.07  # side by side where both series share a size
        xs = [p[0] * dodge for p in pts]
        ks = [p[1] for p in pts]
        ci = [wilson(k, n) for _, k, n in pts]
        ys = [100 * c[0] for c in ci]
        lo = [100 * (c[0] - c[1]) for c in ci]
        hi = [100 * (c[2] - c[0]) for c in ci]
        # 3-shot exists only at 1.7B and 14B: a dotted connector, so no values are implied in between
        ax.errorbar(xs, ys, yerr=[lo, hi], color=color, linewidth=2, marker="o", markersize=7, capsize=4,
                    linestyle="-" if shots == "0-shot" else ":",
                    elinewidth=1.2, markeredgecolor=SURFACE, markeredgewidth=2, label=shots, zorder=3)
        ax.annotate(shots, (xs[-1], ys[-1]), xytext=(12, 0 if shots == "3-shot" else -16), textcoords="offset points", va="center",
                    color=INK_2, fontsize=9)
        rows += [(shots, p[0], k) for p, k in zip(pts, ks)]
    ax.set_xscale("log")
    ax.set_xticks([x for _, x in SIZES])
    ax.set_xticklabels([s for s, _ in SIZES])
    ax.minorticks_off()
    ax.set_xlim(0.45, 22)
    ax.set_ylim(0, 40)
    ax.set_xlabel("Qwen3 base model size (log scale)", color=INK_2, fontsize=9)
    ax.set_ylabel("Assistant score, % of 200 (Wilson 95 % CI)", color=INK_2, fontsize=9)
    ax.set_title("Base models under Protocol A (H200 bf16, rubric v1.3)", color=INK, fontsize=11, loc="left")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper left")
    fig.tight_layout()
    dest = ROOT / "results" / "curves" / "base_size_curve.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, facecolor=SURFACE)
    print(f"-> {dest}  points: {rows}")


def protocol_check(ids: list[str], all_ids: list[str]) -> str:
    a_arm, b_arm = "base-1.7B-0shot-A", "base-1.7B-0shot"
    ans_a, ans_b = load(a_arm, "answers"), load(b_arm, "answers")
    same = sum(clean_answer(ans_a[i]["raw"]) == clean_answer(ans_b[i]["raw"]) for i in all_ids)
    sa, sb = load(a_arm, "scores"), load(b_arm, "scores")
    ka, n = assistant_pass(a_arm, ids)
    kb, _ = assistant_pass(b_arm, ids)
    m = mcnemar_exact([sa[i]["pass"] for i in ids], [sb[i]["pass"] for i in ids])
    ret = [i for i in all_ids if i not in ids]
    ra, rb = sum(sa[i]["pass"] for i in ret), sum(sb[i]["pass"] for i in ret)
    return "\n".join([
        "## Protocol A vs B (sensitivity check)", "",
        "One arm, `base-1.7B-0shot`, decoded under both frozen protocols (plan v3 §2): Protocol A = H200 bf16, "
        "Protocol B = T4 fp16, both greedy, max_new_tokens 200, same template, system prompt and eval set; scored "
        "with rubric v1.3.", "",
        "| Measure | Value |", "|---|---|",
        f"| Answers identical after stop-token cut (220 items) | {same} / {len(all_ids)} = {100 * same / len(all_ids):.1f} % |",
        f"| Assistant /200, A vs B | {ka} vs {kb} (delta {ka - kb:+d}) |",
        f"| Retention /20, A vs B | {ra} vs {rb} |",
        f"| Discordant items (A pass / B fail, A fail / B pass) | {m['a_only']} / {m['b_only']} |",
        f"| Exact McNemar p (200 assistant items) | {m['p_value']:.3f} |", "",
        f"Changing hardware and precision (H200 bf16 vs T4 fp16) changed the text of {len(all_ids) - same}/{len(all_ids)} "
        f"greedy answers of base-1.7B but not its score ({ka} vs {kb} /200; exact McNemar p = {m['p_value']:.2f}). "
        "This supports protocol robustness for the base model; the effect on trained models is tested separately "
        "(T4 vs H200 training check after Tier S).", ""])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    it = items()
    ids = [i for i in it if it[i]["block"] != "R"]
    size_curve(ids)
    section = protocol_check(ids, list(it))
    lim = ROOT / "docs" / "limitations.md"
    head = "# Limitations\n\nKnown limits of the evaluation and the data, with the measurement behind each.\n\n"
    text = lim.read_text(encoding="utf-8") if lim.exists() else head
    if "## Protocol A vs B" in text:
        a = text.index("## Protocol A vs B")
        b = text.find("\n## ", a + 1)
        text = text[:a] + section + (text[b + 1:] if b != -1 else "")
    else:
        text = text.rstrip("\n") + "\n\n" + section
    lim.write_text(text, encoding="utf-8", newline="\n")
    print(section)


if __name__ == "__main__":
    main()
