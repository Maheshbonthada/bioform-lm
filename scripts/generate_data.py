#!/usr/bin/env python
"""
CLI entrypoint for synthetic data generation.

Thin wrapper around data.synthetic_generator that provides consistent
command-line interface for research-repo targets.

Usage:
    python scripts/generate_data.py <num_samples> [--output_dir DIR] [--seed SEED]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.synthetic_generator import generate_synthetic_dataset

logger = logging.getLogger(__name__)


def main(args):
    """Generate synthetic dataset via CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("=" * 70)
    logger.info("SYNTHETIC DATA GENERATION")
    logger.info("=" * 70)
    logger.info(f"Num samples: {args.num_samples}")
    logger.info(f"Output dir: {args.output_dir}")
    logger.info(f"Seed: {args.seed}")

    # Generate and save
    df = generate_synthetic_dataset(
        output_dir=Path(args.output_dir),
        num_samples=args.num_samples,
        seed=args.seed,
    )

    logger.info("\n" + "=" * 70)
    logger.info("✓ DATA GENERATION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Generated {len(df)} samples")
    logger.info(f"Output: {args.output_dir}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic formulation training data"
    )
    parser.add_argument(
        "num_samples",
        type=int,
        nargs="?",
        default=100_000,
        help="Number of samples to generate (default: 100000)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="data",
        help="Output directory for generated data (default: data/)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    args = parser.parse_args()
    main(args)
