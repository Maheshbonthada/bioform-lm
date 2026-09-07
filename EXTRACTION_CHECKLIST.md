# BioFormBench Extraction Checklist

**Use this for each paper you mine.**

---

## Paper Information
- [ ] Paper title: ___________________________
- [ ] DOI/Source: ___________________________
- [ ] Year: _____
- [ ] Table(s) location: ___________________________

---

## For Each Formulation Extracted

### ✅ Protein Information
- [ ] Protein ID/name (e.g., "huIgG1_from_SmithEtAl2020"): _______________
- [ ] Molecular weight (kDa): _____
- [ ] Isoelectric point (pI): _____ (OK to leave blank if not in paper)
- [ ] Baseline Tm (°C) *without additives*: _____ (OK to leave blank if not available)

### ✅ Formulation (Recipe)
- [ ] Buffer species (phosphate, histidine, citrate, acetate, maleate): _______________
- [ ] Buffer concentration (mM): _____
- [ ] pH: _____
- [ ] Ionic strength (mM): _____ 
  - *Note: If not directly given, calculate from NaCl/KCl conc., or ask paper's methods*
- [ ] Osmolarity (mOsm/kg): _____ (optional, use if given)

### ✅ Excipients/Stabilizers
**Format:** `{"trehalose": 50, "tween80": 0.01}`

- [ ] Osmolyte 1 name: ____________ Conc (mM): _____
- [ ] Osmolyte 2 name: ____________ Conc (mM): _____
- [ ] Surfactant name: ____________ Conc (% w/v or mM): _____
- [ ] Other additives: ___________________________

**Conversion tips:**
- Trehalose (MW 342): 100 mg/mL = 292 mM
- Sucrose (MW 342): 100 mg/mL = 292 mM
- Sorbitol (MW 182): 100 mg/mL = 549 mM
- Glycerol (MW 92): 10% w/v = ~1087 mM (but often reported as % w/v, not mM)
- Polysorbate80/Tween80 (MW 1310): 0.01% w/v = 0.076 mM

### ✅ Storage Condition
- [ ] Temperature (°C): _____ (e.g., 4, 25, 37)
- [ ] Time point (if multiple): _____ (e.g., "4 weeks at 25°C")

### ✅ Stability Outcome
- [ ] Aggregation % (from SEC, DLS, or turbidity): _____
  - *Source (which method):* _______________
  - *Note:* 1-5% is excellent; 5-10% is good; >15% is poor
  
- [ ] Tm shift (ΔTm, °C): _____ (vs. baseline without excipients)
  - *Source (DSF, DSC):* _______________
  - *Note:* OK to leave blank if not reported

### ✅ Metadata
- [ ] Confidence level: [ ] HIGH  [ ] MEDIUM  [ ] LOW
  - HIGH = All fields directly in table
  - MEDIUM = Some interpolated from figure or methods
  - LOW = Calculated/inferred (use sparingly)
  
- [ ] Notes / Special conditions: ___________________________

---

## Quality Checks Before Adding to CSV

For each row, verify:

- [ ] Protein MW is 20-200 kDa (biological proteins)
- [ ] pH is 3.0-8.5 (biologics typical range)
- [ ] Ionic strength is 50-300 mM (physiological ~ 150)
- [ ] Stabilizer concentrations are plausible:
  - Disaccharides (trehalose, sucrose): 50-300 mM typical
  - Polyols (sorbitol, glycerol): 50-1000 mM typical
  - Surfactants (Tween, Polysorbate): 0.001-0.1% w/v typical
- [ ] Aggregation % is 0-100
- [ ] Tm shift is -5 to +20°C (reasonable stabilizer effect)
- [ ] Protein ID is unique (no duplicates from same paper)

---

## Computing stability_score

**Rule:** `stability_score = max(0, 1 - 0.01 * aggregation_percent)`

| Aggregation % | stability_score |
|---|---|
| 1% | 0.99 |
| 5% | 0.95 |
| 10% | 0.90 |
| 15% | 0.85 |
| 20% | 0.80 |
| 30% | 0.70 |

---

## Template Row (Copy & Fill)

```
protein_id,protein_mw_kda,protein_pi,protein_tm_baseline_c,buffer_species,buffer_conc_mm,ph,ionic_strength_mm,osmolarity_mosm_kg,stabilizers_json,temperature_c,stability_score,measured_aggregation_percent,measured_tm_shift_c

[YourProteinID_FromPaper],150.0,7.2,61.5,phosphate,20.0,7.0,150.0,300.0,"{""trehalose"": 100.0, ""tween80"": 0.01}",25.0,0.95,5.0,10.0
```

---

## Example Filled Row

From hypothetical paper "Smith et al. 2020, Table 2, IgG formulation screening":

```
protein_id: IgG_huIgG1_SmithEtAl2020
protein_mw_kda: 150.0
protein_pi: 7.2
protein_tm_baseline_c: 61.5
buffer_species: phosphate
buffer_conc_mm: 20.0
ph: 7.0
ionic_strength_mm: 150.0
osmolarity_mosm_kg: 300.0
stabilizers_json: {"trehalose": 100.0, "polysorbate80": 0.01}
temperature_c: 25.0
stability_score: 0.95
measured_aggregation_percent: 5.0
measured_tm_shift_c: 10.0
```

---

## Submission Format

Once you have 8-10 rows extracted, paste into Excel/Google Sheets or directly into CSV:

**File:** `data/bioformbench_extracted_[YourInitials]_[PaperYear].csv`

**Then run validation:**
```bash
python scripts/validate_extraction.py data/bioformbench_extracted_*.csv
```

---

## Common Mistakes to Avoid

❌ **WRONG:** Mixing units (some mM, some % w/v)  
✅ **RIGHT:** Convert everything to mM for osmolytes, % w/v for surfactants

❌ **WRONG:** Reporting negative aggregation or >100%  
✅ **RIGHT:** Clip to [0, 100] range; verify with paper

❌ **WRONG:** Leaving protein MW as 0 or unrealistic (>300 kDa)  
✅ **RIGHT:** Cross-check with PubMed/UniProt if unsure

❌ **WRONG:** Tm shift without knowing baseline Tm (can't calibrate)  
✅ **RIGHT:** Skip Tm shift if baseline not available; extraction can handle missing values

❌ **WRONG:** Mixing storage conditions (e.g., 1 week at 4°C vs. 4 weeks at 25°C in same row)  
✅ **RIGHT:** Each row = one condition; if paper tests multiple time points, create separate rows per time point

---

## When in Doubt

- **Leave fields blank** if not in paper (OK for pH, osmolarity, pI)
- **Mark confidence_level as LOW** if you had to infer
- **Add notes** explaining any calculations

Better to have 80% complete high-confidence rows than 100% complete guesses.

---

**Good luck! Expected yield: 30-40 rows from 3-5 papers.**
