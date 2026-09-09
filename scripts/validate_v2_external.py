#!/usr/bin/env python3
"""
External, out-of-sample validation of simulator v2 against BioFormBench-Marketed.

v2's degradation-pathway constants (buffer pKa, deamidation/hydrolysis onsets,
Hofmeister onset, isotonicity target) were fixed from literature BEFORE this
dataset (165 marketed formulations for 80 FDA-approved antibodies, harvested in
scripts/harvest_labels.py / parse_labels.py) was assembled, and were never tuned
against it. This script asks a strict population-level question: does v2's
UNCONDITIONED optimum -- the pH/ionic-strength/osmolarity a formulator would pick
knowing nothing about which protein it is, since scripts/analyze_platform_convergence.py
already established that protein identity does not predict the marketed choice --
match the central tendency of what real formulators actually chose?

This is a fair test only because it is population-level: v2 is not being asked to
match any individual molecule's pH (nothing predicts that, protein-conditionally
or otherwise -- see results/platform_convergence.json), only the distribution.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import synthetic_generator as sg
from simulator.mechanistic_sim_v2 import AggregationSimulatorV2

gen = sg.SyntheticDataGenerator(num_samples=1, seed=7)
sim = AggregationSimulatorV2()

def score(p, f):
    return sim.predict(p, f).stability_score

# Population of v2-optimal recipes across 300 random proteins (matches the
# marketed data's mAb-scale MW range; v2 has already been shown protein-agnostic
# in its output distribution because it is dominated by the pathway terms that
# don't depend on protein identity when hydrophobicity is held near-typical).
rows = []
for _ in range(300):
    pr = gen._sample_protein()
    cands = [gen._sample_formulation() for _ in range(800)]
    ss = np.array([score(pr, c) for c in cands])
    b = cands[int(np.argmax(ss))]
    rows.append({"ph": b.ph, "ion": b.ionic_strength_mm,
                 "osm": b.osmolarity_mosm_kg, "buf": b.buffer_species})
sim_df = pd.DataFrame(rows)

real = pd.read_csv("data/raw_labels/parsed_formulations.csv")
real = real[real.ph.between(4.0, 9.0)]

out = {"n_simulated_optima": len(sim_df), "n_real_formulations": int(len(real))}

# ---- pH: KS test + mean/CI comparison ----
ks = stats.ks_2samp(sim_df.ph, real.ph.dropna())
out["ph"] = {
    "sim_mean": float(sim_df.ph.mean()), "sim_sd": float(sim_df.ph.std()),
    "real_mean": float(real.ph.mean()), "real_sd": float(real.ph.std()),
    "mean_abs_diff": float(abs(sim_df.ph.mean() - real.ph.mean())),
    "ks_statistic": float(ks.statistic), "ks_p": float(ks.pvalue),
}
# bootstrap CI on the mean difference
rng = np.random.default_rng(0)
diffs = []
sv, rv = sim_df.ph.values, real.ph.dropna().values
for _ in range(20000):
    a = rng.choice(sv, len(sv), replace=True).mean()
    b = rng.choice(rv, len(rv), replace=True).mean()
    diffs.append(a - b)
lo, hi = np.percentile(diffs, [2.5, 97.5])
out["ph"]["bootstrap_mean_diff_ci95"] = [float(lo), float(hi)]

# ---- naive-uniform-prior comparison: how much closer is v2 than "just guess
#      the middle of the allowed range" (pH box is 3.5-9.0, midpoint 6.25)? ----
uniform_guess = (3.5 + 9.0) / 2
out["ph"]["uniform_box_midpoint"] = uniform_guess
out["ph"]["uniform_abs_diff"] = float(abs(uniform_guess - real.ph.mean()))
out["ph"]["v2_improvement_over_uniform"] = float(
    abs(uniform_guess - real.ph.mean()) - abs(sim_df.ph.mean() - real.ph.mean()))

# also compare v1 (unconditioned, corner-seeking) the same way
v1 = gen.simulator
rows1 = []
for _ in range(300):
    pr = gen._sample_protein()
    cands = [gen._sample_formulation() for _ in range(800)]
    ss = np.array([v1.predict(pr, c).stability_score for c in cands])
    rows1.append({"ph": cands[int(np.argmax(ss))].ph})
v1_ph = pd.DataFrame(rows1).ph
out["ph"]["v1_mean"] = float(v1_ph.mean())
out["ph"]["v1_abs_diff"] = float(abs(v1_ph.mean() - real.ph.mean()))

# ---- ionic strength / buffer conc, where real data has it ----
if real.buffer_conc_mm.notna().sum() > 5:
    rc = real.buffer_conc_mm.dropna()
    out["ionic_strength_proxy"] = {
        "sim_ion_mean": float(sim_df.ion.mean()),
        "real_buffer_conc_mean": float(rc.mean()),
        "note": "not directly comparable (different quantities); reported for context only",
    }

# ---- buffer species: does v2's chosen buffer distribution overlap real usage? ----
sim_buf = sim_df.buf.value_counts(normalize=True)
real_buf = real.buffer_species.dropna()
real_buf = real_buf[~real_buf.str.contains(r"\+", na=False)]
real_buf = real_buf.value_counts(normalize=True)
common = set(sim_buf.index) & set(real_buf.index)
out["buffer_species"] = {
    "sim_top3": sim_buf.head(3).round(3).to_dict(),
    "real_top3": real_buf.head(3).round(3).to_dict(),
    "overlap_species": sorted(common),
}

print(json.dumps(out, indent=2))
Path("results/simulator_v2_external_validation.json").write_text(json.dumps(out, indent=2))
