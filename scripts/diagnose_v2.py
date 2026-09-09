"""Re-run the v1 diagnostic against simulator v2."""
import sys, json, statistics as st
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import synthetic_generator as sg
from simulator.mechanistic_sim_v2 import AggregationSimulatorV2

gen = sg.SyntheticDataGenerator(num_samples=1, seed=0)
cfg = gen.config
V = {"v1": gen.simulator, "v2": AggregationSimulatorV2()}
report = {}

for tag, sim in V.items():
    def score(p, f): return sim.predict(p, f).stability_score
    # dead slots
    p, base = gen._sample_protein(), gen._sample_formulation()
    vs = []
    for b in cfg.buffer_types:
        base.buffer_species = b; vs.append(score(p, base))
    buf = max(vs) - min(vs)
    cs = []
    for c in np.linspace(*cfg.buffer_concentration_range, 20):
        base.buffer_conc_mm = float(c); cs.append(score(p, base))
    conc = max(cs) - min(cs)
    # monotonicity / interior argmax
    slots = {"ph": (lambda f, v: setattr(f, "ph", v), *cfg.ph_range),
             "ionic_str": (lambda f, v: setattr(f, "ionic_strength_mm", v), *cfg.ionic_strength_range),
             "osmolarity": (lambda f, v: setattr(f, "osmolarity_mosm_kg", v), *cfg.osmolarity_range),
             "temperature": (lambda f, v: setattr(f, "temperature_c", v), *cfg.temperature_range)}
    mono = {}
    for name, (setter, lo, hi) in slots.items():
        grid = np.linspace(lo, hi, 25); m = i = 0
        for _ in range(200):
            pr, fo = gen._sample_protein(), gen._sample_formulation()
            ys = []
            for g in grid:
                setter(fo, float(g)); ys.append(score(pr, fo))
            ys = np.array(ys); d = np.diff(ys)
            if np.all(d >= -1e-12) or np.all(d <= 1e-12): m += 1
            k = int(np.argmax(ys))
            if 0 < k < 24: i += 1
        mono[name] = {"monotone_frac": m/200, "interior_argmax_frac": i/200}
    # optimum geometry
    rows = []
    for _ in range(60):
        pr = gen._sample_protein()
        cands = [gen._sample_formulation() for _ in range(2000)]
        ss = np.array([score(pr, c) for c in cands]); b2 = cands[int(np.argmax(ss))]
        rows.append({"pi": pr.pi, "hydro": pr.hydrophobicity, "ph": b2.ph,
                     "ion": b2.ionic_strength_mm, "osm": b2.osmolarity_mosm_kg,
                     "temp": b2.temperature_c, "buf": b2.buffer_species})
    box = {"ph": cfg.ph_range, "ion": cfg.ionic_strength_range,
           "osm": cfg.osmolarity_range, "temp": cfg.temperature_range}
    geo = {}
    for k, (lo, hi) in box.items():
        v = [r[k] for r in rows]
        geo[k] = {"opt_mean": st.mean(v), "opt_sd": st.pstdev(v),
                  "frac_of_box_spanned": (max(v)-min(v))/(hi-lo)}
    ph = np.array([r["ph"] for r in rows]); pi = np.array([r["pi"] for r in rows])
    ion = np.array([r["ion"] for r in rows]); hy = np.array([r["hydro"] for r in rows])
    geo["ph_vs_pi_corr"] = float(np.corrcoef(ph, pi)[0, 1])
    geo["ion_vs_hydrophobicity_corr"] = float(np.corrcoef(ion, hy)[0, 1])
    geo["ph_corner_frac"] = float(np.mean((ph < 3.8) | (ph > 8.7)))
    geo["n_distinct_buffers_chosen"] = len(set(r["buf"] for r in rows))
    report[tag] = {"dead_slots": {"buffer_species_spread": buf,
                                  "buffer_conc_spread": conc},
                   "monotonicity": mono, "optimum_geometry": geo}

print(json.dumps(report, indent=2))
Path("results/simulator_diagnosis_v1_vs_v2.json").write_text(json.dumps(report, indent=2))
