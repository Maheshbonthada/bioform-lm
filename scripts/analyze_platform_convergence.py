#!/usr/bin/env python3
"""
What marketed antibody formulations actually look like, and what that implies for
conditional generative design.

Motivation. The protein-conditional claim was tested twice on this data and
failed both times: sequence-derived Fv pI correlates with chosen pH at rho=-0.464
(p=0.015) on the 27 molecules whose full composition parses, but that vanishes at
n=80 (rho=-0.019, p=0.86) and is absent even in the 44-molecule high-confidence
stratum where pH is stated inside the composition sentence (rho=-0.123, p=0.43).
It also fails leave-one-protein-out prediction. The n=27 result was a selection
artifact.

That negative result raises the question this script answers: if the protein does
not explain the formulation, what does? The answer is that approved antibody
formulations are largely a PLATFORM -- a narrow, conventional recipe reused across
molecules -- and the practical consequence is that any conditional model must be
benchmarked against a constant platform prediction, which is a much stronger
baseline than the uniform or random baselines usually reported.

Analyses:
  1. Concentration of the marketed design space (entropy, top-1 share).
  2. The platform baseline: accuracy of always predicting the single most common
     value, per slot -- the number a conditional model has to beat.
  3. Variance decomposition: between-molecule vs within-molecule (across a
     molecule's own presentations) variance in pH.
  4. Whether ANY available covariate -- sequence, route, isotype, format,
     concentration -- explains the residual, via LOPO ridge against the platform.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

RNG = np.random.default_rng(0)
N_PERM = 100_000


def per_molecule(m):
    num = [c for c in m.columns if pd.api.types.is_numeric_dtype(m[c])]
    g = m.groupby("inn")
    out = g[num].median()
    for c in ("buffer_species", "surfactant", "route", "isotype", "format"):
        if c in m:
            out[c] = g[c].agg(lambda s: s.dropna().mode().iloc[0]
                              if s.dropna().size else None)
    out["n_presentations"] = g.size()
    return out.reset_index()


def entropy(counts):
    p = np.asarray(counts, float)
    p = p[p > 0] / p.sum()
    return float(-(p * np.log2(p)).sum())


def ridge_lopo(X, y, lam):
    n = len(y)
    pred = np.empty(n)
    for i in range(n):
        tr = np.ones(n, bool); tr[i] = False
        Xt, yt = X[tr], y[tr]
        mu, sd = Xt.mean(0), Xt.std(0); sd[sd == 0] = 1.0
        Z = np.column_stack([np.ones(tr.sum()), (Xt - mu) / sd])
        A = Z.T @ Z + lam * np.eye(Z.shape[1]); A[0, 0] -= lam
        w = np.linalg.solve(A, Z.T @ yt)
        pred[i] = np.concatenate([[1.0], (X[i] - mu) / sd]) @ w
    return pred


def main():
    f = pd.read_csv("data/raw_labels/parsed_formulations.csv")
    f = f[f.ph.between(4.0, 9.0)].copy()
    d = pd.read_csv("data/protein_descriptors_seq.csv")
    m = f.merge(d, on="inn", how="inner")
    pm = per_molecule(m)
    out = {"n_rows": int(len(m)), "n_molecules": int(len(pm))}
    print(f"{len(m)} marketed formulations, {len(pm)} distinct approved antibodies\n")

    # ---------- 1. how concentrated is the marketed design space? ----------
    print("=== concentration of the marketed design space ===")
    conc = {}
    for slot in ("buffer_species", "surfactant", "route"):
        s = pm[slot].dropna()
        if len(s) < 5:
            continue
        vc = s.value_counts()
        conc[slot] = {"n": int(len(s)), "top": str(vc.index[0]),
                      "top_share": float(vc.iloc[0] / len(s)),
                      "n_distinct": int(len(vc)),
                      "entropy_bits": entropy(vc.values),
                      "max_entropy_bits": float(np.log2(len(vc)))}
        print(f"  {slot:16s} n={len(s):3d}  top='{vc.index[0]}' "
              f"{vc.iloc[0] / len(s):.0%}  distinct={len(vc)}  "
              f"H={entropy(vc.values):.2f}/{np.log2(len(vc)):.2f} bits")
    ph = pm.ph.dropna()
    conc["ph"] = {"n": int(len(ph)), "mean": float(ph.mean()), "sd": float(ph.std()),
                  "iqr": [float(ph.quantile(.25)), float(ph.quantile(.75))],
                  "frac_within_half_unit_of_median": float(
                      (ph.sub(ph.median()).abs() <= 0.5).mean())}
    print(f"  {'ph':16s} n={len(ph):3d}  mean {ph.mean():.2f}  sd {ph.std():.2f}  "
          f"{conc['ph']['frac_within_half_unit_of_median']:.0%} within +/-0.5 of median")
    out["design_space_concentration"] = conc

    # ---------- 2. the platform baseline ----------
    print("\n=== platform baseline: always predict the single most common value ===")
    plat = {}
    for slot in ("buffer_species", "surfactant"):
        s = pm[slot].dropna()
        if len(s) < 5:
            continue
        vc = s.value_counts()
        plat[slot] = {"prediction": str(vc.index[0]),
                      "accuracy": float(vc.iloc[0] / len(s)), "n": int(len(s))}
        print(f"  {slot:16s} predict '{vc.index[0]}' -> accuracy "
              f"{vc.iloc[0] / len(s):.1%}  (n={len(s)})")
    med = float(ph.median())
    plat["ph"] = {"prediction": med, "mae": float((ph - med).abs().mean()),
                  "rmse": float(np.sqrt(((ph - med) ** 2).mean())), "n": int(len(ph))}
    print(f"  {'ph':16s} predict {med:.2f}       -> MAE {plat['ph']['mae']:.3f} pH units")
    out["platform_baseline"] = plat

    # ---------- 3. variance decomposition ----------
    print("\n=== variance in pH: between molecules vs within a molecule ===")
    g = m.groupby("inn").ph
    within = g.std().dropna()
    between = g.median()
    vd = {"between_molecule_sd": float(between.std()),
          "mean_within_molecule_sd": float(within.mean()) if len(within) else None,
          "n_molecules_multi_presentation": int((g.size() > 1).sum())}
    vd["ratio"] = (vd["between_molecule_sd"] / vd["mean_within_molecule_sd"]
                   if vd["mean_within_molecule_sd"] else None)
    out["variance_decomposition"] = vd
    print(f"  between-molecule sd {vd['between_molecule_sd']:.3f}")
    print(f"  within-molecule  sd {vd['mean_within_molecule_sd']}"
          f"  (over {vd['n_molecules_multi_presentation']} multi-presentation molecules)")

    # ---------- 4. does ANY covariate beat the platform? ----------
    print("\n=== can any covariate beat the platform baseline on pH? (LOPO) ===")
    pmm = pm.dropna(subset=["ph", "fv_pi"]).reset_index(drop=True)
    y = pmm.ph.values
    n = len(y)
    blocks = {
        "sequence": ["fv_pi", "fv_charge_ph6", "fv_gravy", "fv_mw_kda"],
        "sequence+context": ["fv_pi", "fv_charge_ph6", "fv_gravy", "fv_mw_kda"],
    }
    if "route" in pmm:
        pmm["_sc"] = (pmm.route.astype(str) == "subcutaneous").astype(float)
        blocks["sequence+context"] = blocks["sequence"] + ["_sc"]
    if "protein_conc_mg_ml" in pmm:
        pmm["_conc"] = pmm.protein_conc_mg_ml.fillna(pmm.protein_conc_mg_ml.median()
                                                     if pmm.protein_conc_mg_ml.notna().any() else 0)
        blocks["sequence+context"] = blocks["sequence+context"] + ["_conc"]

    base_pred = np.array([np.median(np.delete(y, i)) for i in range(n)])
    base_err = np.abs(base_pred - y)
    res = {"n": int(n), "platform_lopo_mae": float(base_err.mean()), "models": {}}
    print(f"  platform (LOPO median)  MAE {base_err.mean():.4f}   n={n}")

    for name, feats in blocks.items():
        feats = [c for c in feats if c in pmm]
        X = pmm[feats].values.astype(float)
        best = None
        for lam in (1.0, 3.0, 10.0, 30.0, 100.0):
            e = np.abs(ridge_lopo(X, y, lam) - y)
            if best is None or e.mean() < best[1].mean():
                best = (lam, e)
        lam, err = best
        dd = base_err - err
        signs = RNG.choice([-1.0, 1.0], size=(N_PERM, n))
        p = (np.sum((signs * dd).mean(axis=1) >= dd.mean() - 1e-12) + 1) / (N_PERM + 1)
        res["models"][name] = {"features": feats, "best_lambda": lam,
                               "mae": float(err.mean()),
                               "improvement_vs_platform": float(dd.mean()),
                               "n_better": int((dd > 0).sum()),
                               "sign_flip_p": float(p)}
        print(f"  {name:18s}    MAE {err.mean():.4f}  "
              f"delta {dd.mean():+.4f}  better {int((dd > 0).sum())}/{n}  p={p:.4f}")
    out["beat_platform"] = res

    Path("results").mkdir(exist_ok=True)
    Path("results/platform_convergence.json").write_text(json.dumps(out, indent=2))
    print("\nwrote results/platform_convergence.json")


if __name__ == "__main__":
    main()
