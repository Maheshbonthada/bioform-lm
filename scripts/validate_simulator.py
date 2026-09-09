#!/usr/bin/env python3
"""
Held-out validation of simulator v1 vs v2 against BioFormBench.

This is the test that decides whether v2's added pathways are real physics or
just extra knobs. None of v2's constants was fit to this benchmark, so agreement
here is genuine out-of-sample evidence.

Two protocols:
  global  -- Spearman(simulator score, measured stability) over all rows. Inflated
             by between-protein variance, so reported only for completeness.
  within  -- Spearman computed inside each protein and then aggregated. This is
             the protocol that matters: it asks whether the simulator ranks
             *formulations of the same protein* correctly, which is the actual
             design task and cannot be won by memorising protein-level offsets.

Significance uses an exact paired sign-flip permutation test over proteins.
"""
import json, sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simulator.mechanistic_sim import (BiologicsFormulationSimulator,
                                       FormulationComposition, ProteinDescriptor)
from simulator.mechanistic_sim_v2 import AggregationSimulatorV2

BENCH = "data/bioformbench_v2.csv"


def row_to_pair(r):
    p = ProteinDescriptor(mw_kda=float(r.protein_mw_kda), pi=float(r.protein_pi),
                          hydrophobicity=0.5,
                          tm_baseline_c=float(r.protein_tm_baseline_c))
    stab = json.loads(r.stabilizers_json) if isinstance(r.stabilizers_json, str) else {}
    # Benchmark records sugar in mM; the simulator expects % w/v.
    stab = {k: (v / 29.2 if v > 5 else v) for k, v in stab.items()}
    f = FormulationComposition(
        buffer_species=str(r.buffer_species).lower(),
        buffer_conc_mm=float(np.clip(r.buffer_conc_mm, 1, 500)),
        ph=float(np.clip(r.ph, 3.0, 10.0)),
        ionic_strength_mm=max(float(r.ionic_strength_mm), 1.0),
        # Clamp to the simulator's validated envelope; 4/67 benchmark rows
        # are hypertonic beyond it and would otherwise be dropped entirely.
        osmolarity_mosm_kg=float(np.clip(r.osmolarity_mosm_kg, 50, 500)),
        stabilizers=stab,
        temperature_c=float(np.clip(r.temperature_c, 4, 37)),
        storage_duration_days=30.0,
    )
    return p, f


def main():
    df = pd.read_csv(BENCH)
    df["protein_key"] = (df.protein_mw_kda.round(2).astype(str) + "_"
                         + df.protein_pi.round(2).astype(str))
    sims = {"v1": BiologicsFormulationSimulator(), "v2": AggregationSimulatorV2()}

    for tag, sim in sims.items():
        preds = []
        for r in df.itertuples():
            p, f = row_to_pair(r)
            preds.append(sim.predict(p, f).stability_score)
        df[f"pred_{tag}"] = preds

    out = {"n_rows": len(df), "n_proteins": df.protein_key.nunique()}

    # ---- global ----
    for tag in sims:
        rho, pv = spearmanr(df[f"pred_{tag}"], df.stability_score)
        out.setdefault("global", {})[tag] = {"spearman": float(rho), "p": float(pv)}

    # ---- within-protein ----
    per = {}
    for key, g in df.groupby("protein_key"):
        if len(g) < 4 or g.stability_score.nunique() < 3:
            continue
        e = {}
        for tag in sims:
            if g[f"pred_{tag}"].nunique() < 2:
                e[tag] = 0.0
            else:
                rho, _ = spearmanr(g[f"pred_{tag}"], g.stability_score)
                e[tag] = 0.0 if np.isnan(rho) else float(rho)
        e["n"] = int(len(g))
        per[key] = e
    out["within_protein"] = {"per_protein": per, "n_proteins_eligible": len(per)}

    v1 = np.array([v["v1"] for v in per.values()])
    v2 = np.array([v["v2"] for v in per.values()])
    d = v2 - v1
    out["within_protein"]["mean_v1"] = float(v1.mean())
    out["within_protein"]["mean_v2"] = float(v2.mean())
    out["within_protein"]["mean_improvement"] = float(d.mean())
    out["within_protein"]["n_improved"] = int((d > 0).sum())
    out["within_protein"]["n_worsened"] = int((d < 0).sum())

    # exact paired sign-flip permutation test
    n = len(d)
    obs = d.mean()
    count = sum(1 for signs in product([1, -1], repeat=n)
                if (np.array(signs) * d).mean() >= obs - 1e-12)
    out["within_protein"]["exact_sign_flip_p"] = count / (2 ** n)
    out["within_protein"]["n_permutations"] = 2 ** n

    print(json.dumps({k: v for k, v in out.items() if k != "within_protein"}, indent=2))
    w = out["within_protein"]
    print(f"\nwithin-protein Spearman  v1 {w['mean_v1']:+.3f}  ->  v2 {w['mean_v2']:+.3f}"
          f"   (delta {w['mean_improvement']:+.3f})")
    print(f"improved {w['n_improved']}/{w['n_proteins_eligible']}   "
          f"worsened {w['n_worsened']}   exact p = {w['exact_sign_flip_p']:.4f}")
    Path("results/simulator_validation.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
