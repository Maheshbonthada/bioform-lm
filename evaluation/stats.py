"""
Exact statistics for very small samples.

`scipy.stats.spearmanr` returns an asymptotic p-value from a t-approximation.
At n = 4-6 that approximation is invalid, and for a perfect correlation the
t-statistic diverges, so it reports p = 0.0 -- which is what the original
manuscript printed. The exact two-sided p-value for a perfect Spearman
correlation is 2/n! (2/24 = 0.083 at n = 4; 2/720 = 0.0028 at n = 6), never zero.

These helpers enumerate or resample the permutation null instead.
"""

from itertools import permutations
from math import factorial
from typing import Sequence, Tuple

import numpy as np
from scipy.stats import spearmanr

EXACT_MAX_N = 8   # 8! = 40320 permutations; enumerate below this, sample above


def spearman_exact(x: Sequence[float], y: Sequence[float],
                   n_resamples: int = 20000, seed: int = 0) -> Tuple[float, float, str]:
    """Return (rho, exact-or-sampled two-sided p, method)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    n = len(x)
    if n < 3:
        return float("nan"), float("nan"), "undefined (n<3)"

    rho = spearmanr(x, y).correlation
    if not np.isfinite(rho):
        return float("nan"), float("nan"), "undefined (constant input)"

    if n <= EXACT_MAX_N:
        count = sum(
            1 for perm in permutations(range(n))
            if abs(spearmanr(x, y[list(perm)]).correlation) >= abs(rho) - 1e-12
        )
        return float(rho), count / factorial(n), f"exact permutation (n!={factorial(n)})"

    rng = np.random.default_rng(seed)
    hits = sum(
        1 for _ in range(n_resamples)
        if abs(spearmanr(x, rng.permutation(y)).correlation) >= abs(rho) - 1e-12
    )
    return float(rho), (hits + 1) / (n_resamples + 1), f"sampled permutation ({n_resamples})"


def bootstrap_ci(values: Sequence[float], n_boot: int = 10000,
                 alpha: float = 0.05, seed: int = 0) -> Tuple[float, float, float]:
    """Mean and percentile bootstrap CI. Honest for tiny fold counts, where a
    mean +/- SD interval can run outside the metric's own range."""
    v = np.asarray(values, float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boots = rng.choice(v, size=(n_boot, len(v)), replace=True).mean(axis=1)
    return float(v.mean()), float(np.percentile(boots, 100 * alpha / 2)), \
           float(np.percentile(boots, 100 * (1 - alpha / 2)))
