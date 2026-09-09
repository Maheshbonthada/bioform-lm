#!/usr/bin/env python3
"""
The pivotal experiment: does a protein's SEQUENCE predict the formulation that
developers actually chose for it?

Every earlier protein-specificity result in this project was measured on
BioFormBench v2, whose protein descriptors were placeholders -- four different
antibodies were all recorded as 150.0 kDa / pI 7.2, and trastuzumab was listed at
pI 7.2 against a published cIEF value of 9.03. A conditional model cannot
distinguish molecules that the data represents identically, so a chance-level
specificity score there was guaranteed by construction and said nothing about
whether the task is learnable.

This script re-asks the question on data where the protein is real:

  * formulations  : FDA label DESCRIPTION sections for approved antibodies, parsed
                    deterministically (scripts/parse_labels.py). For an approved
                    product the formulation is the expert-optimised answer for
                    that specific protein, reviewed by a regulator.
  * descriptors   : computed from the VH/VL sequences in Thera-SAbDab
                    (scripts/compute_protein_descriptors.py). Within an isotype
                    the constant regions are identical, so the variable domains
                    are exactly what distinguishes one therapeutic from another.

Pseudo-replication guard: a molecule with twelve marketed presentations would
otherwise dominate. Every test is run on one row per molecule (median of its
presentations), so n is the number of distinct proteins, not the number of rows.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kruskal, spearmanr

PH_MIN, PH_MAX = 4.0, 9.0     # pharmaceutically valid range for a biologic
SEQ_FEATURES = ["fv_pi", "fv_charge_ph6", "fv_charge_ph5", "fv_gravy",
                "fv_hydrophobic_frac", "fv_aromaticity", "fv_mw_kda",
                "fv_net_charge_density", "fv_instability"]


def load():
    f = pd.read_csv("data/raw_labels/parsed_formulations.csv")
    # pH is the primary target and is stated on far more labels than a full
    # excipient breakdown is; requiring the whole composition would discard two
    # thirds of the molecules. Buffer-species tests below re-filter to the rows
    # that do have it.
    f = f[f.ph.between(PH_MIN, PH_MAX)].copy()
    d = pd.read_csv("data/protein_descriptors_seq.csv")
    m = f.merge(d, on="inn", how="inner")
    return m


def per_molecule(m):
    """One row per molecule: median of numeric fields, mode of categoricals."""
    num = [c for c in m.columns if pd.api.types.is_numeric_dtype(m[c])]
    g = m.groupby("inn")
    out = g[num].median()
    for c in ("buffer_species", "surfactant", "route", "isotype", "format"):
        if c in m:
            out[c] = g[c].agg(lambda s: s.dropna().mode().iloc[0]
                              if s.dropna().size else None)
    out["n_presentations"] = g.size()
    return out.reset_index()


def main():
    m = load()
    pm = per_molecule(m)
    res = {"n_rows": int(len(m)), "n_molecules": int(len(pm))}
    print(f"{len(m)} label formulations covering {len(pm)} distinct approved antibodies\n")

    # ---------- 1. continuous: does sequence predict the chosen pH? ----------
    print("=== sequence feature -> chosen formulation pH ===")
    corrs = {}
    for feat in SEQ_FEATURES:
        if feat not in pm or pm[feat].nunique() < 4:
            continue
        rho, p = spearmanr(pm[feat], pm.ph)
        corrs[feat] = {"spearman": float(rho), "p": float(p), "n": int(len(pm))}
        star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        print(f"  {feat:24s} rho {rho:+.3f}   p {p:.4f} {star}")
    res["ph_vs_sequence"] = corrs

    # ---------- 2. categorical: does sequence predict the buffer chosen? ----------
    print("\n=== sequence feature -> buffer species chosen ===")
    bres = {}
    vc = pm.buffer_species.value_counts()
    keep = vc[vc >= 3].index.tolist()
    sub = pm[pm.buffer_species.isin(keep)]
    print(f"  buffers with n>=3: {dict(vc[vc >= 3])}  (n={len(sub)} molecules)")
    for feat in SEQ_FEATURES:
        if feat not in sub:
            continue
        groups = [g[feat].dropna().values for _, g in sub.groupby("buffer_species")]
        groups = [g for g in groups if len(g) >= 3]
        if len(groups) < 2:
            continue
        try:
            H, p = kruskal(*groups)
        except ValueError:
            continue
        bres[feat] = {"kruskal_H": float(H), "p": float(p),
                      "group_medians": {k: float(np.median(g[feat]))
                                        for k, g in sub.groupby("buffer_species")}}
        star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        print(f"  {feat:24s} H {H:6.3f}  p {p:.4f} {star}")
    res["buffer_vs_sequence"] = bres

    # ---------- 3. the reference test: do the OLD 3 scalars do as well? ----------
    print("\n=== baseline: the descriptors BioFormBench v2 actually had ===")
    old = {}
    for feat in ("label_mw_kda",):
        if feat in pm and pm[feat].notna().sum() >= 8:
            s = pm.dropna(subset=[feat])
            rho, p = spearmanr(s[feat], s.ph)
            old[feat] = {"spearman": float(rho), "p": float(p), "n": int(len(s))}
            print(f"  {feat:24s} rho {rho:+.3f}   p {p:.4f}   n {len(s)}")
    res["ph_vs_label_mw"] = old

    # ---------- 4. spread: is there conditional structure to explain at all? ----------
    print("\n=== is the target even variable across molecules? ===")
    spread = {
        "ph": {"min": float(pm.ph.min()), "max": float(pm.ph.max()),
               "sd": float(pm.ph.std()), "n_distinct": int(pm.ph.nunique())},
        "buffer_species_counts": pm.buffer_species.value_counts().to_dict(),
        "n_distinct_buffers": int(pm.buffer_species.nunique()),
    }
    if "buffer_conc_mm" in pm:
        spread["buffer_conc_mm"] = {"min": float(pm.buffer_conc_mm.min()),
                                    "max": float(pm.buffer_conc_mm.max()),
                                    "sd": float(pm.buffer_conc_mm.std())}
    res["target_spread"] = spread
    print(f"  pH   {spread['ph']['min']:.1f} - {spread['ph']['max']:.1f}  "
          f"sd {spread['ph']['sd']:.2f}  ({spread['ph']['n_distinct']} distinct values)")
    print(f"  buffers chosen: {spread['buffer_species_counts']}")

    Path("results").mkdir(exist_ok=True)
    Path("results/sequence_conditionality.json").write_text(json.dumps(res, indent=2))
    pm.to_csv("data/marketed_formulations_per_molecule.csv", index=False)
    m.to_csv("data/marketed_formulations.csv", index=False)
    print("\nwrote results/sequence_conditionality.json, "
          "data/marketed_formulations{,_per_molecule}.csv")


if __name__ == "__main__":
    main()
