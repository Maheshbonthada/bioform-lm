---
dataset_info:
  - config_name: bioformbench_real
    features:
      - name: protein_id
        dtype: string
        description: Protein identifier (traceable to source_id)
      - name: protein_mw_kda
        dtype: float32
        description: Molecular weight (kDa)
      - name: protein_pi
        dtype: float32
        description: Isoelectric point
      - name: protein_tm_baseline_c
        dtype: float32
        description: Baseline melting temperature (C), no stabilizer
      - name: buffer_species
        dtype: string
        description: Buffer chemical
      - name: buffer_conc_mm
        dtype: float32
        description: Buffer concentration (mM)
      - name: ph
        dtype: float32
        description: Formulation pH
      - name: ionic_strength_mm
        dtype: float32
        description: Ionic strength (mM)
      - name: osmolarity_mosm_kg
        dtype: float32
        description: Osmolarity (mOsm/kg)
      - name: stabilizers_json
        dtype: string
        description: JSON dict of stabilizer name to concentration
      - name: temperature_c
        dtype: float32
        description: Storage/measurement temperature (C)
      - name: stability_score
        dtype: float32
        description: Normalized stability outcome, 0-1, higher = more stable
      - name: measured_aggregation_percent
        dtype: float32
        description: SEC percent aggregation, where reported
      - name: measured_tm_shift_c
        dtype: float32
        description: DSF Tm shift versus baseline, where reported
      - name: source_title
        dtype: string
        description: Title of the primary literature source (required; unsourced rows are excluded, see Data Integrity)
      - name: source_id
        dtype: string
        description: PubMed Central identifier of the primary source
    splits:
      - name: full
        num_examples: 49
  - config_name: bioformbench_marketed
    features:
      - name: inn
        dtype: string
        description: Antibody International Nonproprietary Name
      - name: title
        dtype: string
        description: FDA label title (product name, manufacturer)
      - name: ph
        dtype: float32
        description: Formulation pH parsed from the label
      - name: buffer_species
        dtype: string
        description: Buffer chemical, where fully resolved
      - name: buffer_conc_mm
        dtype: float32
        description: Buffer concentration (mM), where fully resolved
      - name: surfactant
        dtype: string
        description: Surfactant identity, where present
      - name: fv_pi
        dtype: float32
        description: Isoelectric point computed from the VH+VL Fv sequence (Biopython ProtParam)
      - name: fv_mw_kda
        dtype: float32
        description: Fv molecular weight computed from sequence
      - name: source_text
        dtype: string
        description: Verbatim label sentence(s) the row was parsed from
    splits:
      - name: full
        num_examples: 165
license: cc-by-4.0
---

# BioFormBench: Two Open Benchmarks for Biologics Formulation Research

This release contains **two** datasets, kept separate because they answer different
questions and neither should be read as a substitute for the other.

## Data integrity note (please read before using either dataset)

An earlier internal draft of BioFormBench-Real contained 67 rows. Auditing
`source_title`/`source_id` provenance found that **18 of those rows had no
citation** and used placeholder identifiers (`protein_1`–`protein_5`) with
round, unverified descriptors (50.0 kDa / pI 7.2 / Tm 65.0 C) repeated across
otherwise-different molecules. Those rows have been **removed**. The 49 rows in
this release all trace to a PubMed Central ID and were checked against their
source text.

A second, subtler defect was found afterward in how "one protein" is defined
for leave-one-protein-out evaluation: a (molecular weight, pI)-string grouping
silently merged up to **4 different real antibodies** (Trastuzumab, Omalizumab,
and two others) into a single fake pooled protein wherever their placeholder
pI values collided at ≈7.2. This release adds a `real_protein_id` column
(derived from each row's literature source, independent of any descriptor
value) and corrects pI for 5 of 13 proteins where an independent source could
be found (Trastuzumab 7.2→9.03; Omalizumab 7.2→5.79; Adalimumab 7.2→8.5; a
TUR01/adalimumab-biosimilar row 7.3→8.5; a bispecific stated directly in its
source paper, 6.9→8.52). One protein (mAb2) has no independently obtainable
value and keeps its placeholder, flagged via `pi_corrected=False`. Always group
by `real_protein_id`, not by (MW, pI), for any protein-identity-sensitive
analysis. If you have a copy of the 67-row file or a version without
`real_protein_id`, discard it and use this one.

## 1. BioFormBench-Real (49 rows, 13 proteins)

Literature-mined formulation-outcome measurements (DSF Tm-shift, SEC %
aggregation, turbidity) for 13 real proteins across 11 primary papers, each row
traceable to its source. This is the dataset to use for any claim about
*stability-optimal* formulation, but at n=13 proteins (9 with enough
per-protein data for leave-one-protein-out evaluation) it is underpowered for a
definitive protein-conditionality verdict — see the companion paper's
Discussion for what scaling this further would require.

## 2. BioFormBench-Marketed (165 rows, 80 antibodies) — new in this release

165 formulation presentations for 80 FDA-approved antibody therapeutics,
deterministically parsed from FDA Structured Product Labeling (DailyMed) and
linked to real VH/VL variable-domain sequences from Thera-SAbDab. Every parsed
field keeps its verbatim source sentence (`source_text`) for audit. To our
knowledge this is the first open dataset connecting therapeutic antibody
sequence to marketed formulation composition at this scale.

This dataset encodes **what was chosen** for an approved product, not what is
necessarily stability-optimal — marketed choices are also shaped by
manufacturability, prior platform investment and regulatory precedent. Used at
full sample size (n=80) with proper multiple-comparison correction and
leave-one-protein-out validation, protein sequence identity does **not**
detectably predict the chosen pH or buffer beyond a constant "platform"
baseline (all sign-flip p > 0.8) — see the companion paper for the full
statistical analysis, including a worked example of how a naive n=27
subsample of this same data produces a spurious, non-reproducible positive
result (Spearman rho=-0.464, p=0.015, uncorrected) that a full-sample,
corrected, out-of-sample analysis overturns.

## Use cases

1. Test protein-conditional formulation hypotheses at adequate statistical
   power, with the selection-artifact and platform-baseline results in the
   companion paper as a required comparison point, not merely a possible one.
2. Train/evaluate predictive or generative formulation models against a
   documented platform baseline rather than only random/uniform baselines.
3. Audit other mechanistic formulation simulators using the diagnostic
   described in the companion paper (dead-slot spread, interior-argmax
   fraction) against these real formulations.
4. Sequence-to-formulation representation learning (BioFormBench-Marketed
   includes Fv-derived descriptors so no additional sequence processing is
   required to get started).

## Files

- `bioformbench_real.csv` — 49 rows, BioFormBench-Real (see schema above).
- `bioformbench_marketed.csv` — 165 rows, BioFormBench-Marketed (see schema
  above; full computed-descriptor and label-parse columns included).

## Known limitations

- BioFormBench-Real: n=13 proteins (9 LOPO-eligible) is small; treat any
  per-protein result as illustrative, and prefer the aggregate statistics with
  their reported confidence intervals.
- BioFormBench-Marketed: pH is extracted with a confidence flag
  (`ph_is_range`/composition-sentence provenance in the full release columns);
  the low-confidence stratum is retained rather than silently dropped, and the
  companion paper shows the main finding (no sequence effect) holds in the
  high-confidence stratum alone. Only 27–28 of 80 molecules have a fully
  resolved buffer species *and* concentration; buffer-level analyses should
  use that subset and are correspondingly lower-powered.
- Neither dataset should be used to generate or select actual formulations for
  laboratory or clinical use without independent verification; see the
  companion paper's Ethics statement.

## Citation

```bibtex
@dataset{kumar2026bioformbench,
  title={BioFormBench: Two Open Benchmarks for Biologics Formulation Research},
  author={Kumar, Bonthada Sravan},
  year={2026},
  publisher={Hugging Face Datasets},
  url={https://huggingface.co/datasets/Sravankumarbonthada/BioFormBench}
}
```

## Sources

BioFormBench-Marketed is built from public FDA Structured Product Labeling
(DailyMed) and Thera-SAbDab (Raybould et al., Nucleic Acids Research 2020).
BioFormBench-Real is mined from 11 open-access PubMed Central articles, each
cited per-row via `source_id`.

## Contact

Bonthada Sravan Kumar — sravansaijohn@gmail.com — issues via GitHub
(Maheshbonthada/bioform-lm)

## License

CC-BY-4.0

---

**Last updated:** September 8, 2026
