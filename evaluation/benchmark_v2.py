"""
BioFormBench loader with corrected protein identity and leakage control.

Two defects in the original pipeline are fixed here.

1. Protein identity. `protein_id` encodes the *formulation*, not the protein --
   "A33_Fab_citrate_glycine10/20/30..." are one Fab at eight glycine levels. Left
   as-is, LOPO treats each formulation as its own protein, so no protein clears a
   few-shot threshold and the benchmark collapses. Grouping instead on the
   physical descriptors (MW, pI) recovers 15 real proteins from 46 ids.

2. Target leakage. `protein_tm_baseline_c` should be a constant property of the
   protein, but it holds the *measured* post-formulation Tm: across the A33 Fab
   glycine series it climbs 77.1 -> 83.6 C in step with the excipient. Over the
   whole benchmark it correlates with the target at rho = 0.34 (p = 0.005), so
   passing it to the model leaks the outcome. Each protein's baseline is
   therefore collapsed to the minimum observed value -- the least-stabilised
   measurement, the closest available proxy for an unstabilised baseline -- which
   removes within-protein variation while preserving genuine between-protein
   signal.
"""

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "bioformbench_v2.csv"


class BioFormBenchV2:
    def __init__(self, csv_path: Optional[Path] = None, min_formulations: int = 4):
        self.csv_path = Path(csv_path or DEFAULT_CSV)
        self.min_formulations = min_formulations
        self.df: Optional[pd.DataFrame] = None

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.csv_path)

        # (1) real protein identity
        df["protein_key"] = (
            df["protein_mw_kda"].round(2).astype(str) + "_" +
            df["protein_pi"].round(2).astype(str)
        )

        # (2) neutralise the leaking baseline-Tm column
        df["tm_baseline_clean"] = df.groupby("protein_key")["protein_tm_baseline_c"] \
                                    .transform("min")

        counts = df["protein_key"].value_counts()
        df["n_formulations"] = df["protein_key"].map(counts)
        df["lopo_eligible"] = df["n_formulations"] >= self.min_formulations

        self.df = df
        return df

    def eligible(self) -> pd.DataFrame:
        if self.df is None:
            self.load()
        return self.df[self.df["lopo_eligible"]].copy()

    def proteins(self) -> List[str]:
        return sorted(self.eligible()["protein_key"].unique().tolist())

    def protein_rows(self, key: str) -> pd.DataFrame:
        if self.df is None:
            self.load()
        return self.df[self.df["protein_key"] == key].copy()

    def descriptor(self, key: str) -> Dict[str, float]:
        r = self.protein_rows(key).iloc[0]
        return {"mw_kda": float(r["protein_mw_kda"]),
                "pi": float(r["protein_pi"]),
                "tm_baseline_c": float(r["tm_baseline_clean"])}

    def summary(self) -> Dict[str, object]:
        if self.df is None:
            self.load()
        el = self.eligible()
        return {
            "total_formulations": int(len(self.df)),
            "total_proteins": int(self.df["protein_key"].nunique()),
            "eligible_proteins": int(el["protein_key"].nunique()),
            "eligible_formulations": int(len(el)),
            "min_formulations": self.min_formulations,
        }
