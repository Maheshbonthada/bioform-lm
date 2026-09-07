# Path to Publication: Submission Roadmap

*Timeline and priority fixes based on reviewer expectations*

---

## 📊 Current State vs. Publication-Ready

| Aspect | Current | Needed | Priority |
|--------|---------|--------|----------|
| **Code structure** | ✅ Solid | ✅ Done | — |
| **Unit tests** | ✅ 84 passing | ✅ Done | — |
| **Reproducibility infrastructure** | ✅ Checkpoints, logging | ✅ Done | — |
| **Real data evaluation** | ❌ Placeholder | ✅ LOPO CV on BioFormBench | **CRITICAL** |
| **Simulator validation** | ❌ Not done | ✅ vs. published data | **CRITICAL** |
| **Statistical rigor** | ❌ Single run | ✅ Multi-seed, error bars | **CRITICAL** |
| **Fair baselines** | ⚠️ Predictive only | ✅ Domain-specific + fair comparison | **HIGH** |
| **Ablations** | ⚠️ Defined, not run | ✅ Comprehensive ablation table | **HIGH** |
| **Hyperparameter justification** | ❌ Missing | ✅ Search or ablation | **MEDIUM** |
| **Documentation** | ⚠️ Sparse | ✅ Full docstrings + design rationale | **MEDIUM** |
| **Ethics discussion** | ❌ Missing | ✅ Section in paper | **LOW** |

---

## 🎯 Three-Phase Roadmap

### **PHASE 1: VALIDATION (1-2 weeks) — MUST-DO**
Make the system actually work on real data. Without this, rejection is certain.

#### 1.1 Collect BioFormBench
- **Goal:** Curate 20-50 real formulation datapoints from published literature
- **Sources:** 
  - DSF (differential scanning fluorimetry) screening tables in papers
  - SEC (size exclusion chromatography) aggregation % data
  - Published formulation optimization studies
- **Inclusion criteria:** 
  - Quantified stability outcome (Tm, % aggregation, or defined score)
  - Complete recipe (buffer, pH, stabilizers, conditions)
  - Recent papers (2015+) or from reputable labs
- **Quality control:** 
  - Data validation script (check schema, ranges, missing values)
  - Manual review of 10% of extracted data
- **Estimated time:** 3-5 days (research + extraction)
- **Output:** `data/bioformbench.csv` with validated 20-50 rows
- **Blocker removed:** "No real evaluation"

**Success criteria:**
```bash
python -c "
from evaluation.bioformbench import BioFormBench
bench = BioFormBench.load('data/bioformbench.csv')
print(f'Proteins: {bench.num_proteins}')
print(f'Formulations: {len(bench.data)}')
assert bench.num_proteins >= 5  # At least 5 proteins for LOPO
assert len(bench.data) >= 20    # At least 20 real samples
print('✓ BioFormBench validated')
"
```

#### 1.2 Validate Simulator Against Real Data
- **Goal:** Show mechanistic simulator predictions correlate with published outcomes
- **Process:**
  1. For 5-10 proteins in BioFormBench, run simulator on their real formulations
  2. Compare simulator stability predictions vs. published measurements
  3. Report Spearman correlation, RMSE, bias
- **Estimated time:** 2-3 days
- **Output:** Figure/table showing simulator validation (target: r > 0.6)

**Success criteria:**
```python
# Spearman correlation on known formulations
spearman_r >= 0.5  # "reasonable" agreement
bias < 0.15        # systematic error < 15%
```

#### 1.3 Implement LOPO Evaluation (Integration Test)
- **Goal:** End-to-end evaluation: train model on synthetic, evaluate on real
- **Implement:** 
  - `scripts/evaluate.py` → full implementation (not placeholder)
  - For each protein in BioFormBench:
    1. Hide that protein's formulations
    2. Show model k=3 real examples of that protein
    3. Generate N recipe candidates
    4. Score candidates with critic
    5. Measure recall vs. known-good formulations
    6. Measure calibration (predicted stability vs. real)
    7. Measure diversity (recipe variety)
- **Estimated time:** 2-3 days
- **Output:** Results table (per-protein metrics + aggregate mean/std)

**Success criteria:**
```
Per-protein results saved to: evaluation/results/lopo_results_SEED_TIMESTAMP.json
Metrics: recall@5, recall@10, spearman_r, mae, diversity
All metrics computed for all proteins in BioFormBench
```

---

### **PHASE 2: RIGOR (1 week) — MUST-DO**

Run proper experiments with multiple seeds and ablations. Reviewers demand error bars.

#### 2.1 Multi-Seed Evaluation
- **Goal:** Run LOPO evaluation with seeds [42, 123, 456, 789, 999]
- **Process:** For each seed:
  1. Re-generate synthetic training data
  2. Train model from scratch
  3. Run full LOPO evaluation
  4. Save results
- **Estimated time:** 3-4 days (parallel runs)
- **Output:** Results per seed, compute mean ± std for all metrics

**Success criteria:**
```
lopo_results_seed_42.json
lopo_results_seed_123.json
lopo_results_seed_456.json
...
Mean recall@5: 0.65 ± 0.08
Mean spearman_r: 0.58 ± 0.12
```

#### 2.2 Ablation Studies
- **Goal:** Prove architecture choices matter
- **Run these:**

| Ablation | What to change | Expected impact |
|----------|---|---|
| **No critic** | Remove critic scoring, use model directly | Baseline |
| **No in-context** | Train only on synthetic, no real examples at test | Isolated in-context value |
| **Smaller critic** | 2 layers instead of 3 | Justify critic size |
| **Baseline: RF/SVM/MLP** | Already implemented | Predictive comparison |
| **Baseline: Simulator-only** | Direct simulator scoring (no critic) | Justify critic distillation |
| **Few-shot sensitivity** | Test k=1, 3, 5, 10 real examples | Robustness |

- **Estimated time:** 2-3 days
- **Output:** Ablation table (all configs × metrics)

**Success criteria:**
```
Table: Ablation Study Results
Configuration          Recall@5  Spearman_r  Diversity
Base (full system)     0.68      0.62        0.71
- No critic            0.52      0.48        0.68  ← critic helps
- No in-context        0.48      0.44        0.65  ← in-context helps
Baseline: RF            0.35      0.28        —
Baseline: Simulator     0.61      0.57        —     ← critic adds value
```

#### 2.3 Hyperparameter Justification
- **Goal:** Show hyperparameter choices are reasonable
- **Option A (preferred):** Brief grid search on 2-3 key params
  - hidden_dim: [128, 256, 512]
  - num_layers: [4, 6, 8]
  - Report which performed best
- **Option B (minimum):** Document why each choice was made
  - "hidden_dim=256: balance between expressiveness and 3050 memory (55MB checkpoint)"
  - "num_layers=6: empirically stable, no divergence"
  - "num_heads=8: maintains dimensionality (256/8=32 per head)"
- **Estimated time:** 1 day (Option B) or 2-3 days (Option A)

---

### **PHASE 3: POLISH (3-5 days) — SHOULD-DO**

Make paper-ready documentation and error analysis. These won't change rejection/acceptance alone but strengthen the story.

#### 3.1 Enhanced Documentation
- **Add to each class/function:**
  - What it does (purpose)
  - Why it exists (motivation)
  - Key design decisions and alternatives
  - Known limitations
- **Example:**
  ```python
  class FormulationCritic(nn.Module):
      """
      Lightweight critic for scoring formulation recipes.
      
      PURPOSE:
      Distilled from mechanistic simulator to enable fast inference-time
      scoring during best-of-N decoding or DPO preference optimization.
      
      WHY NOT use simulator directly?
      - Simulator is 100x slower (scipy/numba overhead)
      - Critic is differentiable (enables DPO backprop)
      - Critic can be calibrated to real BioFormBench data
      
      DESIGN CHOICES:
      - Transformer instead of MLP: captures token dependencies
      - 4 heads: enough for multi-aspect scoring (charge, hydrophobic, etc.)
      - 3 layers: 2 were insufficient, 4+ showed no improvement
      - Sigmoid output: ensures stability score in [0, 1]
      
      LIMITATIONS:
      - Only validated on proteins in BioFormBench
      - Sensitive to out-of-distribution formulation tokens
      - Requires synthetic pretraining (no cold-start from scratch)
      """
  ```
- **Estimated time:** 1-2 days

#### 3.2 Error Analysis
- **Goal:** Understand failure modes
- **Process:**
  1. Collect all (protein, predicted_recipe, actual_best_recipe) triples
  2. Find cases where model ranked actual_best low (failure cases)
  3. Analyze patterns:
     - Did model predict low stability but real outcome was high?
     - Were exotic stabilizers involved?
     - Extreme pH or salt?
     - Specific protein types (His-tags, PTMs, etc.)?
  4. Qualitative discussion of 3-5 failure cases
- **Estimated time:** 1 day

#### 3.3 Ethics & Limitations Section
- **Add to paper:**
  - Dual-use concerns: generated recipes are computational hypotheses, not clinical recommendations
  - No wet-lab validation: outputs should be experimentally screened
  - Simulator limitations: based on heuristics, not exhaustive physics
  - Data bias: BioFormBench is literature-mined, may over-represent published successes
  - Generalization: evaluated only on proteins with ~5-10 formulations; performance on under-studied proteins unknown
- **Estimated time:** < 1 day

---

## 📅 Timeline

### Aggressive Schedule (3 weeks)
```
Week 1:
  Mon-Wed: Collect BioFormBench (3 days)
  Thu-Fri: Validate simulator (2 days)
  
Week 2:
  Mon-Tue: Implement LOPO evaluation (2 days)
  Wed-Fri: Multi-seed runs (3 days)
  
Week 3:
  Mon-Wed: Ablation studies (3 days)
  Thu-Fri: Documentation + error analysis (2 days)
  
Week 4:
  Paper writing + submission prep
```

### Conservative Schedule (4-5 weeks)
```
Week 1: BioFormBench collection + validation
Week 2: Simulator validation + initial LOPO
Week 3: Multi-seed runs + ablations
Week 4: Hyperparameter justification + documentation
Week 5: Error analysis + paper prep
```

---

## 🚨 Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|---|---|
| **BioFormBench too small** (<20 proteins) | Medium | Start literature search immediately; have backup sources |
| **Simulator correlation poor** (<0.4) | Low | Investigate: tuning simulator parameters, adding more heuristics |
| **Model doesn't beat RF baseline** | Low | Indicates architecture problem; debug first before ablations |
| **LOPO results noisy** (high std) | Medium | Collect more BioFormBench data; use more seeds |
| **No time for Phase 3** | Low | Do Phase 1-2 only, mention improvements for future work |

---

## ✅ Final Checklist Before Submission

- [ ] **Phase 1 done:**
  - [ ] BioFormBench.csv with ≥20 rows, ≥5 proteins
  - [ ] Simulator validated against real data (r > 0.5)
  - [ ] LOPO evaluation implemented and run (5 seeds)
  
- [ ] **Phase 2 done:**
  - [ ] Mean ± std reported for all metrics
  - [ ] Ablation table complete (all 6 configs)
  - [ ] At least one significant ablation showing model component matters
  
- [ ] **Phase 3 done (ideal):**
  - [ ] Function docstrings comprehensive
  - [ ] Error analysis with 3-5 failure cases
  - [ ] Ethics section in paper
  
- [ ] **Code quality:**
  - [ ] All 84 tests still passing
  - [ ] Reproducibility: can reproduce results with seed + requirements.txt
  - [ ] No TODOs in submitted code
  
- [ ] **Paper quality:**
  - [ ] Novel contribution clearly articulated (not just "we built this")
  - [ ] Comparison to related work (AICMET, ExPreSo, SMolLM, etc.)
  - [ ] Limitations honestly discussed
  - [ ] Figures/tables from evaluation

---

## 💡 Key Insight

**Current state:** "Well-organized engineering project"  
**After Phase 1:** "Validated system that works"  
**After Phase 2:** "Rigorous research contribution"  
**After Phase 3:** "Publication-ready manuscript"

The difference between rejection and acceptance is **validation**. Reviewers don't care how clean the code is if it doesn't actually work on real data.

Priority: **Phase 1 > Phase 2 >> Phase 3**

---

## 🎯 Recommended Venue Strategy

### If targeting **NeurIPS/ICML/ICLR main track:**
- Must complete Phase 1 + 2 fully
- Need strong novelty narrative (not "transformer on formulations")
- 18-month timeline realistic for solo researcher

### If targeting **NeurIPS AI4DD workshop** (or similar):
- Phase 1 sufficient
- Can show preliminary Phase 2 results
- 6-8 week timeline realistic
- Good stepping stone to main conference

### If targeting **Datasets & Benchmarks track:**
- Focus on BioFormBench curation as main contribution
- Phase 1 only (high-quality dataset + loader)
- Position as resource paper

**Recommendation:** Start with **NeurIPS AI4DD workshop** as primary target + main track as stretch goal. Workshop paper in 4 weeks → main track camera-ready in 6 months.
