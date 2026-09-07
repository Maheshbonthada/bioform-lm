"""
Evaluation module for BioForm-LM.

Provides tools for evaluating the model on real biologics formulation data
(BioFormBench) using leave-one-protein-out cross-validation.

Components:
- bioformbench: Dataset loader for real formulation data
- metrics: Evaluation metrics (top-k recall, calibration, diversity)
- protocols: Cross-validation protocols (LOPO, random split)
"""

from evaluation.bioformbench import BioFormBench
from evaluation.metrics import RecallMetric, CalibrationMetric, DiversityMetric
from evaluation.protocols import LeaveOneProteinOut, RandomSplit

__all__ = [
    "BioFormBench",
    "RecallMetric",
    "CalibrationMetric",
    "DiversityMetric",
    "LeaveOneProteinOut",
    "RandomSplit",
]
