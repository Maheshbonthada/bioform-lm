---
library_name: pytorch
tags:
  - drug-discovery
  - biologics
  - formulation-design
  - generative-model
  - in-context-learning
  - mechanistic-simulator
license: mit
datasets:
  - Sravankumarbonthada/BioFormBench
language: en
---

# BioForm-LM: an audited generative formulation-design pipeline

## Read this first

This checkpoint's headline architectural claim (protein-conditional generative
formulation design) is **not supported** by the evidence collected so far. That
finding, and how it was reached, is the actual contribution — see the companion
paper ("What Determines a Biologic's Formulation?") for the full analysis. This
card describes what the model demonstrably does and does not do; it does not
repeat an earlier draft's fabricated performance table.

## What changed from the original release

An earlier version of this card reported recall@10 = 0.167, perfect calibration
(r = 1.0) on a held-out protein, and 4.7x formulation-space coverage versus
random sampling. Those numbers came from an evaluation path that never actually
called the model (verified: the code path fell through to `np.random` before
reaching a model forward pass) and from a benchmark that, at the time, silently
dropped 49 of 67 rows via a CSV parser bug and kept 18 unsourced placeholder
rows. Both defects are now fixed, and the numbers below are freshly measured,
model-produced, and reproducible from `scripts/evaluate_real.py`.

## Architecture (unchanged)

Three-stage pipeline:

1. **Mechanistic simulator.** DLVO colloidal theory + Lumry-Eyring aggregation
   kinetics generate synthetic (protein, recipe) to stability triples for
   pretraining. An audit found the original version (v1) has two structurally
   dead recipe slots (buffer species/concentration change predicted stability
   by exactly 0.0) and corner-collapsing optima in 3 of 4 continuous variables
   (100% monotone for ionic strength, osmolarity, temperature). `v2`
   (`simulator/mechanistic_sim_v2.py`) adds nine literature-anchored competing
   degradation pathways that fix this; see the paper for the diagnostic.
2. **In-context generative transformer.** Decoder-only, 6 layers, 8 heads, 256
   hidden dim, 4.9M parameters, 199-token vocabulary. Pretrained on the
   synthetic corpus; adapts to a novel protein from 2-10 real measurements
   supplied in context, no gradient update.
3. **Stability-classification head.** Scores a full (protein, recipe) sequence
   for a discretized stability bin; used for best-of-N reranking.

## Real, verified results (BioFormBench-Real, 9 LOPO folds)

| Metric | Value | 95% CI | Chance |
|---|---|---|---|
| Likelihood percentile | 0.797 | [0.729, 0.865] | 0.5 |
| ...unconditional baseline | 0.872 | - | 0.5 |
| Protein specificity | 0.509 | [0.358, 0.669] | 0.5 |
| Recall@10 (exact match) | 0.011 | [0.000, 0.033] | - |
| Calibration (Spearman rho) | +0.280 | [-0.405, +0.964] | 0 |

**Read this table correctly.** Likelihood percentile looks good in isolation
(0.797) until compared against a protein-blind unconditional model, which
scores *higher* (0.872) — meaning that metric rewards learning the marginal
recipe distribution, not protein-conditional structure. Protein specificity
(swap the true protein descriptor for a foreign one; does the model still
prefer the real recipe?) is the metric that actually isolates conditional
knowledge, and it sits at 0.509, statistically indistinguishable from chance
(95% CI spans 0.5). Given a companion analysis on 80 real approved antibodies
found no detectable relationship between protein sequence and marketed
formulation choice either (see paper Section 3.3), this is not a surprising
model failure so much as the predictable consequence of conditioning on a
relationship that may not be there to learn at the sample sizes available.

## A finding that IS real and reproducible: ICL requires ICL-structured training

Holding the pretraining corpus fixed, a model trained on in-context-structured
sequences shows a real, unanimous effect of real context on likelihood
percentile (9/9 held-out proteins improve, mean +0.027), while a model trained
only on flat triples shows the opposite (9/9 proteins get worse, mean -0.060).
Both are exact permutation p = 0.0039. This is an architecture-level result,
verified by rerunning `scripts/evaluate_real.py` with and without context for
both checkpoints (`experiments/checkpoints_icl/best.pt` vs
`experiments/checkpoints_conditional/best.pt`) — not a domain-specific claim
about formulation design.

## Intended use

**What this model is not, currently:** a validated tool for proposing
formulations for a novel protein. The evidence above does not support that use.

**What it is useful for:** a reference implementation of the sim-to-real +
in-context architecture, a demonstration of the ICL-training-necessity finding
above (independent of the formulation domain), and a component to build on if
the underlying data problem (Discussion, companion paper) is addressed —
specifically, real *measured stability outcomes* across many proteins, not just
the 13 currently available in BioFormBench-Real, or a richer protein
representation than the current 3 scalar descriptors.

## Limitations

1. BioFormBench-Real supports only 9 LOPO folds; too few for a definitive
   protein-conditionality verdict on stability outcomes.
2. Protein descriptors used by this checkpoint are 3 quantized scalars (MW, pI,
   baseline Tm), not full sequence. A follow-up analysis using real VH/VL
   sequence-derived descriptors on 80 approved antibodies (BioFormBench-Marketed)
   also found no detectable protein effect on marketed formulation choice, which
   argues the null result is not merely an artifact of the impoverished
   descriptor, but this has not been tested with sequence descriptors fed
   directly into this model architecture.
3. No wet-lab validation at any stage.
4. Simulator v2's pathway weights are literature-informed, round numbers, not
   fit by optimization against any dataset — treat outputs as documented,
   falsifiable priors, not calibrated probabilities.

## Training details

- Framework: PyTorch, bf16 autocast, TF32 matmul
- Optimizer: AdamW, OneCycleLR
- Loss: joint next-recipe-token CE (masked to simulator-preferred rows) + stability-bin CE
- Hardware: RTX 3050 (8GB) + 28-core CPU for parallel data generation/encoding
- Sequence length: 13 tokens (5 protein-descriptor prefix + 8 recipe slots)

## Ethical considerations

Generated formulation recipes are computational hypotheses only, and the
evidence in this card is a reason for additional scrutiny before wet-lab
screening, not a substitute for it. Do not use outputs for therapeutic
decisions.

## Cite this model

```bibtex
@article{kumar2026bioformlm,
  title={What Determines a Biologic's Formulation? Two Open Benchmarks, an
         Audited Mechanistic Simulator, and a Well-Powered
         Platform-Convergence Result},
  author={Kumar, Bonthada Sravan},
  year={2026}
}
```

## Related resources

- GitHub: https://github.com/Maheshbonthada/bioform-lm
- Dataset: Sravankumarbonthada/BioFormBench (BioFormBench-Real + BioFormBench-Marketed)

## Author

Bonthada Sravan Kumar, Independent Researcher — sravansaijohn@gmail.com

## License

MIT

---

**Last updated:** September 8, 2026
