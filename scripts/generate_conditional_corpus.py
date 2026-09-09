#!/usr/bin/env python3
"""
Build a synthetic pretraining corpus in which recipes actually depend on the
protein, parallelised across CPU cores.

The original corpus (data/synthetic_generator.py) draws the protein and the
formulation independently and lets only the *outcome* depend on both, so
P(recipe | protein) = P(recipe). A next-token model trained on it can learn the
marginal recipe distribution and nothing else -- which is what we measured:
recipe perplexity sat at 7.74 from epoch 1 to 30, against 13.6 for
uniform-within-slot. Marginals learned, conditional structure absent. Stage 1
could not "teach the model the physics", because the physics never entered the
recipe distribution.

Here, for each sampled protein we score many candidate recipes with the
mechanistic simulator and keep the best few, so P(recipe | protein) concentrates
on formulations the physics says work for *that* protein. Candidate count is the
knob that sharpens the signal: with 512 candidates the kept recipes sit far
further into the tail than with 64, which is what the generative head needs.
The simulator is pure CPU at ~14 us/call, so this scales linearly with cores.

Rows are tagged `is_preferred`:
  1 -> simulator-preferred recipe; carries the language-modelling loss.
  0 -> uniformly random recipe; retained so the stability head still sees the
       full outcome range instead of only high-stability examples.

    python scripts/generate_conditional_corpus.py --proteins 60000 --candidates 512
"""

import argparse
import json
import logging
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _worker(task):
    """Generate one shard. Imports happen inside so Windows spawn works."""
    seed, n_proteins, n_candidates, keep_top, keep_random = task
    logging.disable(logging.INFO)
    from data import synthetic_generator as sg

    gen = sg.SyntheticDataGenerator(num_samples=1, seed=seed)
    sim = gen.simulator
    rng = np.random.default_rng(seed)
    rows = []

    for _ in range(n_proteins):
        protein = gen._sample_protein()
        cands = [gen._sample_formulation() for _ in range(n_candidates)]
        scores = np.fromiter(
            (sim.predict(protein, f).stability_score for f in cands),
            dtype=float, count=n_candidates,
        )
        order = np.argsort(-scores)
        chosen = [(cands[j], scores[j], 1) for j in order[:keep_top]]
        for j in rng.choice(n_candidates, size=keep_random, replace=False):
            chosen.append((cands[j], scores[j], 0))

        for f, s, pref in chosen:
            rows.append({
                "protein_mw_kda": protein.mw_kda,
                "protein_pi": protein.pi,
                "protein_tm_baseline_c": protein.tm_baseline_c,
                "buffer_species": f.buffer_species,
                "buffer_conc_mm": f.buffer_conc_mm,
                "ph": f.ph,
                "ionic_strength_mm": f.ionic_strength_mm,
                "osmolarity_mosm_kg": f.osmolarity_mosm_kg,
                "stabilizers_json": json.dumps(f.stabilizers or {}),
                "temperature_c": f.temperature_c,
                "stability_score": float(s),
                "is_preferred": pref,
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proteins", type=int, default=60000)
    ap.add_argument("--candidates", type=int, default=512, help="scored per protein")
    ap.add_argument("--keep-top", type=int, default=3)
    ap.add_argument("--keep-random", type=int, default=1)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/conditional_training_data.parquet")
    a = ap.parse_args()

    per = [a.proteins // a.workers] * a.workers
    for i in range(a.proteins - sum(per)):
        per[i] += 1
    tasks = [(a.seed + i, per[i], a.candidates, a.keep_top, a.keep_random)
             for i in range(a.workers) if per[i] > 0]

    calls = a.proteins * a.candidates
    print(f"{a.proteins:,} proteins x {a.candidates} candidates "
          f"= {calls:,} simulator calls across {len(tasks)} workers")

    t0 = time.time()
    with Pool(len(tasks)) as pool:
        shards = pool.map(_worker, tasks)
    rows = [r for shard in shards for r in shard]
    dt = time.time() - t0

    df = pd.DataFrame(rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(a.out, index=False)

    pref = df[df.is_preferred == 1]["stability_score"]
    rand = df[df.is_preferred == 0]["stability_score"]
    print(f"\nwrote {a.out}: {len(df):,} rows  [{dt:.0f}s, "
          f"{calls/dt/1000:.0f}k calls/s]")
    print(f"  preferred {len(pref):,}  mean stability {pref.mean():.3f}")
    print(f"  random    {len(rand):,}  mean stability {rand.mean():.3f}")
    print(f"  separation {pref.mean() - rand.mean():+.3f}  "
          f"(the conditional signal available to the LM)")


if __name__ == "__main__":
    main()
