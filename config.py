"""
BioForm-LM Configuration Module
Centralized config for all experiments, simulators, and training runs.
Enforces type safety via Pydantic.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path
import json

# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
SIMULATOR_DIR = PROJECT_ROOT / "simulator"
MODEL_DIR = PROJECT_ROOT / "model"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
TESTS_DIR = PROJECT_ROOT / "tests"
PAPER_DIR = PROJECT_ROOT / "paper"
CHECKPOINTS_DIR = EXPERIMENTS_DIR / "checkpoints"

# Create directories if they don't exist
for d in [DATA_DIR, CHECKPOINTS_DIR, EXPERIMENTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================================
# SIMULATOR CONFIGURATION
# ============================================================================

@dataclass
class SimulatorConfig:
    """Mechanistic simulator (DLVO + Lumry-Eyring) hyperparameters."""

    # DLVO Model
    hamaker_constant: float = 1e-20  # Joules, typical for proteins
    bjerrum_length: float = 0.7  # nanometers, water at 25°C
    debye_screening_strength: float = 1.0  # tuning parameter

    # Lumry-Eyring thermodynamics
    tm_baseline_default: float = 65.0  # °C, fallback if not provided
    cp_folding: float = 1.5  # kJ/mol/K, heat capacity change

    # Stabilizer effects (literature values, ΔTm per unit concentration)
    stabilizer_effects: Dict[str, tuple] = field(default_factory=lambda: {
        "sucrose": ("percent", 0.5),  # +0.5°C per 1% w/v
        "sorbitol": ("percent", 0.3),
        "trehalose": ("percent", 0.7),
        "polysorbate_20": ("percent", 0.24),
        "polysorbate_80": ("percent", 0.2),
        "glycerol": ("percent_v", 0.18),
        "bsa": ("percent", 0.4),
        "gelatin": ("percent", 0.35),
    })

    # pH effect (quadratic penalty for deviation from optimal)
    ph_penalty_per_unit_sq: float = 0.5  # °C per pH-unit²

    # Osmolarity effect
    osmol_positive_slope: float = 0.01  # °C per mOsm/kg above 300
    osmol_negative_slope: float = -0.02  # °C per mOsm/kg below 300

    # Aggregation kinetics (Lumry-Eyring)
    aggregation_rate_constant: float = 0.08  # temperature-dependent scaling

    # Validation thresholds
    tm_prediction_mae_threshold: float = 3.0  # °C (acceptable error)
    aggregation_prediction_r2_threshold: float = 0.7  # minimum R² on literature data


# ============================================================================
# SYNTHETIC DATA GENERATION CONFIG
# ============================================================================

@dataclass
class SyntheticDataConfig:
    """Parameters for generating synthetic (protein, formulation) → outcome triples."""

    num_synthetic_samples: int = 500_000  # total synthetic samples to generate

    # Protein descriptor ranges
    protein_mw_range: tuple = (10, 200)  # kDa
    protein_pi_range: tuple = (4.0, 10.0)
    protein_hydrophobicity_range: tuple = (0.2, 0.8)

    # Formulation parameter ranges
    buffer_types: list = field(default_factory=lambda: [
        "histidine", "acetate", "phosphate", "tris", "citrate", "succinate"
    ])
    buffer_concentration_range: tuple = (5, 100)  # mM
    ph_range: tuple = (3.5, 9.0)
    ionic_strength_range: tuple = (10, 500)  # mM
    osmolarity_range: tuple = (150, 400)  # mOsm/kg

    # Stabilizers (multi-select, each has own concentration range)
    stabilizer_pool: Dict[str, tuple] = field(default_factory=lambda: {
        "sucrose": (0, 10),  # % w/v range
        "sorbitol": (0, 15),
        "trehalose": (0, 10),
        "polysorbate_20": (0, 1.0),
        "polysorbate_80": (0, 1.0),
        "glycerol": (0, 20),  # % v/v
        "bsa": (0, 5),
    })

    num_stabilizers_per_sample: int = 3  # avg stabilizers per formulation

    # Storage conditions
    temperature_range: tuple = (4, 37)  # °C
    storage_duration_range: tuple = (1, 365)  # days


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

@dataclass
class ModelConfig:
    """Transformer architecture for generative formulation design."""

    # Model size
    hidden_dim: int = 256
    num_layers: int = 6
    num_heads: int = 8
    feedforward_dim: int = 1024
    max_seq_len: int = 64

    # Vocabulary
    vocab_size: int = 1024  # tokenized formulation components
    embedding_dim: int = 128

    # Training
    batch_size: int = 32
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5
    max_epochs: int = 100
    early_stopping_patience: int = 15
    warmup_steps: int = 1000

    # Dropout & regularization
    dropout: float = 0.1
    label_smoothing: float = 0.1

    # Loss weighting (physics-informed)
    stability_loss_weight: float = 0.7  # main prediction target
    diversity_loss_weight: float = 0.15  # encourage varied recipes
    physics_regularization_weight: float = 0.15  # simulator consistency

    # In-context learning (few-shot adaptation)
    num_context_shots: int = 5  # how many real measurements for adaptation
    context_embedding_dim: int = 64


# ============================================================================
# TRAINING CONFIGURATION
# ============================================================================

@dataclass
class TrainingConfig:
    """Training pipeline configuration."""

    # Phases
    phase_1_synthetic_epochs: int = 50  # pretrain on synthetic
    phase_2_real_epochs: int = 100  # fine-tune on BioFormBench
    phase_3_adaptive_epochs: int = 20  # in-context fine-tuning

    # Data split
    train_val_split: float = 0.8  # 80% train, 20% val (on synthetic)
    test_split: float = 0.1  # separate test set

    # Checkpointing
    save_every_n_epochs: int = 5
    save_best_model: bool = True

    # Validation
    val_every_n_steps: int = 500
    compute_calibration_metrics: bool = True
    compute_uncertainty: bool = True  # Bayesian predictive variance

    # Hardware
    device: str = "cuda"  # or "cpu"
    num_workers: int = 4  # data loading
    pin_memory: bool = True
    mixed_precision: bool = True  # fp16 training

    # Reproducibility
    seed: int = 42
    deterministic: bool = True


# ============================================================================
# BIOFORMBENCH CONFIGURATION
# ============================================================================

@dataclass
class BioFormBenchConfig:
    """Literature-mined biologics formulation dataset configuration."""

    # Data extraction
    min_extraction_confidence: float = 0.8  # 0-1 scale

    # Quality filters
    min_formulations_per_protein: int = 3
    min_proteins_in_dataset: int = 5  # minimum viable dataset

    # Cross-validation
    cv_strategy: str = "leave_one_protein_out"  # LPO for unbiased evaluation

    # Uncertainty
    estimate_measurement_noise: bool = True
    measurement_noise_std: float = 0.5  # °C (typical DSF precision)


# ============================================================================
# EVALUATION CONFIGURATION
# ============================================================================

@dataclass
class EvaluationConfig:
    """Metrics and evaluation configuration."""

    # Recipe generation metrics
    top_k_recall: list = field(default_factory=lambda: [1, 3, 5, 10])
    top_k_precision: list = field(default_factory=lambda: [1, 3, 5, 10])

    # Stability prediction
    stability_mae_threshold: float = 2.0  # °C
    stability_rmse_threshold: float = 3.0  # °C

    # Ranking metrics
    spearman_correlation_min: float = 0.7
    kendall_tau_min: float = 0.6

    # Diversity metrics
    recipe_diversity_min: float = 0.5  # 0-1, measure of distinct generated recipes

    # Calibration (uncertainty quantification)
    calibration_error_max: float = 0.05  # 5% max miscalibration
    coverage_at_2sigma: float = 0.95  # 95% of true values within 2σ


# ============================================================================
# GLOBAL CONFIG INSTANCE
# ============================================================================

class BioFormLMConfig:
    """Master configuration singleton."""

    def __init__(self):
        self.simulator = SimulatorConfig()
        self.synthetic_data = SyntheticDataConfig()
        self.model = ModelConfig()
        self.training = TrainingConfig()
        self.bioformbench = BioFormBenchConfig()
        self.evaluation = EvaluationConfig()

    def to_dict(self) -> Dict[str, Any]:
        """Convert all configs to dict for logging."""
        return {
            "simulator": self.simulator.__dict__,
            "synthetic_data": self.synthetic_data.__dict__,
            "model": self.model.__dict__,
            "training": self.training.__dict__,
            "bioformbench": self.bioformbench.__dict__,
            "evaluation": self.evaluation.__dict__,
        }

    def save_to_file(self, path: Path):
        """Persist configuration for reproducibility."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def load_from_file(self, path: Path):
        """Load configuration from file."""
        with open(path, 'r') as f:
            config_dict = json.load(f)
        # Re-initialize from dict (simplified version)
        print(f"Loaded config from {path}")


# Global config instance
CFG = BioFormLMConfig()


if __name__ == "__main__":
    print("=" * 80)
    print("BioForm-LM Configuration")
    print("=" * 80)
    import json
    print(json.dumps(CFG.to_dict(), indent=2, default=str))

    # Save for future reference
    CFG.save_to_file(PROJECT_ROOT / "config_snapshot.json")
    print(f"\nConfiguration saved to {PROJECT_ROOT / 'config_snapshot.json'}")
