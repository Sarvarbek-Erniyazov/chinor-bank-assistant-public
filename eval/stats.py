"""Statistics for eval scores: Wilson 95 % CI, exact paired McNemar, bootstrap CI.

Usage:
  python eval/stats.py --arm A                 # per-block pass rates with Wilson CI
  python eval/stats.py --arm A --compare B     # adds exact McNemar A vs B per block and aggregate

Aggregates: "assistant" = T-seen + T-held + B1-B4 (200 items, system prompt);
"retention" = R (20 items, no system prompt). The two are never summed.
"""
from __future__ import annotations

import argparse
import json
import sys
import math
import random
from pathlib import Path

from scipy.stats import binomtest, norm

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = ["T-seen", "T-held", "B1", "B2", "B3", "B4", "R"]
AGGREGATES = {
    "assistant": ["T-seen", "T-held", "B1", "B2", "B3", "B4"],
    "retention": ["R"],
}


def in_group(blk: str, item_block: str) -> bool:
    return item_block in AGGREGATES.get(blk, [blk])


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(a: list[bool], b: list[bool]) -> dict:
    """Exact (binomial) McNemar test on paired pass/fail vectors."""
    assert len(a) == len(b)
    b01 = sum(1 for x, y in zip(a, b) if not x and y)   # A fail, B pass
    b10 = sum(1 for x, y in zip(a, b) if x and not y)   # A pass, B fail
    n = b01 + b10
    p = 1.0 if n == 0 else binomtest(min(b01, b10), n, 0.5, alternative="two-sided").pvalue
    return {"a_only": b10, "b_only": b01, "discordant": n, "p_value": p}


def bootstrap_ci(passes: list[bool], iters: int = 10000, seed: int = 20261027) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(passes)
    if n == 0:
        return float("nan"), float("nan")
    vals = sorted(sum(rng.choices(passes, k=n)) / n for _ in range(iters))
    return vals[int(0.025 * iters)], vals[int(0.975 * iters) - 1]


def load_scores(arm: str) -> dict[str, dict]:
    p = ROOT / "eval" / "outputs" / arm / "scores.jsonl"
    return {r["id"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def load_blocks() -> dict[str, str]:
    p = ROOT / "eval" / "eval_set.jsonl"
    return {r["id"]: r["block"] for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def summarise(arm: str) -> dict:
    scores, blocks = load_scores(arm), load_blocks()
    out = {}
    for blk in BLOCKS + list(AGGREGATES):
        ids = [i for i in scores if in_group(blk, blocks[i])]
        passes = [scores[i]["pass"] for i in ids]
        k, n = sum(passes), len(passes)
        p, lo, hi = wilson(k, n)
        entry = {"k": k, "n": n, "rate": p, "wilson_lo": lo, "wilson_hi": hi}
        if blk in AGGREGATES:
            entry["boot_lo"], entry["boot_hi"] = bootstrap_ci(passes)
        for f in ("hard_violation", "over_refusal", "injection_success", "fabricated_number"):
            entry[f] = sum(scores[i]["flags"].get(f, False) for i in ids)
        out[blk] = entry
    return out


def compare(arm_a: str, arm_b: str) -> dict:
    sa, sb, blocks = load_scores(arm_a), load_scores(arm_b), load_blocks()
    ids = sorted(set(sa) & set(sb))
    out = {}
    for blk in BLOCKS + list(AGGREGATES):
        sel = [i for i in ids if in_group(blk, blocks[i])]
        out[blk] = mcnemar_exact([sa[i]["pass"] for i in sel], [sb[i]["pass"] for i in sel])
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--compare", default=None)
    args = ap.parse_args()
    s = summarise(args.arm)
    for blk, e in s.items():
        extra = f" boot[{e['boot_lo']:.3f},{e['boot_hi']:.3f}]" if "boot_lo" in e else ""
        print(f"{blk:>9}: {e['k']:>3}/{e['n']:<3} {e['rate']:.3f} [{e['wilson_lo']:.3f},{e['wilson_hi']:.3f}]{extra} "
              f"HV={e['hard_violation']} OR={e['over_refusal']} INJ={e['injection_success']} NUM={e['fabricated_number']}")
    if args.compare:
        print(f"\nMcNemar exact {args.arm} vs {args.compare}")
        for blk, c in compare(args.arm, args.compare).items():
            print(f"{blk:>9}: A-only={c['a_only']} B-only={c['b_only']} p={c['p_value']:.4f}")


if __name__ == "__main__":
    main()
