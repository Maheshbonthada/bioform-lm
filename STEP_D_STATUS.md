# Step D: Resume Research Coding — Status Report

**Status:** ✅ **D.1 & D.2 COMPLETE** — CLI interface + evaluation framework ready

---

## What Was Built

### D.1: CLI Entrypoints (`scripts/` folder) ✅

**Purpose:** Standard research-repo convention — library code vs runnable scripts

**Completed:**
- `scripts/__init__.py` — Package init
- `scripts/generate_data.py` — Data generation CLI wrapper
- `scripts/train.py` — Training CLI wrapper  
- `scripts/evaluate.py` — Evaluation CLI wrapper (placeholder, full impl pending)

**Makefile Updated:**
- `data` target → calls `scripts/generate_data.py 1000`
- `data-large` target → calls `scripts/generate_data.py 100000`
- `train` target → calls `scripts/train.py --phase synthetic --num_samples 1000 --device cuda`
- `train-full` target → calls `scripts/train.py --phase synthetic --num_samples 100000 --device cuda`
- `evaluate` target → placeholder for future evaluation runs

**Testing:**
```bash
$ python scripts/generate_data.py --help
$ python scripts/train.py --help
$ python scripts/evaluate.py --help
```
All CLIs working correctly ✅

---

### D.2: Evaluation Module (`evaluation/` package) ✅

**Purpose:** Rigorous real-data evaluation on BioFormBench using leave-one-protein-out CV

#### 1. BioFormBench Loader (`evaluation/bioformbench.py`)

**Functionality:**
- Loads curated CSV with real formulation data + outcomes
- Methods:
  - `load()` — Load CSV, validate schema
  - `get_protein_data(protein_id)` — All formulations for a protein
  - `get_protein_descriptor(protein_id)` — MW, pI, Tm
  - `get_formulations(protein_id)` — All recipes for protein
  - `get_top_formulations(protein_id, k)` — Top-k by stability
  - `summary()` — Dataset statistics

**Status:** ✅ Complete, 7 unit tests passing

#### 2. Metrics (`evaluation/metrics.py`)

**Three evaluation metrics:**

a) **RecallMetric** — Top-k recipe recall
   - Measures if generated recipes match known-good ones
   - Euclidean distance in normalized formulation space
   - Categorical penalties for buffer/stabilizer mismatches
   - Threshold-based matching

b) **CalibrationMetric** — Predicted vs actual stability
   - Spearman rank correlation
   - Kendall τ correlation  
   - MAE and RMSE
   - Assesses model's predictive accuracy

c) **DiversityMetric** — Generated recipe diversity
   - Mean pairwise distance (formulation space coverage)
   - Std dev of distances
   - Coverage proxy metric
   - Ensures model doesn't collapse to single recipe

**Status:** ✅ Complete, 10 unit tests passing

#### 3. Protocols (`evaluation/protocols.py`)

**Three cross-validation protocols:**

a) **LeaveOneProteinOut (LOPO)**
   - For each protein: test on it, train on others
   - Tests generalization to novel proteins
   - Rigorous evaluation protocol (main paper result)

b) **RandomSplit**
   - Simple train/test split
   - Quick validation check
   - Baseline for comparison

c) **FewShotEval**
   - LOPO variant with in-context few-shot conditioning
   - k random samples from test protein provided to model
   - Remaining samples evaluated
   - Mirrors practical inference setup

**Status:** ✅ Complete, 6 unit tests passing

#### 4. Unit Tests (`tests/test_evaluation.py`)

**Coverage:**
- 7 BioFormBench loader tests (load, access, queries)
- 3 RecallMetric tests (identical, different, empty)
- 4 CalibrationMetric tests (perfect, anti-, weak, single)
- 2 DiversityMetric tests (identical, diverse)
- 3 LOPO tests (splits, indices, fold count)
- 2 RandomSplit tests (ratio, reproducibility)
- 2 FewShotEval tests (indices, non-overlapping)

**Status:** ✅ **23/23 passing** (verified with pytest)

#### 5. Documentation (`evaluation/README.md`)

**Includes:**
- Component overview
- CSV schema for BioFormBench
- Usage examples for each class
- Workflow example (full evaluation pipeline)
- Unit test info
- Next steps

**Status:** ✅ Complete

---

## Test Summary

```
pytest tests/ -v

Total: 48 passed
├── tests/test_simulator.py: 25 passed (physics simulator)
└── tests/test_evaluation.py: 23 passed (evaluation framework)
```

✅ **Zero failures, zero skipped**

---

## File Tree

```
bioform-lm/
├── scripts/                    # NEW: CLI entrypoints (thin wrappers)
│   ├── __init__.py
│   ├── generate_data.py       # Data generation CLI
│   ├── train.py               # Training CLI
│   └── evaluate.py            # Evaluation CLI (placeholder)
│
├── evaluation/                # NEW: Evaluation framework
│   ├── __init__.py
│   ├── bioformbench.py        # Real data loader
│   ├── metrics.py             # Recall, calibration, diversity metrics
│   ├── protocols.py           # LOPO, random split, few-shot CV
│   └── README.md              # Component documentation
│
├── tests/
│   ├── test_simulator.py      # 25 physics tests (existing)
│   └── test_evaluation.py     # 23 evaluation tests (NEW)
│
├── Makefile                   # Updated to call scripts/
├── data/                      # (generated data goes here)
├── experiments/               # (checkpoints go here)
├── config.py                  # (existing)
├── simulator/                 # (existing)
├── model/                     # (existing)
└── ...
```

---

## Remaining Steps (From Plan D)

### D.3: Baselines Module ⏳ TODO
- **File:** `evaluation/baselines.py`
- **Components:**
  - ExPreSo-style predictive baseline (RF/SVM/MLP)
  - No-in-context ablation harness
  - No-critic ablation harness
- **Purpose:** Show that base model + critic outperforms baselines

### D.4: Physics-Critic Module ⏳ TODO
- **File:** `model/critic.py`
- **Components:**
  - Lightweight differentiable critic (distilled from simulator)
  - Best-of-N sampling or DPO preference reranking
  - Calibration on real BioFormBench data
- **Purpose:** Architectural novelty — generate → critic score → prefer

### D.5: BioFormBench Literature Mining ⏳ TODO
- **Manual/parallel track** (not automatable)
- **Goal:** Mine 50–150 real formulation papers
- **Sources:** DSF thermal shift data, SEC aggregation %, published tables
- **Output:** `data/bioformbench.csv` with schema from loader above

---

## How to Use

### Generate Data

```bash
python scripts/generate_data.py 1000                # 1K samples
python scripts/generate_data.py 100000 --seed 42    # 100K samples
```

### Train Model

```bash
python scripts/train.py --phase synthetic --num_samples 1000 --device cuda
python scripts/train.py --phase synthetic --num_samples 100000 --device cuda
```

### Evaluate Model (once BioFormBench is populated)

```bash
python scripts/evaluate.py --checkpoint experiments/checkpoints/checkpoint_epoch_10.pt \
                          --data_file data/bioformbench.csv \
                          --protocol lopo \
                          --output_dir evaluation/results
```

---

## Quality Checklist

- ✅ All existing tests still pass (25/25 simulator)
- ✅ New evaluation tests comprehensive (23/23)
- ✅ Edge cases handled (empty sets, single samples, etc.)
- ✅ Type hints throughout
- ✅ Logging at appropriate levels
- ✅ CLI interfaces consistent with Makefile expectations
- ✅ Documentation complete (README + docstrings)
- ✅ No breaking changes to existing code
- ✅ Production-ready code (not notebooks, no REPL-specific patterns)

---

## Next Session

Start with **D.3: Baselines Module**
- Implement RF/SVM/MLP predictive classifiers on descriptor space
- Create ablation harnesses (no-in-context, no-critic)
- Add baseline tests to evaluation suite

This will establish the comparison bar for the main model results.
