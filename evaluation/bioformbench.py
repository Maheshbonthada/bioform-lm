"""
BioFormBench: Real biologics formulation data from literature mining.

Curated dataset of real formulation recipes and their measured outcomes,
mined from published literature (DSF thermal shifts, SEC aggregation %, etc.).

This is the held-out real-data benchmark for evaluating BioForm-LM.
Used for leave-one-protein-out cross-validation to assess generalization
to novel proteins with limited real-data measurements.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BioFormBench:
    """
    Loader for BioFormBench curated formulation dataset.

    Expected CSV columns:
    - protein_id: unique protein identifier (e.g. "protein_1", "antibody_XYZ")
    - protein_mw_kda: molecular weight in kDa
    - protein_pi: isoelectric point
    - protein_tm_baseline_c: baseline melting temperature (Celsius)
    - buffer_species: e.g. "histidine", "phosphate", "acetate"
    - buffer_conc_mm: buffer concentration (mM)
    - ph: pH value
    - ionic_strength_mm: ionic strength (mM NaCl equivalent)
    - osmolarity_mosm_kg: osmolarity (mOsm/kg)
    - stabilizers_json: JSON string of stabilizer dict {name: concentration}
    - temperature_c: storage/measurement temperature (Celsius)
    - stability_score: measured stability outcome (0-1 scale, higher=better)
    - measured_aggregation_percent: aggregation % from SEC/turbidity (optional)
    - measured_tm_shift_c: thermal shift from DSF (optional)
    """

    def __init__(self, csv_path: Optional[Path] = None):
        """
        Initialize BioFormBench loader.

        Args:
            csv_path: Path to BioFormBench CSV file.
                     If None, looks for data/bioformbench.csv by default.
        """
        self.csv_path = csv_path or Path(__file__).parent.parent / "data" / "bioformbench.csv"
        self.df = None
        self.proteins = None
        self.is_loaded = False

    def load(self) -> pd.DataFrame:
        """
        Load BioFormBench dataset from CSV.

        Returns:
            DataFrame with columns as described in class docstring.

        Raises:
            FileNotFoundError: If csv_path does not exist.
            ValueError: If required columns are missing.
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"BioFormBench CSV not found at {self.csv_path}. "
                f"Please ensure literature-mined dataset is saved there."
            )

        logger.info(f"Loading BioFormBench from {self.csv_path}")
        self.df = pd.read_csv(self.csv_path)

        # Validate required columns
        required_cols = [
            "protein_id",
            "protein_mw_kda",
            "protein_pi",
            "protein_tm_baseline_c",
            "buffer_species",
            "buffer_conc_mm",
            "ph",
            "ionic_strength_mm",
            "osmolarity_mosm_kg",
            "stabilizers_json",
            "temperature_c",
            "stability_score",
        ]

        missing_cols = [col for col in required_cols if col not in self.df.columns]
        if missing_cols:
            raise ValueError(
                f"BioFormBench CSV missing required columns: {missing_cols}. "
                f"Found columns: {list(self.df.columns)}"
            )

        # Extract unique proteins
        self.proteins = self.df["protein_id"].unique().tolist()
        self.is_loaded = True

        logger.info(
            f"✓ Loaded BioFormBench: {len(self.df)} samples from {len(self.proteins)} proteins"
        )

        return self.df

    def get_protein_data(self, protein_id: str) -> pd.DataFrame:
        """
        Get all formulations for a specific protein.

        Args:
            protein_id: Protein identifier

        Returns:
            Subset DataFrame for that protein
        """
        if not self.is_loaded:
            self.load()

        subset = self.df[self.df["protein_id"] == protein_id]
        if len(subset) == 0:
            raise ValueError(f"Protein '{protein_id}' not found in BioFormBench")

        return subset

    def get_protein_descriptor(self, protein_id: str) -> Dict[str, float]:
        """
        Get protein descriptor for a specific protein (MW, pI, Tm).

        Args:
            protein_id: Protein identifier

        Returns:
            Dict with keys: mw_kda, pi, tm_baseline_c
        """
        if not self.is_loaded:
            self.load()

        protein_data = self.get_protein_data(protein_id)
        first_row = protein_data.iloc[0]

        return {
            "mw_kda": first_row["protein_mw_kda"],
            "pi": first_row["protein_pi"],
            "tm_baseline_c": first_row["protein_tm_baseline_c"],
        }

    def get_formulations(self, protein_id: str) -> List[Dict]:
        """
        Get list of known-good formulations for a protein.

        Args:
            protein_id: Protein identifier

        Returns:
            List of formulation dicts with stability_score and formulation params
        """
        if not self.is_loaded:
            self.load()

        protein_data = self.get_protein_data(protein_id)
        formulations = []

        for _, row in protein_data.iterrows():
            formulation = {
                "buffer_species": row["buffer_species"],
                "buffer_conc_mm": row["buffer_conc_mm"],
                "ph": row["ph"],
                "ionic_strength_mm": row["ionic_strength_mm"],
                "osmolarity_mosm_kg": row["osmolarity_mosm_kg"],
                "stabilizers_json": row["stabilizers_json"],
                "temperature_c": row["temperature_c"],
                "stability_score": row["stability_score"],
            }
            formulations.append(formulation)

        return formulations

    def get_top_formulations(self, protein_id: str, k: int = 5) -> List[Dict]:
        """
        Get top-k best formulations for a protein (by stability score).

        Args:
            protein_id: Protein identifier
            k: Number of top formulations to return

        Returns:
            List of top-k formulation dicts, sorted by stability_score (descending)
        """
        if not self.is_loaded:
            self.load()

        protein_data = self.get_protein_data(protein_id)
        sorted_data = protein_data.sort_values("stability_score", ascending=False)

        formulations = []
        for _, row in sorted_data.head(k).iterrows():
            formulation = {
                "buffer_species": row["buffer_species"],
                "buffer_conc_mm": row["buffer_conc_mm"],
                "ph": row["ph"],
                "ionic_strength_mm": row["ionic_strength_mm"],
                "osmolarity_mosm_kg": row["osmolarity_mosm_kg"],
                "stabilizers_json": row["stabilizers_json"],
                "temperature_c": row["temperature_c"],
                "stability_score": row["stability_score"],
            }
            formulations.append(formulation)

        return formulations

    def summary(self) -> Dict:
        """
        Get summary statistics for BioFormBench.

        Returns:
            Dict with key stats
        """
        if not self.is_loaded:
            self.load()

        return {
            "num_samples": len(self.df),
            "num_proteins": len(self.proteins),
            "proteins": self.proteins,
            "stability_score_range": (
                self.df["stability_score"].min(),
                self.df["stability_score"].max(),
            ),
            "stability_score_mean": self.df["stability_score"].mean(),
            "stability_score_std": self.df["stability_score"].std(),
        }

    def __len__(self) -> int:
        """Get number of samples."""
        if not self.is_loaded:
            self.load()
        return len(self.df)

    def __repr__(self) -> str:
        if self.is_loaded:
            return (
                f"BioFormBench(n_samples={len(self.df)}, n_proteins={len(self.proteins)})"
            )
        return f"BioFormBench(path={self.csv_path}, not loaded)"
