#!/usr/bin/env python3
"""
Diagnose why simulator-derived optima are protein-agnostic.

Two hypotheses, both testable without any model:

H1 (dead slots): buffer species and buffer concentration never enter predict(),
    so 2 of 8 recipe slots carry zero signal and are unlearnable by construction.

H2 (monotone objective): every remaining continuous term is monotone in its
    variable over the sampled box, so argmax collapses to a box CORNER. The only
    protein-dependent choice left is which pH corner (below vs above pI), giving
    ~2 distinct optima regardless of how many proteins are drawn.
"""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import synthetic_generator as sg

gen = sg.SyntheticDataGenerator(num_samples=1, seed=0)
sim, cfg = gen.simulator, gen.config
rng = np.random.default_rng(0)

def score(p, f):
    return sim.predict(p, f).stability_score

# ---- H1: are buffer slots dead? ----
p = gen._sample_protein()
base = gen._sample_formulation()
vals = []
for b in cfg.buffer_types:
    base.buffer_species = b
    vals.append(score(p, base))
buf_spread = max(vals) - min(vals)
cvals = []
for c in np.linspace(*cfg.buffer_concentration_range, 20):
    base.buffer_conc_mm = float(c)
    cvals.append(score(p, base))
conc_spread = max(cvals) - min(cvals)

# ---- H2: monotonicity of each continuous slot ----
def monotone_frac(setter, lo, hi, n_proteins=200, n_grid=25):
    """Fraction of proteins for which the slot's response is monotone."""
    grid = np.linspace(lo, hi, n_grid)
    mono, interior = 0, 0
    for _ in range(n_proteins):
        pr, fo = gen._sample_protein(), gen._sample_formulation()
        ys = []
        for g in grid:
            setter(fo, float(g))
            ys.append(score(pr, fo))
        ys = np.array(ys)
        d = np.diff(ys)
        if np.all(d >= -1e-12) or np.all(d <= 1e-12):
            mono += 1
        k = int(np.argmax(ys))
        if 0 < k < n_grid - 1:
            interior += 1
    return mono / n_proteins, interior / n_proteins

slots = {
    "ph":          (lambda f, v: setattr(f, "ph", v), *cfg.ph_range),
    "ionic_str":   (lambda f, v: setattr(f, "ionic_strength_mm", v), *cfg.ionic_strength_range),
    "osmolarity":  (lambda f, v: setattr(f, "osmolarity_mosm_kg", v), *cfg.osmolarity_range),
    "temperature": (lambda f, v: setattr(f, "temperature_c", v), *cfg.temperature_range),
}
mono_report = {}
for name, (setter, lo, hi) in slots.items():
    m, i = monotone_frac(setter, lo, hi)
    mono_report[name] = {"monotone_frac": m, "interior_argmax_frac": i}

# ---- H2b: how many DISTINCT optima across proteins? ----
def coarse(f):
    return (f.buffer_species, round(f.ph, 0), round(f.ionic_strength_mm, -2),
            round(f.osmolarity_mosm_kg, -2), round(f.temperature_c, 0),
            tuple(sorted(f.stabilizers)))

opts, pis = [], []
for _ in range(40):
    pr = gen._sample_protein()
    cands = [gen._sample_formulation() for _ in range(512)]
    ss = np.array([score(pr, c) for c in cands])
    best = cands[int(np.argmax(ss))]
    opts.append(coarse(best)); pis.append(pr.pi)
distinct = len(set(opts))

out = {
  "H1_dead_slots": {
    "buffer_species_stability_spread": buf_spread,
    "buffer_conc_stability_spread": conc_spread,
    "verdict": "DEAD - never read by predict()" if max(buf_spread, conc_spread) < 1e-12 else "live",
  },
  "H2_monotone_objective": mono_report,
  "H2b_distinct_optima": {"n_proteins": 40, "n_distinct": distinct,
                          "collapse_ratio": distinct / 40},
}
print(json.dumps(out, indent=2))
Path("results").mkdir(exist_ok=True)
Path("results/simulator_diagnosis_v1.json").write_text(json.dumps(out, indent=2))
