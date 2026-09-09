#!/usr/bin/env python3
"""
Formally combine the two independently-trained checkpoints' specificity evidence.

Section on the identity-fix result reported the conditional checkpoint's effect
as significant (p=0.016-0.023) and the ICL checkpoint's as only marginal
(p=0.078-0.211) when tested alone, noting they agree in direction (rank
correlation) without a formal combined test. Two independent p-values testing
the same directional hypothesis (protein specificity > chance) should be
combined properly rather than left as two separate numbers for the reader to
eyeball -- Stouffer's method (sum of inverse-normal-transformed one-sided
p-values) is the standard tool for exactly this, given as a pre-specified
combination, not chosen after seeing which combination looks best.
"""
import json
from itertools import product
from pathlib import Path

import numpy as np
from scipy.stats import norm


def per_protein_spec(f):
    return {k: v["protein_specificity"] for k, v in json.load(open(f))["per_protein"].items()}


def one_sided_exact_p(vals):
    """Exact one-sided sign-flip p-value for mean(vals) > 0.5."""
    x = np.array(list(vals.values())) - 0.5
    n = len(x)
    obs = x.mean()
    cnt = sum(1 for s in product([1, -1], repeat=n) if (np.array(s) * x).mean() >= obs - 1e-12)
    return cnt / 2 ** n, obs + 0.5, n


def stouffer(p_values, weights=None):
    """Stouffer's Z-score method for combining independent one-sided p-values."""
    p = np.clip(np.array(p_values), 1e-12, 1 - 1e-12)
    z = norm.isf(p)  # inverse survival function: large z for small p
    w = np.ones(len(p)) if weights is None else np.array(weights)
    Z = (w * z).sum() / np.sqrt((w ** 2).sum())
    return float(Z), float(norm.sf(Z))


def main():
    cond = per_protein_spec("results/lopo_v4_checkpoints_conditional_shots1.json")
    icl = per_protein_spec("results/lopo_v4_checkpoints_icl_shots1.json")

    out = {}
    for label, keep in (("n=8_all", None), ("n=7_excl_mAb2", "mAb2")):
        c = {k: v for k, v in cond.items() if k != keep} if keep else cond
        i = {k: v for k, v in icl.items() if k != keep} if keep else icl
        p_c, m_c, n_c = one_sided_exact_p(c)
        p_i, m_i, n_i = one_sided_exact_p(i)
        Z, p_combined = stouffer([p_c, p_i], weights=[np.sqrt(n_c), np.sqrt(n_i)])
        out[label] = {
            "conditional": {"p_one_sided": p_c, "mean": m_c, "n": n_c},
            "icl": {"p_one_sided": p_i, "mean": m_i, "n": n_i},
            "stouffer_combined": {"Z": Z, "p_one_sided": p_combined},
        }
        print(f"=== {label} ===")
        print(f"  conditional: mean={m_c:.3f} n={n_c} p(one-sided)={p_c:.4f}")
        print(f"  icl:         mean={m_i:.3f} n={n_i} p(one-sided)={p_i:.4f}")
        print(f"  Stouffer combined (sample-size weighted): Z={Z:.3f} "
              f"p(one-sided)={p_combined:.5f}")
        print()

    Path("results/specificity_combined_stouffer.json").write_text(json.dumps(out, indent=2))
    print("wrote results/specificity_combined_stouffer.json")


if __name__ == "__main__":
    main()
