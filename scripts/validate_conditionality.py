#!/usr/bin/env python3
"""
Rigorous validation of the sequence-conditionality result.

The headline correlation (Fv pI vs chosen formulation pH, rho = -0.464, p = 0.015,
n = 27 molecules) is the paper's central positive claim, so it is stress-tested
here rather than reported on its own:

  1. Permutation test        -- no normality or monotone-linearity assumption.
  2. Holm-Bonferroni         -- nine sequence features were screened; the family-
                                wise error rate has to be controlled.
  3. Bootstrap CI            -- how precise is the estimate at n = 27?
  4. Confound control        -- route (SC vs IV) and isotype both plausibly drive
                                pH; partial correlation removes them.
  5. Leave-one-protein-out   -- the decisive test. Correlation is description;
                                design requires predicting the pH for a molecule
                                the model has never seen. Compared against the
                                global-mean baseline with a paired permutation
                                test over held-out proteins.
  6. Influence check         -- does dropping any single molecule overturn it?

Direction matters as much as significance: colloidal theory says formulate away
from the pI, so a basic antibody should be formulated at LOWER pH. A negative rho
is therefore the physically predicted sign, not a free parameter.
"""
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

RNG = np.random.default_rng(0)
N_PERM = 200_000
SEQ_FEATURES = ["fv_pi", "fv_charge_ph6", "fv_charge_ph5", "fv_gravy",
                "fv_hydrophobic_frac", "fv_aromaticity", "fv_mw_kda",
                "fv_net_charge_density", "fv_instability"]


def perm_p(x, y, n=N_PERM):
    """Two-sided permutation p-value for Spearman rho."""
    obs = spearmanr(x, y).statistic
    y = np.asarray(y)
    cnt = 0
    for _ in range(n):
        if abs(spearmanr(x, RNG.permutation(y)).statistic) >= abs(obs) - 1e-12:
            cnt += 1
    return obs, (cnt + 1) / (n + 1)


def fast_perm_p(x, y, n=N_PERM):
    """Same test, vectorised: Spearman on ranks is Pearson on ranks."""
    rx = rankdata(x)
    ry = rankdata(y)
    rx = (rx - rx.mean()) / rx.std()
    ry = (ry - ry.mean()) / ry.std()
    obs = float(rx @ ry / len(rx))
    idx = np.argsort(RNG.random((n, len(ry))), axis=1)
    null = (ry[idx] @ rx) / len(rx)
    p = (np.sum(np.abs(null) >= abs(obs) - 1e-12) + 1) / (n + 1)
    return obs, float(p)


def partial_spearman(x, y, covars):
    """Spearman of residuals after regressing rank(x), rank(y) on covariates."""
    rx, ry = rankdata(x), rankdata(y)
    C = np.column_stack([np.ones(len(rx))] + covars)
    bx = np.linalg.lstsq(C, rx, rcond=None)[0]
    by = np.linalg.lstsq(C, ry, rcond=None)[0]
    return spearmanr(rx - C @ bx, ry - C @ by)


def ridge_lopo(X, y, lam=1.0):
    """Leave-one-out predictions from ridge regression on standardised features."""
    n = len(y)
    preds = np.empty(n)
    for i in range(n):
        tr = np.ones(n, bool)
        tr[i] = False
        Xt, yt = X[tr], y[tr]
        mu, sd = Xt.mean(0), Xt.std(0)
        sd[sd == 0] = 1.0
        Z = (Xt - mu) / sd
        Z = np.column_stack([np.ones(len(Z)), Z])
        A = Z.T @ Z + lam * np.eye(Z.shape[1])
        A[0, 0] -= lam                       # do not penalise the intercept
        w = np.linalg.solve(A, Z.T @ yt)
        z = np.concatenate([[1.0], (X[i] - mu) / sd])
        preds[i] = z @ w
    return preds


def main():
    pm = pd.read_csv("data/marketed_formulations_per_molecule.csv")
    pm = pm.dropna(subset=["ph", "fv_pi"]).reset_index(drop=True)
    n = len(pm)
    out = {"n_molecules": int(n)}
    print(f"n = {n} distinct approved antibodies\n")

    # ---- 1-3: permutation, Holm, bootstrap ----
    print("=== permutation tests + Holm-Bonferroni over 9 screened features ===")
    rows = []
    for f in SEQ_FEATURES:
        rho, p = fast_perm_p(pm[f].values, pm.ph.values)
        rows.append({"feature": f, "rho": rho, "p_perm": p})
    rows.sort(key=lambda r: r["p_perm"])
    m = len(rows)
    prev = 0.0
    for i, r in enumerate(rows):
        adj = min(1.0, max(prev, (m - i) * r["p_perm"]))
        prev = adj
        r["p_holm"] = adj
        star = "***" if adj < 0.001 else "**" if adj < 0.01 else "*" if adj < 0.05 else ""
        print(f"  {r['feature']:24s} rho {r['rho']:+.3f}  p {r['p_perm']:.5f}  "
              f"Holm {adj:.4f} {star}")
    out["screen"] = rows

    best = rows[0]
    x, y = pm[best["feature"]].values, pm.ph.values
    boot = []
    for _ in range(20000):
        idx = RNG.integers(0, n, n)
        if len(np.unique(idx)) < 4:
            continue
        r = spearmanr(x[idx], y[idx]).statistic
        if not np.isnan(r):
            boot.append(r)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    out["bootstrap_ci95"] = [float(lo), float(hi)]
    print(f"\n  bootstrap 95% CI for {best['feature']}: [{lo:+.3f}, {hi:+.3f}]  "
          f"(excludes 0: {bool(hi < 0 or lo > 0)})")

    # ---- 4: confounds ----
    print("\n=== partial correlation controlling for route and isotype ===")
    cov = []
    names = []
    if "route" in pm:
        cov.append((pm.route.astype(str) == "subcutaneous").astype(float).values)
        names.append("route=SC")
    if "isotype" in pm:
        for iso in sorted(set(pm.isotype.astype(str)))[:-1]:
            cov.append((pm.isotype.astype(str) == iso).astype(float).values)
            names.append(f"isotype={iso}")
    if cov:
        pr = partial_spearman(x, y, cov)
        out["partial"] = {"rho": float(pr.statistic), "p": float(pr.pvalue),
                          "covariates": names}
        print(f"  controlling for {names}")
        print(f"  partial rho {pr.statistic:+.3f}   p {pr.pvalue:.4f}")

    # ---- 5: leave-one-protein-out prediction ----
    print("\n=== leave-one-protein-out prediction of formulation pH ===")
    feats = ["fv_pi", "fv_charge_ph6", "fv_gravy", "fv_mw_kda", "fv_aromaticity"]
    X = pm[feats].values.astype(float)
    pred_seq = ridge_lopo(X, y)
    # baseline: the mean pH of the other proteins (no protein information at all)
    pred_base = np.array([np.delete(y, i).mean() for i in range(n)])
    err_seq = np.abs(pred_seq - y)
    err_base = np.abs(pred_base - y)
    d = err_base - err_seq                    # positive => sequence model better

    obs = d.mean()
    signs = RNG.choice([-1.0, 1.0], size=(N_PERM, n))
    null = (signs * d).mean(axis=1)
    p_lopo = (np.sum(null >= obs - 1e-12) + 1) / (N_PERM + 1)

    out["lopo"] = {
        "features": feats,
        "mae_sequence": float(err_seq.mean()),
        "mae_baseline": float(err_base.mean()),
        "improvement": float(obs),
        "n_better": int((d > 0).sum()), "n_worse": int((d < 0).sum()),
        "sign_flip_p": float(p_lopo),
        "spearman_pred_vs_true": float(spearmanr(pred_seq, y).statistic),
    }
    print(f"  MAE  sequence model {err_seq.mean():.4f}   baseline {err_base.mean():.4f}")
    print(f"  improvement {obs:+.4f} pH units   better on {int((d > 0).sum())}/{n} proteins")
    print(f"  paired sign-flip p = {p_lopo:.5f}")
    print(f"  Spearman(predicted, true) = {spearmanr(pred_seq, y).statistic:+.3f}")

    # ---- 6: influence ----
    drops = []
    for i in range(n):
        r = spearmanr(np.delete(x, i), np.delete(y, i)).statistic
        drops.append(float(r))
    out["jackknife"] = {"min_rho": min(drops), "max_rho": max(drops),
                        "all_same_sign": bool(all(r < 0 for r in drops))}
    print(f"\n=== jackknife: rho ranges [{min(drops):+.3f}, {max(drops):+.3f}] "
          f"over all single-molecule deletions; sign stable: "
          f"{all(r < 0 for r in drops)}")

    Path("results/conditionality_validation.json").write_text(json.dumps(out, indent=2))
    print("\nwrote results/conditionality_validation.json")


if __name__ == "__main__":
    main()
