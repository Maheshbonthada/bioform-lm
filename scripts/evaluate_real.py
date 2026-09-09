#!/usr/bin/env python3
"""
Leave-one-protein-out evaluation that actually runs the model.

The previous evaluator (scripts/evaluate.py) loaded the checkpoint and then never
called it: `_generate_recipes` returned `np.random` draws behind a
"TODO: Use actual generation from model", and calibration correlated
`np.random.uniform(0.5, 0.95, n)` against the measured scores. Every reported
number was noise.

This version generates with the trained model under grammar constraints, ranks
with the stability head (best-of-N), and reports exact permutation p-values and
bootstrap intervals.

    python scripts/evaluate_real.py --checkpoint experiments/checkpoints_conditional/best.pt
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.INFO)

from evaluation.benchmark_v2 import BioFormBenchV2
from evaluation.stats import bootstrap_ci, spearman_exact
from model.bioform_lm import BioFormLM, PREFIX_LEN, RECIPE_SLOTS
from model.tokenizer import FormulationTokenizer

# A generated recipe counts as matching a real one when the discretised buffer,
# pH and ionic-strength slots agree. Those are the three variables the
# formulation literature reports most consistently; requiring all eight slots to
# agree would make matching essentially impossible at this vocabulary size.
MATCH_SLOTS = ["BUFFER", "PH", "IS"]


def encode_row(tk, row, tm_clean):
    ids, _ = tk.encode_sample(
        {"mw_kda": row.protein_mw_kda, "pi": row.protein_pi, "tm_baseline_c": tm_clean},
        {
            "buffer_species": row.buffer_species,
            "buffer_conc_mm": row.buffer_conc_mm,
            "ph": row.ph,
            "ionic_strength_mm": row.ionic_strength_mm,
            "osmolarity_mosm_kg": row.osmolarity_mosm_kg,
            "temperature_c": row.temperature_c,
            "stabilizers": row.stabilizers_json,
        },
    )
    # Rows with no stabilizer yield 11 tokens rather than 13, since the tokenizer
    # emits the STAB/STABCONC pair only when a stabilizer is present. Pad to the
    # fixed slot layout so batches stack; the matched slots (buffer, pH, ionic
    # strength) sit before the padding and are unaffected.
    ids = ids[: PREFIX_LEN + len(RECIPE_SLOTS)]
    return ids + [tk.PAD_ID] * (PREFIX_LEN + len(RECIPE_SLOTS) - len(ids))


def slot_key(tokens):
    idx = {n: i for i, (n, _, _) in enumerate(RECIPE_SLOTS)}
    return tuple(int(tokens[idx[s]]) for s in MATCH_SLOTS)


@torch.no_grad()
def recipe_logprob(model, prefix, recipes, device):
    """Teacher-forced log P(recipe | prefix) for a batch of recipes."""
    P = len(prefix)
    seq = torch.cat([
        torch.tensor(prefix, dtype=torch.long).unsqueeze(0).repeat(len(recipes), 1),
        torch.as_tensor(recipes, dtype=torch.long),
    ], dim=1).to(device)
    _, logits = model(seq)
    lp = torch.log_softmax(logits[:, P - 1: -1, :].float(), dim=-1)
    tgt = seq[:, P:]
    return lp.gather(2, tgt.unsqueeze(-1)).squeeze(-1).sum(dim=1).cpu().numpy()


def likelihood_percentile(model, prefix, true_recipes, device, n_ref=2000, seed=0):
    """
    Fraction of random grammar-valid recipes the model ranks *below* the true one.

    Exact-match recall is dominated by sampling luck when the match space is far
    larger than the candidate budget, so it cannot separate a model that has
    learned useful structure from one that has not. This is sampling-free: it
    asks directly whether the model places more probability mass on the real
    held-out formulation than on arbitrary valid alternatives. 0.5 is chance.
    """
    rng = np.random.default_rng(seed)
    ref = np.stack([
        rng.integers(lo, hi, size=n_ref) for _, lo, hi in RECIPE_SLOTS
    ], axis=1)
    ref_lp = recipe_logprob(model, prefix, ref, device)
    true_lp = recipe_logprob(model, prefix, np.asarray(true_recipes), device)
    return float(np.mean([(ref_lp < t).mean() for t in true_lp]))


def protein_specificity(model, prefix_builder, true_recipes, other_keys, device):
    """
    Does the model prefer these recipes under their *own* protein descriptor?

    The likelihood percentile compares real recipes against uniform-random ones,
    which a model can win on marginals alone -- and indeed the unconditionally
    pretrained baseline scores higher on it (0.872) than the conditional model
    (0.860), so it cannot evidence protein-conditional knowledge. This instead
    holds the recipe fixed and swaps the conditioning protein: a model that has
    learned P(recipe | protein) should assign higher likelihood under the correct
    descriptor than under a foreign one. 0.5 is chance.
    """
    own = recipe_logprob(model, prefix_builder(None), true_recipes, device)
    wins, total = 0, 0
    for k in other_keys:
        alt = recipe_logprob(model, prefix_builder(k), true_recipes, device)
        wins += int((own > alt).sum())
        total += len(own)
    return wins / max(total, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default="experiments/checkpoints_conditional/best.pt")
    ap.add_argument("--shots", type=int, default=2)
    ap.add_argument("--candidates", type=int, default=50)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--no-critic", action="store_true",
                    help="ablation: skip best-of-N reranking, keep sample order")
    ap.add_argument("--no-context", action="store_true",
                    help="ablation: drop in-context examples from the prefix")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="results/lopo_real.json")
    a = ap.parse_args()

    tk = FormulationTokenizer()
    ck = torch.load(a.checkpoint, map_location=a.device, weights_only=False)
    model = BioFormLM(vocab_size=tk.vocab_size).to(a.device)
    model.load_state_dict(ck["model_state_dict"])
    model.eval()

    bench = BioFormBenchV2()
    bench.load()
    print("benchmark: " + json.dumps(bench.summary()))
    print("checkpoint: {} (epoch {}, val {:.4f})\n".format(
        a.checkpoint, ck.get("epoch"), ck.get("val_loss", float("nan"))))

    per_protein = {}
    for key in bench.proteins():
        rows = bench.protein_rows(key).reset_index(drop=True)
        desc = bench.descriptor(key)
        tm = desc["tm_baseline_c"]

        # Deterministic split: the K highest-stability formulations become the
        # in-context examples, the remainder are held out for scoring.
        order = rows["stability_score"].sort_values(ascending=False).index.tolist()
        shot_idx, test_idx = order[: a.shots], order[a.shots:]
        if len(test_idx) < 2:
            continue

        prefix = [tk.CLS_ID] + tk.encode_protein(desc["mw_kda"], desc["pi"], tm) + [tk.SEP_ID]
        if not a.no_context:
            for i in shot_idx:
                prefix += encode_row(tk, rows.loc[i], tm)[PREFIX_LEN:]
                prefix += [tk.encode_stability(float(rows.loc[i, "stability_score"]))]
        prefix_t = torch.tensor(prefix, dtype=torch.long)

        real_keys = {slot_key(encode_row(tk, rows.loc[i], tm)[PREFIX_LEN:]) for i in test_idx}

        rec, div, cov = [], [], []
        for seed in a.seeds:
            g = torch.Generator(device=a.device).manual_seed(seed)
            cands = model.generate(prefix_t, num_candidates=a.candidates,
                                   temperature=a.temperature, generator=g).cpu()
            if a.no_critic:
                ranked = cands
            else:
                seqs = torch.stack([
                    torch.cat([torch.tensor(prefix[:PREFIX_LEN]), c]) for c in cands
                ]).to(a.device)
                scores = model.score_stability(seqs).cpu().numpy()
                ranked = cands[np.argsort(-scores)]

            keys = [slot_key(c.tolist()) for c in ranked]
            rec.append(sum(1 for k in keys[:10] if k in real_keys) / min(10, len(real_keys)))
            div.append(len(set(keys)) / len(keys))
            cov.append(len(set(keys)) / (6 * 20 * 20))   # |BUFFER| * |PH| * |IS|

        # Likelihood percentile on the held-out real formulations.
        true_recipes = [encode_row(tk, rows.loc[i], tm)[PREFIX_LEN:] for i in test_idx]
        lp_pct = likelihood_percentile(model, prefix, true_recipes, a.device)

        # Protein specificity: same recipes, foreign conditioning descriptors.
        def build_prefix(other_key, _rows=rows, _tm=tm, _sh=shot_idx):
            d = bench.descriptor(other_key) if other_key else desc
            t_ = bench.descriptor(other_key)["tm_baseline_c"] if other_key else _tm
            px = [tk.CLS_ID] + tk.encode_protein(d["mw_kda"], d["pi"], t_) + [tk.SEP_ID]
            if not a.no_context:
                for i in _sh:
                    px += encode_row(tk, _rows.loc[i], _tm)[PREFIX_LEN:]
                    px += [tk.encode_stability(float(_rows.loc[i, "stability_score"]))]
            return px
        others = [k for k in bench.proteins() if k != key]
        spec = protein_specificity(model, build_prefix, true_recipes, others, a.device)

        # Calibration: model score vs measured stability on the held-out rows.
        test_seq = torch.tensor(
            [encode_row(tk, rows.loc[i], tm) for i in test_idx], dtype=torch.long
        ).to(a.device)
        pred = model.score_stability(test_seq).cpu().numpy()
        actual = rows.loc[test_idx, "stability_score"].to_numpy()
        rho, p, method = spearman_exact(pred, actual)

        per_protein[key] = {
            "n_formulations": int(len(rows)),
            "n_shots": len(shot_idx) if not a.no_context else 0,
            "n_test": len(test_idx),
            "recall_at_10": float(np.mean(rec)),
            "recall_sd": float(np.std(rec)),
            "diversity": float(np.mean(div)),
            "likelihood_percentile": lp_pct,
            "protein_specificity": spec,
            "coverage": float(np.mean(cov)),
            "calibration_rho": None if np.isnan(rho) else float(rho),
            "calibration_p": None if np.isnan(p) else float(p),
            "calibration_method": method,
            "example_id": str(rows.iloc[0]["protein_id"]),
        }
        r = per_protein[key]
        print("{:<28} n={:>2}  lik%={:.3f}  spec={:.3f}  div={:.3f}  "
              "rho={:+.3f}".format(
                  r["example_id"][:28], r["n_formulations"], lp_pct, spec,
                  r["diversity"], rho))

    rec_all = [v["recall_at_10"] for v in per_protein.values()]
    rho_all = [v["calibration_rho"] for v in per_protein.values()
               if v["calibration_rho"] is not None]
    spec_all = [v["protein_specificity"] for v in per_protein.values()]
    sm, slo, shi = bootstrap_ci(spec_all)
    lik_all = [v["likelihood_percentile"] for v in per_protein.values()]
    lm_, llo, lhi = bootstrap_ci(lik_all)
    m, lo, hi = bootstrap_ci(rec_all)
    mr, rlo, rhi = bootstrap_ci(rho_all) if rho_all else (float("nan"),) * 3

    agg = {
        "n_folds": len(per_protein),
        "recall_at_10": {"mean": m, "ci95": [lo, hi]},
        "likelihood_percentile": {"mean": lm_, "ci95": [llo, lhi], "chance": 0.5},
        "protein_specificity": {"mean": sm, "ci95": [slo, shi], "chance": 0.5},
        "calibration_rho": {"mean": mr, "ci95": [rlo, rhi]},
        "diversity": {"mean": float(np.mean([v["diversity"] for v in per_protein.values()]))},
        "coverage": {"mean": float(np.mean([v["coverage"] for v in per_protein.values()]))},
        "config": {
            "shots": 0 if a.no_context else a.shots,
            "candidates": a.candidates,
            "seeds": a.seeds,
            "checkpoint": a.checkpoint,
            "match_slots": MATCH_SLOTS,
            "no_critic": a.no_critic,
            "no_context": a.no_context,
        },
        "benchmark": bench.summary(),
    }
    print("\nfolds {}".format(agg["n_folds"]))
    print("recall@10   {:.3f}  95% CI [{:.3f}, {:.3f}]".format(m, lo, hi))
    print("likelihood% {:.3f}  95% CI [{:.3f}, {:.3f}]   (chance 0.500)".format(lm_, llo, lhi))
    print("specificity {:.3f}  95% CI [{:.3f}, {:.3f}]   (chance 0.500)".format(sm, slo, shi))
    print("calibration {:+.3f}  95% CI [{:+.3f}, {:+.3f}]".format(mr, rlo, rhi))
    print("diversity   {:.3f}".format(agg["diversity"]["mean"]))
    print("coverage    {:.3f}".format(agg["coverage"]["mean"]))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"aggregate": agg, "per_protein": per_protein}, indent=2))
    print("\nwrote " + a.out)


if __name__ == "__main__":
    main()
