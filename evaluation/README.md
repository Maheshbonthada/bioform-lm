# Evaluation Module

Evaluation framework for BioForm-LM on real biologics formulation data.

## Components

### BioFormBench Loader (`bioformbench.py`)

Loads curated real formulation data from literature mining.

**Expected CSV columns:**
- `protein_id`: unique protein identifier
- `protein_mw_kda`: molecular weight (kDa)
- `protein_pi`: isoelectric point
- `protein_tm_baseline_c`: baseline melting temperature (°C)
- `buffer_species`: e.g., "histidine", "phosphate"
- `buffer_conc_mm`: buffer concentration (mM)
- `ph`: pH value
- `ionic_strength_mm`: ionic strength (mM)
- `osmolarity_mosm_kg`: osmolarity (mOsm/kg)
- `stabilizers_json`: JSON dict of stabilizers
- `temperature_c`: storage temperature (°C)
- `stability_score`: measured outcome (0-1, higher=better)
- `measured_aggregation_percent` (optional): SEC aggregation %
- `measured_tm_shift_c` (optional): thermal shift

**Usage:**

```python
from evaluation.bioformbench import BioFormBench

bench = BioFormBench("data/bioformbench.csv")
bench.load()

# Get data for a protein
protein_data = bench.get_protein_data("protein_1")
descriptor = bench.get_protein_descriptor("protein_1")
top_formulations = bench.get_top_formulations("protein_1", k=5)
```

### Metrics (`metrics.py`)

Three evaluation metrics:

#### RecallMetric: Top-k Recipe Recall

Measures if generated recipes match known-good ones.

```python
from evaluation.metrics import RecallMetric

metric = RecallMetric(distance_threshold=0.15)
recall, num_matches = metric.compute(generated, known_good, k=5)
# recall: fraction of known-good recipes found in top-k generated
```

#### CalibrationMetric: Predicted vs Actual Stability

Measures alignment between predicted and measured stability scores.

```python
from evaluation.metrics import CalibrationMetric

metric = CalibrationMetric()
result = metric.compute(predicted_scores, actual_scores)
# Returns: spearman_r, kendall_tau, mae, rmse, etc.
```

#### DiversityMetric: Recipe Diversity

Measures variety of generated recipes.

```python
from evaluation.metrics import DiversityMetric

metric = DiversityMetric()
result = metric.compute(generated_formulations)
# Returns: mean_pairwise_distance, coverage, etc.
```

### Protocols (`protocols.py`)

Cross-validation strategies:

#### LeaveOneProteinOut (LOPO)

For each protein, use it as test set and all others for training.

```python
from evaluation.protocols import LeaveOneProteinOut

splitter = LeaveOneProteinOut(df)
for train_proteins, test_protein in splitter.split():
    # Evaluate on test_protein
    pass

# Or get indices for specific fold
train_idx, test_idx = splitter.get_split_data(df, fold_idx=0)
```

#### RandomSplit

Simple train/test split.

```python
from evaluation.protocols import RandomSplit

splitter = RandomSplit(train_ratio=0.8, random_state=42)
train_idx, test_idx = splitter.split(df)
```

#### FewShotEval

LOPO variant where test protein provides few real measurements for conditioning.

```python
from evaluation.protocols import FewShotEval

evaluator = FewShotEval(n_shots=3)
shot_idx, test_idx = evaluator.get_shot_indices(df, "protein_1")
```

## Workflow Example

```python
import pandas as pd
from evaluation.bioformbench import BioFormBench
from evaluation.protocols import LeaveOneProteinOut
from evaluation.metrics import RecallMetric, CalibrationMetric, DiversityMetric

# Load data
bench = BioFormBench("data/bioformbench.csv")
df = bench.load()

# Set up LOPO
splitter = LeaveOneProteinOut(df)

# Metrics
recall_metric = RecallMetric()
cal_metric = CalibrationMetric()
div_metric = DiversityMetric()

# Evaluate on each fold
results = []
for i, (train_proteins, test_protein) in enumerate(splitter.split()):
    train_idx, test_idx = splitter.get_split_data(df, i)
    
    # Train on train_idx, get predictions on test_idx
    # generated_recipes = model.generate(...)
    # predicted_scores = model.predict_stability(...)
    
    # Compute metrics
    recall, _ = recall_metric.compute(generated, known_good)
    cal_result = cal_metric.compute(predicted, actual)
    div_result = div_metric.compute(generated)
    
    results.append({
        "protein": test_protein,
        "recall": recall,
        "spearman_r": cal_result["spearman_r"],
        "diversity": div_result["mean_pairwise_distance"],
    })

# Aggregate results
df_results = pd.DataFrame(results)
print(df_results.mean())
```

## Unit Tests

Run tests with:

```bash
pytest tests/test_evaluation.py -v
```

Tests cover:
- BioFormBench loader and data access
- Metric computation (recall, calibration, diversity)
- Cross-validation protocols (LOPO, random split, few-shot)
- Edge cases (empty sets, single samples, etc.)

## Status

- **BioFormBench loader**: ✅ Complete, 7 tests
- **Metrics**: ✅ Complete, 10 tests
- **Protocols**: ✅ Complete, 6 tests
- **Total**: ✅ 23 tests passing

## Next Steps

Once the model is trained:
1. Save trained checkpoint to `experiments/checkpoints/`
2. Create `data/bioformbench.csv` with literature-mined real data
3. Run evaluation with `scripts/evaluate.py --checkpoint PATH --data_file data/bioformbench.csv`
4. Results saved to `evaluation/results/`
