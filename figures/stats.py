"""Statistics for the figures: Wilson CI, exact McNemar, paired bootstrap of Δ /200, Holm adjustment.

Paired bootstrap: arms A and B are paired seed by seed (a single-seed arm such as a base model is paired with every
seed of the other arm). Within each seed stratum the item indices are resampled with replacement, the same indices
for A and B; Δ = mean over seeds of (passes A − passes B). 10,000 resamples, numpy seed 20261029. The CI is the
2.5 / 97.5 percentile interval; p is the two-sided share of resampled Δ on the other side of 0 (doubled, capped at 1).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import beta, binomtest, norm

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


def cluster_bootstrap(seed_rows: list, n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    """Rate and 95 % CI with the attack (item) as the unit: seed_rows = one 0/1 vector per seed, items in the same
    order. Per item, the mean over seeds; rate = mean over items; the CI resamples items (clusters) with replacement."""
    per_item = np.asarray(seed_rows, float).mean(axis=0)
    rng = np.random.default_rng(seed)
    n = len(per_item)
    boot = per_item[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"rate": float(per_item.mean()), "ci_lo": float(lo), "ci_hi": float(hi), "n_items": n,
            "seeds": len(seed_rows), "n_boot": n_boot}


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Clopper–Pearson) two-sided interval for k successes out of n."""
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return lo, hi


def bca_cluster_bootstrap(seed_rows: list, n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    """Cluster bootstrap over items with a BCa interval. Per item the mean over seeds; statistic = mean over items.
    Bias correction z0 counts resamples equal to the estimate as half below; acceleration from the item jackknife."""
    per_item = np.asarray(seed_rows, float).mean(axis=0)
    n, theta = len(per_item), float(per_item.mean())
    rng = np.random.default_rng(seed)
    boot = per_item[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    if boot.min() == boot.max():
        return {"rate": theta, "ci_lo": theta, "ci_hi": theta}
    prop = (boot < theta).mean() + 0.5 * (boot == theta).mean()
    z0 = norm.ppf(min(max(prop, 1 / n_boot), 1 - 1 / n_boot))
    jack = (per_item.sum() - per_item) / (n - 1)
    d = jack.mean() - jack
    a = float((d ** 3).sum() / (6 * ((d ** 2).sum()) ** 1.5)) if (d ** 2).sum() > 0 else 0.0
    q = []
    for z in (norm.ppf(0.025), norm.ppf(0.975)):
        q.append(100 * norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z))))
    lo, hi = np.percentile(boot, q)
    return {"rate": theta, "ci_lo": float(lo), "ci_hi": float(hi)}


def redteam_interval(seed_rows: list) -> dict:
    """Red-team rate and 95 % interval with the attack as the unit. One seed: Clopper–Pearson on k / n attacks.
    Several seeds: BCa cluster bootstrap over attacks; if at most 2 attacks succeed in any seed, also Clopper–Pearson
    on 'attacks succeeded in >= 1 seed' as a conservative interval."""
    rows = np.asarray(seed_rows, int)
    n = rows.shape[1]
    if rows.shape[0] == 1:
        k = int(rows.sum())
        lo, hi = clopper_pearson(k, n)
        return {"rate": k / n, "ci_lo": lo, "ci_hi": hi, "method": "CP", "seeds": 1}
    out = bca_cluster_bootstrap(rows)
    out.update(method="BCa", seeds=int(rows.shape[0]))
    any_k = int((rows.max(axis=0) > 0).sum())
    if any_k <= 2:
        out["cons_k"] = any_k
        out["cons_lo"], out["cons_hi"] = clopper_pearson(any_k, n)
    return out


def fmt_rt(b: dict, k: int, N: int) -> str:
    """'x % [lo, hi] (k/N; method)' for the red-team tables; CP bounds below 1 % keep two decimals."""
    f = lambda v: f"{100 * v:.2f}" if 0 < 100 * v < 1 else f"{100 * v:.1f}"
    s = f"{100 * b['rate']:.1f} % [{f(b['ci_lo'])}, {f(b['ci_hi'])}] ({k}/{N}; {b['method']}"
    if "cons_k" in b:
        s += f"; ≥ 1 seed: {b['cons_k']}/60 CP [{f(b['cons_lo'])}, {f(b['cons_hi'])}]"
    return s + ")"
