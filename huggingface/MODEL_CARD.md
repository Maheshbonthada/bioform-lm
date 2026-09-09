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

## Real, verified results (BioFormBench-Real)

The protein-specificity number below was revised after this card's first
release. The original evaluation grouped "one protein" by a (molecular weight,
pI)-string match, which silently merged up to 4 different real antibodies
(Trastuzumab, Omalizumab, and two others) into one fake pooled protein wherever
their placeholder pI values collided — so the original 0.509 was measured on a
benchmark that could not, by construction, cleanly separate several of its own
proteins. Fixing the grouping and correcting pI for 5 of 13 proteins gives:

| Metric | Value | 95% CI / p | Chance | Folds |
|---|---|---|---|---|
| Likelihood percentile | 0.797 | CI [0.729, 0.865] | 0.5 | 9 (original grouping) |
| ...unconditional baseline | 0.872 | - | 0.5 | 9 |
| Protein specificity (original, buggy grouping) | 0.509 | CI [0.358, 0.669] | 0.5 | 9 |
| **Protein specificity (identity-fixed)** | **0.737–0.781** | **p = 0.016–0.023** | 0.5 | 8 (7 excl. one unresolved protein) |
| ...same-architecture untrained control | 0.565–0.625 | p = 0.20–0.50 (n.s.) | 0.5 | 8 |
| Recall@10 (exact match) | 0.011–0.025 | CI incl. 0 | - | 8–9 |

**Read this table correctly, in both directions.** The likelihood-percentile
caveat still holds: it is winnable from the marginal recipe distribution alone
(the unconditional baseline scores higher), so it does not by itself evidence
conditional knowledge. The corrected protein-specificity result is real
progress — significant, largely unanimous (7/7 once the one still-unresolved
protein, `mAb2`, is excluded), and not explained by an untrained
same-architecture control, which stays at chance. But it is **not fully
settled**: a second, independently-trained checkpoint
(`checkpoints_icl`) replicates the *direction* (Spearman rank agreement 0.73,
p=0.039 across the two checkpoints' per-protein values) but reaches
significance only marginally on its own (p=0.078), and an ablation intended as
an unconditional baseline unexpectedly also reached significance in this
setup, for reasons we could not fully re-verify (see the paper's Limitations).
Treat this as genuine, mechanistically-explained evidence that the earlier
chance-level verdict was partly a benchmark bug, not as proof the model has
learned formulation physics.

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
