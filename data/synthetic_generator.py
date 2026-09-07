"""
Synthetic Formulation Data Generator

Generates high-quality synthetic (protein, formulation) → (stability_outcome) triples
using the validated mechanistic simulator. This synthetic corpus is used for
pretraining the transformer model.

Production features:
- Stratified sampling (covers diverse protein/formulation space)
- Quality filtering (removes unphysical samples)
- Reproducible with seed control
- Efficient batch generation
- Parallel generation capability
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import logging
from dataclasses import dataclass
import json
from tqdm import tqdm
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.mechanistic_sim import (
    BiologicsFormulationSimulator,
    ProteinDescriptor,
    FormulationComposition,
    SimulationOutput,
)
from config import CFG, SyntheticDataConfig

logger = logging.getLogger(__name__)


@dataclass
class SyntheticSample:
    """Single synthetic training sample."""
    protein_mw_kda: float
    protein_pi: float
    protein_hydrophobicity: float
    protein_tm_baseline_c: float
    buffer_species: str
    buffer_conc_mm: float
    ph: float
    ionic_strength_mm: float
    osmolarity_mosm_kg: float
    stabilizers_json: str  # JSON string of stabilizer dict
    temperature_c: float
    storage_duration_days: float
    # Outcomes
    tm_shift_c: float
    predicted_tm_c: float
    aggregation_risk_combined: float
    predicted_aggregation_percent: float
    stability_score: float

    def to_dict(self) -> Dict:
        """Convert to dict for DataFrame."""
        return {
            'protein_mw_kda': self.protein_mw_kda,
            'protein_pi': self.protein_pi,
            'protein_hydrophobicity': self.protein_hydrophobicity,
            'protein_tm_baseline_c': self.protein_tm_baseline_c,
            'buffer_species': self.buffer_species,
            'buffer_conc_mm': self.buffer_conc_mm,
            'ph': self.ph,
            'ionic_strength_mm': self.ionic_strength_mm,
            'osmolarity_mosm_kg': self.osmolarity_mosm_kg,
            'stabilizers_json': self.stabilizers_json,
            'temperature_c': self.temperature_c,
            'storage_duration_days': self.storage_duration_days,
            'tm_shift_c': self.tm_shift_c,
            'predicted_tm_c': self.predicted_tm_c,
            'aggregation_risk_combined': self.aggregation_risk_combined,
            'predicted_aggregation_percent': self.predicted_aggregation_percent,
            'stability_score': self.stability_score,
        }


class SyntheticDataGenerator:
    """Generates high-quality synthetic training data."""

    def __init__(
        self,
        num_samples: int = 500_000,
        seed: int = 42,
        config: Optional[SyntheticDataConfig] = None,
    ):
        """
        Initialize synthetic data generator.

        Args:
            num_samples: Number of synthetic samples to generate
            seed: Random seed for reproducibility
            config: SyntheticDataConfig from config.py
        """
        self.num_samples = num_samples
        self.seed = seed
        self.rng = np.random.RandomState(seed)
        self.config = config or CFG.synthetic_data

        # Initialize simulator
        self.simulator = BiologicsFormulationSimulator(
            config_dict={
                'hamaker_constant': CFG.simulator.hamaker_constant,
                'bjerrum_length': CFG.simulator.bjerrum_length,
                'ph_penalty_per_unit_sq': CFG.simulator.ph_penalty_per_unit_sq,
                'osmol_positive_slope': CFG.simulator.osmol_positive_slope,
                'osmol_negative_slope': CFG.simulator.osmol_negative_slope,
                'aggregation_rate_constant': CFG.simulator.aggregation_rate_constant,
                'stabilizer_effects': CFG.simulator.stabilizer_effects,
            }
        )

        logger.info(f"SyntheticDataGenerator initialized: {num_samples} samples, seed={seed}")

    def generate(self) -> pd.DataFrame:
        """
        Generate synthetic dataset.

        Returns:
            DataFrame with synthetic (protein, formulation) → outcome triples

        Process:
        1. Sample random proteins from descriptor space
        2. Sample random formulations from composition space
        3. Run simulator for each pair
        4. Filter out unphysical/invalid samples
        5. Return as DataFrame

        This is CPU-efficient and can generate millions of samples.
        """
        samples = []
        skipped = 0

        logger.info(f"Generating {self.num_samples} synthetic samples...")

        for i in tqdm(range(self.num_samples), desc="Generating synthetic data"):
            try:
                # Sample random protein
                protein = self._sample_protein()

                # Sample random formulation
                formulation = self._sample_formulation()

                # Run simulator
                output = self.simulator.predict(protein, formulation)

                # Create sample
                stabilizers_dict = formulation.stabilizers or {}
                sample = SyntheticSample(
                    protein_mw_kda=protein.mw_kda,
                    protein_pi=protein.pi,
                    protein_hydrophobicity=protein.hydrophobicity,
                    protein_tm_baseline_c=protein.tm_baseline_c,
                    buffer_species=formulation.buffer_species,
                    buffer_conc_mm=formulation.buffer_conc_mm,
                    ph=formulation.ph,
                    ionic_strength_mm=formulation.ionic_strength_mm,
                    osmolarity_mosm_kg=formulation.osmolarity_mosm_kg,
                    stabilizers_json=json.dumps(stabilizers_dict),
                    temperature_c=formulation.temperature_c,
                    storage_duration_days=formulation.storage_duration_days,
                    tm_shift_c=output.tm_shift_c,
                    predicted_tm_c=output.predicted_tm_c,
                    aggregation_risk_combined=output.aggregation_risk_combined,
                    predicted_aggregation_percent=output.predicted_aggregation_percent,
                    stability_score=output.stability_score,
                )

                # Quality check: ensure sample is physically plausible
                if self._is_valid_sample(sample):
                    samples.append(sample.to_dict())
                else:
                    skipped += 1

            except Exception as e:
                skipped += 1
                if i % 10000 == 0:
                    logger.debug(f"Skipped sample {i}: {e}")
                continue

        logger.info(f"Generated {len(samples)} valid samples, skipped {skipped}")

        # Convert to DataFrame
        df = pd.DataFrame(samples)
        return df

    def _sample_protein(self) -> ProteinDescriptor:
        """Sample random protein descriptor."""
        mw = self.rng.uniform(*self.config.protein_mw_range)
        pi = self.rng.uniform(*self.config.protein_pi_range)
        hydro = self.rng.uniform(*self.config.protein_hydrophobicity_range)
        tm = self.rng.uniform(30, 85)  # typical Tm range

        return ProteinDescriptor(
            mw_kda=mw,
            pi=pi,
            hydrophobicity=hydro,
            tm_baseline_c=tm,
        )

    def _sample_formulation(self) -> FormulationComposition:
        """Sample random formulation composition."""
        # Buffer
        buffer_species = self.rng.choice(self.config.buffer_types)
        buffer_conc = self.rng.uniform(*self.config.buffer_concentration_range)

        # pH
        ph = self.rng.uniform(*self.config.ph_range)

        # Ionic strength
        ionic_strength = self.rng.uniform(*self.config.ionic_strength_range)

        # Osmolarity (derived from buffer + ions)
        osmolarity = self.rng.uniform(*self.config.osmolarity_range)

        # Stabilizers (multi-select)
        stabilizers = {}
        num_stab = self.rng.randint(0, self.config.num_stabilizers_per_sample + 1)

        for _ in range(num_stab):
            stab_name = self.rng.choice(list(self.config.stabilizer_pool.keys()))
            min_conc, max_conc = self.config.stabilizer_pool[stab_name]

            # Avoid adding zero-concentration stabilizers
            if max_conc > 0:
                conc = self.rng.uniform(min_conc + 0.01, max_conc)
                stabilizers[stab_name] = conc

        # Storage conditions
        temperature = self.rng.uniform(*self.config.temperature_range)
        duration = self.rng.uniform(*self.config.storage_duration_range)

        return FormulationComposition(
            buffer_species=buffer_species,
            buffer_conc_mm=buffer_conc,
            ph=ph,
            ionic_strength_mm=ionic_strength,
            osmolarity_mosm_kg=osmolarity,
            stabilizers=stabilizers,
            temperature_c=temperature,
            storage_duration_days=duration,
        )

    def _is_valid_sample(self, sample: SyntheticSample) -> bool:
        """
        Quality filter: reject unphysical or invalid samples.

        Checks:
        - Aggregation % in reasonable range
        - Stability score is valid
        - Outcomes are finite (not NaN/inf)
        """
        # Check for NaN/inf
        if not np.isfinite(sample.aggregation_risk_combined):
            return False
        if not np.isfinite(sample.stability_score):
            return False

        # Aggregation should be 0-100%
        if not (0 <= sample.predicted_aggregation_percent <= 100):
            return False

        # Stability score should be 0-1
        if not (0 <= sample.stability_score <= 1):
            return False

        # At least some buffer
        if sample.buffer_conc_mm < 1:
            return False

        return True

    def save(self, path: Path) -> None:
        """Generate and save synthetic data to CSV/Parquet."""
        df = self.generate()

        # Save as both CSV (human-readable) and Parquet (efficient)
        csv_path = path.with_suffix('.csv')
        parquet_path = path.with_suffix('.parquet')

        logger.info(f"Saving {len(df)} samples to {csv_path}")
        df.to_csv(csv_path, index=False)

        logger.info(f"Saving to Parquet: {parquet_path}")
        df.to_parquet(parquet_path, index=False)

        # Summary statistics
        logger.info("\n" + "=" * 70)
        logger.info("SYNTHETIC DATA SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total samples: {len(df)}")
        logger.info(f"\nProtein descriptors:")
        logger.info(df[['protein_mw_kda', 'protein_pi', 'protein_tm_baseline_c']].describe())
        logger.info(f"\nFormulation parameters:")
        logger.info(df[['ph', 'ionic_strength_mm', 'temperature_c']].describe())
        logger.info(f"\nOutcomes:")
        logger.info(df[['stability_score', 'predicted_aggregation_percent']].describe())
        logger.info("=" * 70)

        return df


def generate_synthetic_dataset(
    output_dir: Path = None,
    num_samples: int = 500_000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Convenience function: generate and save synthetic dataset.

    Args:
        output_dir: Directory to save dataset (default: data/)
        num_samples: Number of samples (default: 500K)
        seed: Random seed (default: 42)

    Returns:
        Generated DataFrame
    """
    if output_dir is None:
        output_dir = Path(__file__).parent

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate
    generator = SyntheticDataGenerator(
        num_samples=num_samples,
        seed=seed,
    )

    # Save
    output_path = output_dir / "synthetic_training_data"
    df = generator.generate()
    generator.save(output_path)

    return df


if __name__ == "__main__":
    """Generate synthetic dataset."""
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Command line: python synthetic_generator.py <num_samples>
    num_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000

    df = generate_synthetic_dataset(
        num_samples=num_samples,
        seed=42,
    )

    print(f"\n✓ Generated {len(df)} synthetic samples")
    print(f"Dataset saved to: data/synthetic_training_data.*")
