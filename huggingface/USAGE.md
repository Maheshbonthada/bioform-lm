# BioForm-LM: Quick Start Guide

## Installation

```bash
# Clone repository
git clone https://github.com/Maheshbonthada/bioform-lm.git
cd bioform-lm

# Install dependencies
pip install -r requirements.txt

# Optional: For Hugging Face integration
pip install huggingface_hub datasets
```

## Load Model & Dataset

### Load from Hugging Face Hub

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from datasets import load_dataset

# Load model
model = AutoModelForCausalLM.from_pretrained("Maheshbonthada/bioform-lm")
tokenizer = AutoTokenizer.from_pretrained("Maheshbonthada/bioform-lm")

# Load BioFormBench dataset
dataset = load_dataset("Maheshbonthada/BioFormBench")
```

### Load Locally

```python
import torch
from bioform_lm.experiments.train import BioFormLM
from bioform_lm.model.tokenizer import FormulationTokenizer

# Load checkpoint
checkpoint = torch.load("experiments/checkpoints/checkpoint_epoch_7.pt")
model = BioFormLM(vocab_size=199, hidden_size=256, num_layers=6, num_heads=8)
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# Initialize tokenizer
tokenizer = FormulationTokenizer()
```

## Generate Formulation Candidates

### Minimal Example

```python
import torch

# Define novel protein
protein = {
    "mw": 27000,        # Molecular weight (Da)
    "pi": 5.8,          # Isoelectric point
    "tm": 65.0          # Baseline melting temperature (°C)
}

# Provide 3-10 real stability measurements as context
context_examples = [
    {
        "buffer": "phosphate",
        "ph": 6.5,
        "ionic_strength": 150,
        "stabilizer": "trehalose",
        "conc": 50,
        "stability": 0.92
    },
    {
        "buffer": "histidine",
        "ph": 6.0,
        "ionic_strength": 100,
        "stabilizer": "sucrose",
        "conc": 100,
        "stability": 0.88
    },
    {
        "buffer": "acetate",
        "ph": 5.5,
        "ionic_strength": 80,
        "stabilizer": "sorbitol",
        "conc": 75,
        "stability": 0.85
    }
]

# Generate 50 candidate recipes
with torch.no_grad():
    candidates = model.generate(
        protein=protein,
        context=context_examples,
        num_candidates=50,
        temperature=0.7,
        top_k=10
    )

# Get top-5 ranked by physics critic
top_5_recipes = candidates[:5]

# Print results
for i, recipe in enumerate(top_5_recipes, 1):
    print(f"\nRank {i}:")
    print(f"  Buffer: {recipe['buffer']} (pH {recipe['ph']})")
    print(f"  Ionic strength: {recipe['ionic_strength']} mM")
    print(f"  Stabilizer: {recipe['stabilizer']} ({recipe['conc']}% w/v)")
    print(f"  Predicted stability: {recipe['predicted_stability']:.3f}")
```

### Full Workflow with Evaluation

```python
from bioform_lm.evaluation.protocols import LOPOProtocol
from bioform_lm.evaluation.metrics import Recall, Calibration, Diversity
from datasets import load_dataset

# Load BioFormBench
dataset = load_dataset("Maheshbonthada/BioFormBench")

# Initialize evaluation protocol
lopo = LOPOProtocol(
    dataset=dataset,
    proteins=["protein_1_igg", "protein_2_scfv", "protein_3_fab"]
)

# Run leave-one-protein-out evaluation
results = lopo.evaluate(
    model=model,
    num_context_examples=3,
    num_candidates_to_generate=50
)

# Metrics
print(f"Recall@10: {results['recall_at_10']:.3f}")
print(f"Diversity (MPD): {results['diversity']:.3f}")
print(f"Calibration (Spearman r): {results['calibration']:.3f}")
print(f"Coverage: {results['coverage']:.1f}%")
```

## Training from Scratch

### Generate Synthetic Data

```python
from bioform_lm.data.synthetic_generator import SyntheticGenerator

# Initialize simulator
generator = SyntheticGenerator(
    num_samples=100000,
    seed=42
)

# Generate synthetic corpus
synthetic_data = generator.generate()
synthetic_data.to_csv("data/synthetic_training_data.csv", index=False)
synthetic_data.to_parquet("data/synthetic_training_data.parquet")
```

### Train Model

```python
from bioform_lm.experiments.train import train

# Training config
config = {
    "model": {
        "vocab_size": 199,
        "hidden_size": 256,
        "num_layers": 6,
        "num_heads": 8,
        "intermediate_size": 1024,
        "max_position_embeddings": 64,
        "dropout": 0.1
    },
    "training": {
        "batch_size": 32,
        "learning_rate": 1e-4,
        "num_epochs": 15,
        "device": "cuda",
        "checkpoint_dir": "experiments/checkpoints",
        "log_interval": 100
    }
}

# Train
train(config=config, data_path="data/synthetic_training_data.parquet")
```

## Baselines

Compare against predictive models:

```python
from bioform_lm.evaluation.baselines import RandomForest, SVM

# Train baselines on synthetic data
rf = RandomForest()
svm = SVM()

rf.fit(X_train, y_train)
svm.fit(X_train, y_train)

# Evaluate
rf_recall = rf.score(X_test, y_test)
svm_recall = svm.score(X_test, y_test)

print(f"RandomForest Recall@10: {rf_recall:.3f}")
print(f"SVM Recall@10: {svm_recall:.3f}")
print(f"BioForm-LM Recall@10: 0.167")
```

## Input Specifications

### Protein Descriptor Format

```json
{
  "mw": 27000,              // Molecular weight (Daltons) [10000-150000]
  "pi": 5.8,                // Isoelectric point [4.0-9.0]
  "tm": 65.0                // Baseline Tm (°C) [50-80]
}
```

### Formulation Recipe Format

```json
{
  "buffer": "phosphate",    // Options: histidine, phosphate, acetate, citrate
  "ph": 6.5,                // [4.5-7.5]
  "ionic_strength": 150,    // mM [50-300]
  "stabilizer": "trehalose",// Options: trehalose, sucrose, sorbitol, glycerol
  "conc": 50,               // % w/v [0-200]
  "stability": 0.92         // [0.0-1.0] for context examples
}
```

### Output Format

Each generated candidate includes:

```json
{
  "buffer": "phosphate",
  "ph": 6.5,
  "ionic_strength": 150,
  "stabilizer": "trehalose",
  "conc": 50,
  "predicted_stability": 0.91,
  "confidence": 0.85,
  "rank": 1
}
```

## Troubleshooting

### GPU Memory Error
```python
# Use CPU instead
model.to("cpu")
candidates = model.generate(..., device="cpu")
```

### Slow Generation
```python
# Reduce number of candidates
candidates = model.generate(num_candidates=10)  # Default: 50

# Use smaller temperature (more greedy)
candidates = model.generate(temperature=0.1)
```

### Model Not Found
```bash
# Download checkpoint manually
wget https://huggingface.co/Maheshbonthada/bioform-lm/resolve/main/checkpoint_epoch_7.pt
```

## Citation

If you use BioForm-LM, please cite:

```bibtex
@article{kumar2026bioformlm,
  title={BioForm-LM: Generative Design of Biologics Formulations via In-Context Learning and Physics-Informed Decoding},
  author={Kumar, Bonthada Sravan},
  journal={Research Square (Preprint)},
  year={2026},
  doi={10.21203/rs.[DOI]}
}
```

## Support

- **Issues:** https://github.com/Maheshbonthada/bioform-lm/issues
- **Discussions:** https://github.com/Maheshbonthada/bioform-lm/discussions
- **Email:** sravansaijohn@gmail.com

---

**Last Updated:** September 7, 2026
