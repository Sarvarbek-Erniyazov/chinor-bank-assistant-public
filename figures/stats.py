"""Statistics for the figures: Wilson CI, exact McNemar, paired bootstrap of Δ /200, Holm adjustment.

Paired bootstrap: arms A and B are paired seed by seed (a single-seed arm such as a base model is paired with every
seed of the other arm). Within each seed stratum the item indices are resampled with replacement, the same indices
for A and B; Δ = mean over seeds of (passes A − passes B). 10,000 resamples, numpy seed 20261029. The CI is the
2.5 / 97.5 percentile interval; p is the two-sided share of resampled Δ on the other side of 0 (doubled, capped at 1).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import binomtest

BOOT_SEED = 20261029
BOOT_N = 10_000


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(a, b) -> dict:
    """Exact (binomial) McNemar on paired pass/fail vectors; a_only = A pass & B fail."""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    a_only, b_only = int((a & ~b).sum()), int((~a & b).sum())
    n = a_only + b_only
    p = 1.0 if n == 0 else binomtest(min(a_only, b_only), n, 0.5).pvalue
    return {"a_only": a_only, "b_only": b_only, "discordant": n, "p_value": float(p)}


def paired_bootstrap(a_seeds: list, b_seeds: list, n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    """Δ = A − B in passes over the items given (e.g. the 200 assistant items), stratified by seed."""
    a = [np.asarray(x, float) for x in a_seeds]
    b = [np.asarray(x, float) for x in b_seeds]
    if len(a) == 1 and len(b) > 1:
        a = a * len(b)
    if len(b) == 1 and len(a) > 1:
        b = b * len(a)
    if len(a) != len(b):
        raise ValueError("seed counts differ and neither arm has a single seed")
    rng = np.random.default_rng(seed)
    n = len(a[0])
    boot = np.zeros(n_boot)
    for x, y in zip(a, b):
        d = x - y
        boot += d[rng.integers(0, n, size=(n_boot, n))].sum(axis=1)
    boot /= len(a)
    delta = float(np.mean([(x - y).sum() for x, y in zip(a, b)]))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    p = min(1.0, 2 * min((boot <= 0).mean(), (boot >= 0).mean()))
    return {"delta": delta, "ci_lo": float(lo), "ci_hi": float(hi), "p_value": float(p), "n_boot": n_boot, "seeds": len(a)}


def holm(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, returned in input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj
