#!/usr/bin/env python
"""
CLI entrypoint for model training.

Thin wrapper around experiments.train that provides consistent
command-line interface for research-repo targets.

Usage:
    python scripts/train.py --phase synthetic --num_samples 100000 --device cuda
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.train import main as train_main


def main(args):
    """Train BioFormLM via CLI."""
    # Convert args to the format expected by experiments.train.main()
    # experiments/train.py expects args object with:
    #   - phase: "synthetic", "real", "all"
    #   - num_samples: int
    #   - output_dir: Path
    #   - device: "cuda" or "cpu"
    #   - seed: int

    # Pass through to experiments.train.main()
    train_main(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train BioForm-LM model on synthetic or real data"
    )
    parser.add_argument(
        "--phase",
        choices=["synthetic", "real", "all"],
        default="synthetic",
        help="Training phase: synthetic pretraining, real fine-tuning, or both (default: synthetic)",
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        default=100_000,
        help="Number of samples to train on (default: 100000)",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("experiments/checkpoints"),
        help="Output directory for checkpoints (default: experiments/checkpoints)",
    )
    parser.add_argument(
        "--device",
        choices=["cuda", "cpu"],
        default="cuda",
        help="Compute device (default: cuda, falls back to cpu if unavailable)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    main(args)
