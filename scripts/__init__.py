"""
CLI entrypoints for BioForm-LM research pipeline.

Scripts in this package are thin wrappers around library code in data/,
model/, and experiments/ packages. They provide a consistent command-line
interface for research-repo targets (Makefile, workflows, etc.).

Standard convention:
- Library code (reusable functions/classes) lives in data/, model/, experiments/, etc.
- CLI entrypoints (argparse, logging setup, orchestration) live in scripts/
- Tests live in tests/
"""

__all__ = ["generate_data", "train", "evaluate"]
