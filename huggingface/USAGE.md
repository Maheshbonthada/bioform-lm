# BioForm-LM: Quick Start Guide

**Before using this model, read `MODEL_CARD.md`.** The headline
protein-conditional claim is not supported by the evidence collected so far;
this guide is for reproducing the paper's real, verified results and for
building on the corrected pipeline, not for generating formulations to trust.

## Installation

```bash
git clone https://github.com/Maheshbonthada/bioform-lm.git
cd bioform-lm
pip install -r requirements.txt
pip install huggingface_hub datasets   # for Hub access
```

## Load a checkpoint

Two checkpoints are released, used together for the paper's in-context
necessity finding (Section 3.5): one pretrained on in-context-structured
sequences, one on flat triples only, sharing everything else.

```python
import torch
from huggingface_hub import hf_hub_download

from model.bioform_lm import BioFormLM
from model.tokenizer import FormulationTokenizer

tokenizer = FormulationTokenizer()

def load(filename):
    ckpt_path = hf_hub_download("Sravankumarbonthada/bioform-lm",
                                f"checkpoints/{filename}")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model = BioFormLM(vocab_size=tokenizer.vocab_size)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    return model, ckpt

icl_model, icl_ckpt = load("checkpoint_icl_best.pt")
flat_model, flat_ckpt = load("checkpoint_conditional_best.pt")
print(icl_ckpt["epoch"], icl_ckpt["val_loss"])
```

## Load the datasets

```python
import pandas as pd
from huggingface_hub import hf_hub_download

real_path = hf_hub_download("Sravankumarbonthada/BioFormBench",
                            "bioformbench_real.csv", repo_type="dataset")
marketed_path = hf_hub_download("Sravankumarbonthada/BioFormBench",
                                "bioformbench_marketed.csv", repo_type="dataset")

bfb_real = pd.read_csv(real_path)          # 49 rows, 13 proteins, literature-sourced
bfb_marketed = pd.read_csv(marketed_path)  # 165 rows, 80 approved antibodies, FDA-label-sourced
```

## Reproduce the paper's key results

```bash
# Simulator audit + correction
python scripts/diagnose_simulator.py
python scripts/diagnose_v2.py

# The n=27 -> n=80 selection artifact (Section 3.2 of the paper)
python scripts/analyze_sequence_conditionality.py
python scripts/validate_conditionality.py

# Platform-convergence result (Section 3.3)
python scripts/analyze_platform_convergence.py

# Original LOPO generative evaluation
python scripts/evaluate_real.py --checkpoint experiments/checkpoints_conditional/best.pt

# ICL-necessity comparison (Section 3.5): run each checkpoint with and without
# real context, compare likelihood_percentile per protein
python scripts/evaluate_real.py --checkpoint experiments/checkpoints_icl/best.pt --shots 2 --out results/icl_with.json
python scripts/evaluate_real.py --checkpoint experiments/checkpoints_icl/best.pt --no-context --out results/icl_without.json
```

## Generating candidate recipes (for exploration, not for use as-is)

```python
protein_desc = {"mw_kda": 148.0, "pi": 8.5, "tm_baseline_c": 72.0}
prefix = [tokenizer.CLS_ID] + tokenizer.encode_protein(**protein_desc) + [tokenizer.SEP_ID]
prefix_t = torch.tensor(prefix, dtype=torch.long)

candidates = icl_model.generate(prefix_t, num_candidates=50, temperature=1.0)
scores = icl_model.score_stability(
    torch.stack([torch.cat([prefix_t[:5], c]) for c in candidates])
)
top5 = candidates[scores.argsort(descending=True)[:5]]
```

Treat `top5` as computational hypotheses only. Per the model card and paper,
protein-conditional specificity in this pipeline is not distinguishable from
chance (0.509, 95% CI [0.358, 0.669]) at current sample sizes, so do not expect
`protein_desc` to meaningfully steer the output toward a molecule-specific
optimum yet.

## Contact

Bonthada Sravan Kumar — sravansaijohn@gmail.com
