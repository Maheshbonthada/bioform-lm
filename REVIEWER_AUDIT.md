# 20-Reviewer Research Code Audit

*How NeurIPS/ICML/ICLR reviewers would critique BioForm-LM*

---

## 🔴 **CRITICAL ISSUES** (Show-stoppers)

### 1. **No Real Data Evaluation** ⚠️
- **Reviewer says:** "You trained on synthetic data only. BioFormBench exists but is never used to validate the model. How do you know this actually works?"
- **Current state:** `scripts/evaluate.py` is a placeholder
- **Fix needed:** Implement actual LOPO CV evaluation on BioFormBench
- **Impact:** Without this, paper is just "we trained a transformer on synthetic data" — not novel enough

### 2. **Critic Circular Training** ⚠️
- **Reviewer says:** "You distill the critic from the mechanistic simulator, then use the critic to guide generation. Isn't the critic just learning simulator artifacts? How is this better than using the simulator directly?"
- **Current state:** Critic trained on simulator outputs → uses critic to score generated recipes → prefer critic scores
- **Question:** Is critic actually learning meaningful stability patterns or just memorizing simulator bias?
- **Fix needed:** 
  - Validate critic against real stability data (BioFormBench)
  - Show critic adds value over baseline (bare model + simulator scoring)
  - Ablation: compare critic-guided vs simulator-direct scoring

### 3. **No Comparison to Domain Baselines** ⚠️
- **Reviewer says:** "You compare to RF/SVM/MLP on features, but the real baseline is ExPreSo, FormulationDE, or actual formulation software. Do those even exist as open-source? If not, why not implement them?"
- **Current state:** Only predictive baselines (no domain-specific formulation design tools)
- **Fix needed:** 
  - Research: are ExPreSo/FormulationDE open-source?
  - If yes: implement as baseline
  - If no: cite and discuss why comparison is infeasible

### 4. **Simulator Validation Missing** ⚠️
- **Reviewer says:** "Your mechanistic simulator combines DLVO + Lumry-Eyring + heuristics. Have you validated this against published data? What's the error rate?"
- **Current state:** `simulator/mechanistic_sim.py` exists but no validation vs. real lab data
- **Question:** Is the simulator even accurate enough to be useful for training?
- **Fix needed:**
  - Validate simulator predictions against published DSF/SEC data from 5-10 proteins
  - Report RMSE/correlation vs. real outcomes
  - Sensitivity analysis: which parameters matter most?

### 5. **Statistical Rigor Missing** ⚠️
- **Reviewer says:** "You show one training run with one seed. LOPO has one test set per protein. No error bars, confidence intervals, or significance tests. How do I know results aren't noise?"
- **Current state:** Tests pass but only on random synthetic data
- **Fix needed:**
  - Multiple random seeds (3-5 minimum)
  - Report mean ± std on LOPO folds
  - Significance testing (t-test between baselines)
  - Per-protein results + aggregate

---

## 🟡 **MAJOR CONCERNS** (Likely rejection if unfixed)

### 6. **Tokenization Not Validated**
- **Issue:** Formulation→tokens→model. How sensitive are results to tokenization choices?
- **Missing:** Ablation on vocabulary size, quantization granularity, sequence length
- **Fix:** Show robustness to tokenization variants

### 7. **Hyperparameter Search Not Documented**
- **Issue:** Model has 8+ hyperparams (hidden_dim=256, num_layers=6, etc.). Were these swept or hand-tuned?
- **Missing:** Justify or show ablation
- **Fix:** Ablation study on hidden_dim, num_layers, learning_rate

### 8. **Baseline Unfairness**
- **Issue:** RF/SVM/MLP train on 10-dim feature vectors extracted differently than the generative model ingests data
- **Reviewer:** "You're comparing apples (low-dim features) to oranges (high-dim sequences). Make baselines use the same tokenized input."
- **Fix:** Create fair baseline that operates on tokenized sequences (e.g., "predict next stability token")

### 9. **Generalization Not Proven**
- **Issue:** All experiments are on synthetic data or literature-mined small dataset
- **Question:** Will this work on proteins outside the literature? On new buffer systems?
- **Fix:** LOPO + diversity analysis. Show model generalizes to unseen proteins

### 10. **No Ablation on Critic Design**
- **Issue:** FormulationCritic has specific architecture (4 heads, 3 layers, 64-32-1 scoring head). Why?
- **Missing:** Ablation on nhead, num_layers, hidden_dim
- **Fix:** Show critic architecture choices matter

### 11. **Evaluation Metrics Not Justified**
- **Reviewer:** "Why top-k recall? Why Spearman? Why not task-specific metrics like 'did this formulation actually stabilize the protein?'"
- **Issue:** Metrics borrowed from molecule/protein generation, not validated for formulations
- **Fix:** Justify each metric choice or add domain-specific ones

### 12. **Literature Mining (BioFormBench) Not Documented**
- **Issue:** The dataset doesn't exist yet. How will you collect it? What are inclusion criteria? Quality control?
- **Reviewer:** "Without seeing the data curation process, I can't assess evaluation validity."
- **Fix:** Protocol document: sources, inclusion/exclusion, inter-rater agreement, schema validation

---

## 🟡 **MODERATE CONCERNS** (Fixable, expected in submission)

### 13. **No Reproducibility Statement**
- **Missing:** "Code/data will be released at [URL]. Results reproducible with seed=42 + requirements.txt."
- **Fix:** Add to paper + repo README

### 14. **Limited Docstring Coverage**
- **Issue:** Functions have 1-line docstrings, no argument descriptions
- **Example:** `Trainer.train()` has no docstring explaining return value, side effects, exceptions
- **Fix:** Add comprehensive docstrings (Args, Returns, Raises, Examples)

### 15. **No Configuration Version Control**
- **Issue:** `config.py` hardcoded values. If you change them, old results aren't reproducible
- **Fix:** Snapshot config to JSON at training time (`experiments/config_snapshot_TIMESTAMP.json`)

### 16. **Few-Shot Evaluation Not Ablated**
- **Issue:** LOPO gives model k=3 real examples. Did you test k=1, k=5, k=10? How sensitive are results?
- **Fix:** Ablation table showing performance vs. k

### 17. **No Error Analysis**
- **Missing:** "What formulations does the model fail on? Why?"
- **Examples:** "High-salt proteins", "Non-standard stabilizers", "Extreme pH"
- **Fix:** Qualitative analysis of failure modes

### 18. **Scalability Claims Unsubstantiated**
- **Claim (implicit):** "Works on RTX 3050"
- **Reality:** Tested on 1K-100K synthetic samples, tiny model
- **Question:** What about 1M samples? Larger model?
- **Fix:** Scaling experiments or be more conservative in claims

### 19. **Ethical Considerations Absent**
- **Issue:** Generative formulation design could be misused (bioweapons, dangerous stabilizers)
- **Missing:** Discussion of dual-use, safety mitigations, responsible release
- **Fix:** Add ethics section to paper

### 20. **Missing Negative Results**
- **Issue:** All experiments show your method working. Did anything fail? (e.g., "critic didn't help", "in-context learning didn't matter")
- **Reviewer:** "Cherry-picked results. What didn't work?"
- **Fix:** Document ablations that didn't improve performance

---

## 📋 **CHECKLIST FOR PUBLICATION-READY CODE**

### Reproducibility
- [ ] README with exact reproduction steps
- [ ] Requirements.txt with pinned versions
- [ ] Seed management (comment showing all random seeds used)
- [ ] Config snapshot saved during training
- [ ] Training logs saved to file

**Current status:**
- ✓ Requirements.txt exists
- ✗ Seed snapshots not saved
- ⚠️ README incomplete (no end-to-end instructions)

### Testing
- [ ] Unit tests for all classes (>80% coverage)
- [ ] Integration tests (simulator→training→evaluation pipeline)
- [ ] No test data leakage
- [ ] Edge case testing (empty inputs, single sample, etc.)

**Current status:**
- ✓ 84 tests for simulator, evaluation, baselines, critic
- ✓ Edge cases covered
- ✗ Integration tests missing (end-to-end pipeline not tested)
- ✗ No coverage metrics

### Documentation
- [ ] Module-level docstrings explaining purpose
- [ ] Class docstrings with architecture description
- [ ] Function docstrings (Args, Returns, Raises, Examples)
- [ ] Design decisions documented (why these choices?)
- [ ] Common pitfalls noted

**Current status:**
- ✓ Module docstrings present
- ⚠️ Function docstrings sparse
- ✗ Design decisions not explained
- ✗ Pitfalls not documented

### Code Quality
- [ ] Type hints complete (mypy --strict passing)
- [ ] Linting clean (black, isort, flake8)
- [ ] No hardcoded paths (all relative to PROJECT_ROOT)
- [ ] Error messages informative
- [ ] No TODO comments in submitted code

**Current status:**
- ⚠️ Type hints present but incomplete (Dict not imported in train.py before)
- ✓ Linting configured in Makefile
- ✓ Relative paths used
- ⚠️ Some TODO comments exist (e.g., "TODO: add recipe generation as auxiliary task")

### Experiments
- [ ] Ablation studies comprehensive
- [ ] Baseline comparisons fair and well-documented
- [ ] Statistical significance reported
- [ ] Hyperparameter search documented
- [ ] Training curves shown (loss, validation loss)
- [ ] Error bars on all metrics

**Current status:**
- ✗ No ablations yet (evaluation not implemented)
- ⚠️ Baselines exist but fairness questionable
- ✗ No statistical testing
- ✗ Hyperparameter search not documented
- ✗ Training curves not saved/reported

### Data Handling
- [ ] Data versioning (hash or DOI)
- [ ] Schema validation (columns, types, ranges)
- [ ] Handling of missing values documented
- [ ] No data leakage between splits
- [ ] Audit trail of data transformations

**Current status:**
- ✗ BioFormBench not yet collected
- ✓ Synthetic data has clear schema
- ⚠️ No validation code (should check CSV schema before loading)
- ✓ No leakage (LOPO protocol is sound)

---

## 🎯 **PRIORITY FIXES FOR SUBMISSION**

### Tier 1: Must-fix (without these, rejection likely)
1. **Implement BioFormBench evaluation** — at least 20-30 curated data points from literature
2. **Validate simulator against real data** — show correlation with published results
3. **Add statistical rigor** — multiple seeds, error bars, significance tests
4. **Fair baseline comparison** — use same tokenized input space

### Tier 2: Should-fix (strengthens paper significantly)
5. **Ablation on critic design** — why this architecture?
6. **Ablation on tokenization** — sensitivity analysis
7. **Few-shot sensitivity** — how many real examples needed?
8. **Error analysis** — what fails and why?

### Tier 3: Nice-to-have (polish, not critical)
9. **Scaling experiments** — how does performance scale with model/data size?
10. **Hyperparameter ablations** — justify key choices
11. **Ethics discussion** — dual-use considerations
12. **Enhanced documentation** — design decision rationales

---

## 💬 **Typical Reviewer Comments**

**Reviewer A (Methods):**
> "The architecture is straightforward but lacks novelty. Why is this better than training a standard LM on formulation sequences without the critic? The circular dependency (critic trained on simulator, simulator used as oracle) is concerning."

**Reviewer B (Experiments):**
> "Results shown only on synthetic data. The 'real' evaluation (BioFormBench) isn't yet done. Cannot assess generalization without it."

**Reviewer C (Reproducibility):**
> "Training details missing. What optimizer settings? Learning rate schedule? How many epochs before early stopping? I'd need significant effort to reproduce."

**Reviewer D (Comparison):**
> "The RF/SVM/MLP baselines are unfairly weak. They use hand-crafted features instead of end-to-end learned representations. This makes the generative model look better than it probably is."

**Reviewer E (Clarity):**
> "The paper conflates 'generative model' with 'critic-guided search.' It's not clear whether performance gains come from generation or critic ranking."

**Reviewer F (Significance):**
> "The problem is niche (biologics formulation) and the solution, while competent, isn't sufficiently novel for a top venue. This reads more like a strong domain application paper than a methods paper."

---

## ✅ **WHAT'S GOOD**

Despite the above, the codebase *does* have real strengths:

✅ **Organized structure** — clear separation: simulator, tokenizer, model, training, evaluation  
✅ **Comprehensive testing** — 84 tests, edge cases covered  
✅ **Reproducibility infrastructure** — checkpoints, logging, config  
✅ **Ablation harnesses ready** — no-critic, no-in-context ablations defined  
✅ **Documentation mindset** — README, guides, docstrings exist  
✅ **Production code** — no notebooks, no technical debt visible  

These make it *implementable*. The critical gap is **validation**: proving the system works on real data and that the architecture choices matter.

---

## 🚀 **Path to Acceptance**

1. ✅ **Code: Done** (structure, testing, infrastructure solid)
2. ⏳ **Data: Pending** (collect BioFormBench, ~20-50 curated formulations)
3. ⏳ **Validation: Pending** (run LOPO evaluation, show real-world generalization)
4. ⏳ **Analysis: Pending** (ablations, error analysis, statistical rigor)
5. ⏳ **Paper: Pending** (clear novelty narrative, not just "we built this")

**Estimated effort to address Tier 1 issues:** 1-2 weeks  
**Estimated effort to address Tier 1 + Tier 2:** 2-4 weeks

After that: submission-ready, but acceptance depends on (a) BioFormBench quality and (b) actual performance gains on real data.

---

## 💡 **Bottom Line**

**What reviewers will say:**

> "This is competent engineering. The code is well-organized, tests pass, and the idea is sensible. However, it's not yet ready for publication because:
> 1. No real-world validation (BioFormBench promised but not done)
> 2. No proof the architecture choices matter (ablations incomplete)
> 3. Unfair baselines (comparing to weak predictive models)
> 4. Circular critic dependency (trained on simulator, evaluated on simulator)
>
> The paper reads like a technical report on a well-executed but unvalidated system, not a research contribution. Resubmit once you've (a) collected real data, (b) run rigorous LOPO evaluation, (c) ablated architecture choices, and (d) proven generalization to unseen proteins."

**Recommendation:** **Borderline to Weak Reject** — fixable, but needs validation work first.
