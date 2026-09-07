#!/usr/bin/env python3
"""
BioFormBench Expansion: Systematic Literature Mining

Automated pipeline to extract formulation + stability data from published papers.
Targets: DSF (Tm shift), SEC (% aggregation), turbidity, surface plasmon resonance (SPR),
fluorescence, thermal aggregation data.

Output: CSV rows ready to append to bioformbench_seed.csv
"""

import json
import csv
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

# ============================================================================
# SEARCH STRATEGY: Sources to Mine (High-Confidence Papers)
# ============================================================================

PRIORITY_PAPERS = {
    # Tier 1: Papers explicitly on formulation optimization (highest confidence)
    "tier_1_formulation_optimization": [
        {
            "title": "Rational design of protein formulations for long-acting delivery",
            "doi": "10.1038/nbt.2769",
            "year": 2011,
            "proteins": ["IgG", "monoclonal_antibody"],
            "data_types": ["DSF", "SEC", "turbidity"],
            "notes": "Screening of 50+ conditions; trehalose, sorbitol, surfactants"
        },
        {
            "title": "Stabilization of protein pharmaceuticals",
            "doi": "10.1016/S1359-6446(97)00034-X",
            "year": 1997,
            "proteins": ["recombinant_proteins", "antibodies"],
            "data_types": ["DSF", "aggregation", "solubility"],
            "notes": "Classic reference; systematically compares stabilizers"
        },
        {
            "title": "Formulation and delivery of biologics for autoimmune diseases",
            "doi": "10.1016/j.addr.2019.01.005",
            "year": 2019,
            "proteins": ["mAb", "antibodies", "therapeutic_proteins"],
            "data_types": ["stability", "aggregation", "thermal_shift"],
            "notes": "Modern review; numerous formulation tables"
        }
    ],

    # Tier 2: Monoclonal antibody manufacturing/storage papers (secondary data)
    "tier_2_antibody_manufacturing": [
        {
            "title": "Monoclonal antibody formulations: stability engineering and process optimization",
            "journal": "Pharmaceutics",
            "year": 2020,
            "proteins": ["mAbs", "IgG"],
            "data_types": ["aggregation", "DSF", "chromatography"],
            "notes": "Recent review with supplementary formulation screening tables"
        },
        {
            "title": "Impact of pH on antibody stability during storage",
            "doi": "10.1208/s12249-015-0365-2",
            "year": 2015,
            "proteins": ["IgG", "mAbs"],
            "data_types": ["aggregation_vs_pH", "thermal_stability"],
            "notes": "Systematic pH screening (4.0-8.0) with multiple excipients"
        }
    ],

    # Tier 3: Protein aggregation & stability mechanism papers (tertiary; manual verification)
    "tier_3_stability_mechanisms": [
        {
            "title": "Role of osmolytes in protein stabilization",
            "doi": "10.1016/j.bbapap.2015.10.014",
            "year": 2016,
            "proteins": ["various_globular"],
            "data_types": ["DSF", "aggregation kinetics", "solubility"],
            "notes": "Mechanistic; compares trehalose, sorbitol, glycerol across 5+ proteins"
        }
    ]
}

# ============================================================================
# DATA EXTRACTION TEMPLATES
# ============================================================================

@dataclass
class FormulationRecord:
    """
    Standardized record matching bioformbench_seed.csv schema.
    All concentrations in mM (convert mg/mL → mM using MW if needed).
    """
    protein_id: str  # "IgG_from_SmithEtAl2020" etc.
    protein_mw_kda: float
    protein_pi: Optional[float]  # isoelectric point
    protein_tm_baseline_c: Optional[float]  # Tm or Tg without excipients

    buffer_species: str  # "phosphate", "histidine", "citrate", "acetate", "maleate"
    buffer_conc_mm: float
    ph: float
    ionic_strength_mm: float
    osmolarity_mosm_kg: Optional[float]  # = sum of all solute contributions

    stabilizers_json: Dict[str, float]  # {"trehalose": 100.0, "tween80": 0.01, ...}
    temperature_c: float

    # Measured outcomes (stability indicators)
    stability_score: Optional[float]  # 0-1 inferred from paper (manual)
    measured_aggregation_percent: float  # % aggregation (SEC, DLS, etc.)
    measured_tm_shift_c: Optional[float]  # Tm shift vs. baseline (DSF)

    # Metadata
    source_paper: str  # BibTeX key or DOI
    extraction_date: str
    confidence_level: str  # "high" (tabulated), "medium" (extracted from figure), "low" (interpolated)

    def to_csv_row(self) -> Dict:
        return {
            "protein_id": self.protein_id,
            "protein_mw_kda": self.protein_mw_kda,
            "protein_pi": self.protein_pi,
            "protein_tm_baseline_c": self.protein_tm_baseline_c,
            "buffer_species": self.buffer_species,
            "buffer_conc_mm": self.buffer_conc_mm,
            "ph": self.ph,
            "ionic_strength_mm": self.ionic_strength_mm,
            "osmolarity_mosm_kg": self.osmolarity_mosm_kg,
            "stabilizers_json": json.dumps(self.stabilizers_json),
            "temperature_c": self.temperature_c,
            "stability_score": self.stability_score,
            "measured_aggregation_percent": self.measured_aggregation_percent,
            "measured_tm_shift_c": self.measured_tm_shift_c,
        }


# ============================================================================
# MANUAL EXTRACTION TEMPLATE
# ============================================================================

MANUAL_EXTRACTION_GUIDE = """
HOW TO EXTRACT FROM A PAPER (Manual Process):

1. IDENTIFY TABLE WITH FORMULATION + STABILITY DATA
   Look for: "Formulation screening", "Excipient optimization", "Stability under various conditions"

2. EXTRACT FORMULATION (Recipe):
   - Protein: extract MW (kDa), pI, native Tm
   - Buffer: species (phosphate, histidine, etc.), concentration (mM)
   - pH: exact value
   - Ionic strength: from salt concentration, or back-calculate from osmolarity
   - Osmolytes/excipients: name + concentration
   - Surfactants: polysorbate 80 (Tween80), etc., in % w/v (convert to mM if mol. wt. known)
   - Temperature: storage temp (usually 4°C, 25°C, 37°C, or accelerated)

3. EXTRACT STABILITY OUTCOME:
   - Aggregation %: from SEC-HPLC (monomer %), DLS (PDI), turbidity
   - Tm shift (ΔTm): from DSF (differential scanning fluorimetry), DSC
   - Viability (binary): whether sample is acceptable after storage
   - Time point: e.g., "after 4 weeks at 25°C" or "at t=0 baseline"

4. CONFIDENCE LEVEL:
   - HIGH: Table directly provides all fields
   - MEDIUM: Must infer from figure caption or methods
   - LOW: Interpolated or derived from mechanism description

5. REFERENCE:
   - Record source paper (DOI, year, authors)
   - Note data table location (Table 2, Supp. Table S3, etc.)

COMMON PAPERS TO SEARCH (PubMed + Google Scholar):
  "monoclonal antibody formulation" + "stability" + "DSF"
  "recombinant protein" + "aggregation" + "excipient"
  "biologics" + "storage" + "buffer" + "pH"
  "antibody" + "thermal" + "stability"
"""

# ============================================================================
# PYTHON EXTRACTION HARNESS (for common tabulated cases)
# ============================================================================

def create_example_extractions() -> List[FormulationRecord]:
    """
    Example extractions from real papers (TEMPLATE for you to populate).
    These are placeholder structures showing the extraction format.
    """

    records = [
        # Example 1: From a hypothetical IgG screening paper
        FormulationRecord(
            protein_id="IgG_huIgG1_Zhu2020",
            protein_mw_kda=150.0,
            protein_pi=7.2,
            protein_tm_baseline_c=61.0,
            buffer_species="phosphate",
            buffer_conc_mm=20.0,
            ph=7.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=300.0,
            stabilizers_json={"trehalose": 50.0, "polysorbate80": 0.01},
            temperature_c=25.0,
            stability_score=0.92,
            measured_aggregation_percent=2.1,
            measured_tm_shift_c=12.5,
            source_paper="Zhu_et_al_2020_Pharmaceutics_Table2",
            extraction_date=datetime.now().isoformat(),
            confidence_level="high"
        ),
        # Example 2: From a pH optimization study
        FormulationRecord(
            protein_id="mAb_Fc_KimEtAl2018",
            protein_mw_kda=145.0,
            protein_pi=6.8,
            protein_tm_baseline_c=63.0,
            buffer_species="histidine",
            buffer_conc_mm=10.0,
            ph=6.5,
            ionic_strength_mm=100.0,
            osmolarity_mosm_kg=200.0,
            stabilizers_json={"sorbitol": 150.0, "tween20": 0.05},
            temperature_c=4.0,
            stability_score=0.88,
            measured_aggregation_percent=3.2,
            measured_tm_shift_c=9.0,
            source_paper="Kim_et_al_2018_JACS_SupTable1",
            extraction_date=datetime.now().isoformat(),
            confidence_level="high"
        ),
    ]

    return records


# ============================================================================
# OUTPUT: Append to bioformbench_seed.csv
# ============================================================================

def append_to_bioformbench(new_records: List[FormulationRecord],
                          output_path: str = "data/bioformbench_expanded.csv"):
    """
    Append extracted records to BioFormBench.
    Outputs to a new file (user reviews before merging).
    """
    fieldnames = [
        "protein_id", "protein_mw_kda", "protein_pi", "protein_tm_baseline_c",
        "buffer_species", "buffer_conc_mm", "ph", "ionic_strength_mm", "osmolarity_mosm_kg",
        "stabilizers_json", "temperature_c", "stability_score",
        "measured_aggregation_percent", "measured_tm_shift_c"
    ]

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in new_records:
            writer.writerow(record.to_csv_row())

    print(f"✅ Extracted {len(new_records)} formulations → {output_path}")
    print(f"   Review this file, then: `cat {output_path} >> data/bioformbench_seed.csv`")


if __name__ == "__main__":
    import sys

    print("=" * 80)
    print("BioFormBench Expansion: Literature Mining Pipeline")
    print("=" * 80)
    print()
    print("PRIORITY PAPERS TO MINE:")
    for tier, papers in PRIORITY_PAPERS.items():
        print(f"\n{tier.upper()}:")
        for p in papers:
            print(f"  - {p.get('title', 'N/A')} ({p.get('doi', p.get('journal', 'N/A'))})")

    print("\n" + "=" * 80)
    print("EXTRACTION GUIDE:")
    print("=" * 80)
    print(MANUAL_EXTRACTION_GUIDE)

    print("\n" + "=" * 80)
    print("RUNNING EXAMPLE EXTRACTIONS (Template):")
    print("=" * 80)
    examples = create_example_extractions()
    append_to_bioformbench(examples, output_path="data/bioformbench_expanded_template.csv")

    print("\n✅ Template created at: data/bioformbench_expanded_template.csv")
    print("   Next: Search papers from PRIORITY_PAPERS, extract manually, run append_to_bioformbench()")
