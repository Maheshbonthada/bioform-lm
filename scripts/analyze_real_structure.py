#!/usr/bin/env python3
"""
Two questions that must be answered before any modelling claim can stand.

Q1  Does BioFormBench have the statistical power to discriminate between
    simulators at all? (Are v1/v2 within-protein correlations distinguishable
    from zero, or from each other?)

Q2  Is there protein-conditional structure in the REAL data? If the best
    formulation is the same regardless of protein, then protein-conditional
    design is not merely hard to learn -- it is not a well-posed task, and no
    model or simulator can fix that.
"""
import json, sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

df = pd.read_csv("data/bioformbench_v2.csv")
df["protein_key"] = (df.protein_mw_kda.round(2).astype(str) + "_"
                     + df.protein_pi.round(2).astype(str))
out = {}

# ---------- Q1: power ----------
val = json.loads(Path("results/simulator_validation.json").read_text())
per = val["within_protein"]["per_protein"]


def exact_one_sample(x):
    x = np.asarray(x, float)
    n = len(x)
    obs = x.mean()
    c = sum(1 for s in product([1, -1], repeat=n)
            if abs((np.array(s) * x).mean()) >= abs(obs) - 1e-12)
    return c / 2 ** n


for tag in ("v1", "v2"):
    v = np.array([per[k][tag] for k in per])
    out.setdefault("Q1_power", {})[tag] = {
        "n_proteins": len(v), "mean_rho": float(v.mean()),
        "sd": float(v.std(ddof=1)),
        "exact_two_sided_p_vs_zero": exact_one_sample(v),
        "per_protein": [round(float(z), 3) for z in v],
    }

# ---------- Q2: is the task well posed? ----------
# For each protein take its best-measured formulation; ask whether those best
# formulations differ across proteins more than formulations differ by chance.
best_rows, all_rows = [], []
for key, g in df.groupby("protein_key"):
    if len(g) < 3:
        continue
    b = g.loc[g.stability_score.idxmax()]
    best_rows.append({"key": key, "pi": b.protein_pi, "mw": b.protein_mw_kda,
                      "ph": b.ph, "ion": b.ionic_strength_mm,
                      "buf": str(b.buffer_species).lower(),
                      "bconc": b.buffer_conc_mm, "osm": b.osmolarity_mosm_kg})
    all_rows.append(g)
B = pd.DataFrame(best_rows)
out["Q2_task_wellposed"] = {"n_proteins_with_3plus": len(B)}

if len(B) >= 4:
    # (a) do the winning recipes differ at all?
    out["Q2_task_wellposed"]["best_recipe_spread"] = {
        "ph": {"min": float(B.ph.min()), "max": float(B.ph.max()),
               "sd": float(B.ph.std())},
        "ionic_strength": {"min": float(B.ion.min()), "max": float(B.ion.max()),
                           "sd": float(B.ion.std())},
        "n_distinct_buffers": int(B.buf.nunique()),
        "buffer_counts": B.buf.value_counts().to_dict(),
    }
    # (b) do protein descriptors PREDICT the winning recipe?
    for target in ("ph", "ion"):
        for feat in ("pi", "mw"):
            if B[target].nunique() > 2:
                rho, p = spearmanr(B[feat], B[target])
                out["Q2_task_wellposed"].setdefault("descriptor_predicts_optimum", {})[
                    f"{feat}->{target}"] = {"spearman": float(rho), "p": float(p)}

# (c) Within-protein variance vs between-protein variance of the pH that wins.
#     If a single global pH won for every protein, between-variance would be ~0.
grand = df.groupby("protein_key").apply(
    lambda g: g.loc[g.stability_score.idxmax()].ph if len(g) >= 3 else np.nan)
grand = grand.dropna()
within = df.groupby("protein_key").ph.std().dropna()
out["Q2_task_wellposed"]["variance_decomposition"] = {
    "between_protein_sd_of_winning_ph": float(grand.std()),
    "mean_within_protein_sd_of_screened_ph": float(within.mean()),
    "ratio": float(grand.std() / within.mean()) if within.mean() > 0 else None,
}

print(json.dumps(out, indent=2))
Path("results/real_structure_analysis.json").write_text(json.dumps(out, indent=2))
