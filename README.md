# BioForm-LM: What Determines a Biologic's Formulation?

**Author:** Bonthada Sravan Kumar (Independent Researcher)
**License:** MIT

## Read this first

This repo previously claimed a working protein-conditional generative
formulation-design system, with results including recall@10 = 0.167 and
perfect calibration (r = 1.0) on a held-out protein. Those numbers were never
real: the evaluation code never called the model (it fell through to
`np.random`), and the benchmark it ran against silently dropped 49 of 67 real
rows to a CSV parser bug while keeping 18 unsourced placeholder rows. Both bugs
are now fixed. The corrected numbers, the audit that found the bugs, and what
the pipeline actually does and does not demonstrate are in the paper below —
please read `papers/BioForm-LM_Main_Paper.pdf`, not the historical `.md` status
files elsewhere in this repo, which are dated progress logs from before the
audit and are kept only as a record of how the project got here.

**The honest summary:** the central claim (a protein's identity determines its
formulation, learnable well enough to generate novel formulations for a new
protein) is not supported by the evidence collected so far, at the sample
sizes available. What survives, verified: two open benchmarks (one of them
new: 165 marketed formulations for 80 real approved antibodies with real
sequences), a documented and fixed structural flaw in a common mechanistic
simulator design pattern, a rigorous demonstration of how an n=27 selection
artifact can look like a real, correctly-signed, bootstrap-stable effect and
not be one, a well-powered negative result (formulation choice tracks a
constant "platform" baseline, not protein sequence), and an unrelated but real
architecture finding (in-context conditioning requires in-context-structured
pretraining, p = 0.0039 in both directions).

## Overview

Three-stage pipeline:
- **Mechanistic simulator** (`simulator/mechanistic_sim.py` = v1, audited;
  `simulator/mechanistic_sim_v2.py` = corrected) for synthetic pretraining data.
- **In-context generative transformer** (`model/bioform_lm.py`) for few-shot
  adaptation to novel proteins.
- **Stability-classification head** for best-of-N reranking.

## Installation

```bash
git clone https://github.com/Maheshbonthada/bioform-lm.git
cd bioform-lm
pip install -r requirements.txt
```

## Reproducing the paper's results

```bash
# Simulator audit (v1 dead slots / corner-seeking optima) and v2 correction
python scripts/diagnose_simulator.py
python scripts/diagnose_v2.py

# External, out-of-sample validation of v2 against real marketed formulations
python scripts/validate_v2_external.py

# The n=27 -> n=80 selection artifact and its resolution
python scripts/analyze_sequence_conditionality.py
python scripts/validate_conditionality.py

# Platform-convergence result (no covariate beats a constant baseline)
python scripts/analyze_platform_convergence.py

# BioFormBench-Marketed construction from scratch (FDA labels + Thera-SAbDab)
python scripts/harvest_labels_1_enumerate.py
python scripts/harvest_labels.py
python scripts/parse_labels.py
python scripts/compute_protein_descriptors.py

# Original LOPO generative evaluation on BioFormBench-Real
python scripts/evaluate_real.py --checkpoint experiments/checkpoints_conditional/best.pt

# ICL-necessity comparison (requires both checkpoints; see Hugging Face model repo)
python scripts/evaluate_real.py --checkpoint experiments/checkpoints_icl/best.pt --out results/icl_with.json
python scripts/evaluate_real.py --checkpoint experiments/checkpoints_icl/best.pt --no-context --out results/icl_without.json
```

## Data and model availability

- **Datasets** (BioFormBench-Real, 49 rows; BioFormBench-Marketed, 165 rows /
  80 sequenced antibodies): [huggingface.co/datasets/Sravankumarbonthada/BioFormBench](https://huggingface.co/datasets/Sravankumarbonthada/BioFormBench)
- **Model checkpoints** (ICL-trained and flat-trained, used for the
  in-context-necessity result): [huggingface.co/Sravankumarbonthada/bioform-lm](https://huggingface.co/Sravankumarbonthada/bioform-lm)
- **Paper:** `papers/BioForm-LM_Main_Paper.pdf` (two-column) or
  `papers/BioForm-LM_ResearchSquare.md` / `.docx` (single-column, for preprint
  submission).

## Project structure

```
bioform-lm/
├── model/               # Transformer (bioform_lm.py) + tokenizer
├── simulator/           # Mechanistic simulator: v1 (audited) and v2 (corrected)
├── data/                # BioFormBench-Real/Marketed CSVs, provenance, raw labels
├── evaluation/          # Benchmark loader, metrics, statistics
├── experiments/         # Checkpoints (gitignored; see Hugging Face)
├── scripts/             # Every analysis and figure in the paper, one script each
├── papers/              # Manuscript (LaTeX + Markdown), make_figures.py
├── results/             # Result JSONs (gitignored; regenerate via scripts/)
└── README.md            # This file
```

## Ethics and intended use

Generated formulations are computational hypotheses only, never clinical or
manufacturing recommendations, and the evidence in this repo is a reason for
additional scrutiny before any wet-lab use, not a substitute for it. No
human-subjects data was used. FDA label text and Thera-SAbDab sequences used to
build BioFormBench-Marketed are public regulatory and research records, used
here for descriptive analysis only.

## Citation

```bibtex
@article{kumar2026bioformlm,
  title={What Determines a Biologic's Formulation? Two Open Benchmarks, an
         Audited Mechanistic Simulator, and a Well-Powered
         Platform-Convergence Result},
  author={Kumar, Bonthada Sravan},
  year={2026}
}
```

## Contact

Bonthada Sravan Kumar — sravansaijohn@gmail.com
