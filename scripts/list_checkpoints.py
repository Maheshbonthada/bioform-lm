#!/usr/bin/env python
"""
List available model checkpoints and their metadata.

Run: python scripts/list_checkpoints.py
"""

import torch
from pathlib import Path
from tabulate import tabulate
import argparse

CHECKPOINT_DIR = Path("experiments/checkpoints")


def list_checkpoints(verbose: bool = False):
    """List all available checkpoints."""
    if not CHECKPOINT_DIR.exists():
        print(f"❌ No checkpoints found at {CHECKPOINT_DIR}")
        return

    checkpoints = sorted(CHECKPOINT_DIR.glob("checkpoint_epoch_*.pt"))

    if not checkpoints:
        print(f"❌ No checkpoints found in {CHECKPOINT_DIR}")
        return

    print(f"\n📦 Found {len(checkpoints)} checkpoints in {CHECKPOINT_DIR}\n")

    data = []
    for ckpt_path in checkpoints:
        try:
            size_mb = ckpt_path.stat().st_size / (1024 ** 2)

            if verbose:
                # Load checkpoint to get metadata
                ckpt = torch.load(ckpt_path, map_location="cpu")
                epoch = ckpt.get("epoch", "?")
                val_loss = ckpt.get("val_loss", "?")
                data.append([
                    ckpt_path.name,
                    f"{size_mb:.1f} MB",
                    epoch,
                    f"{val_loss:.4f}" if isinstance(val_loss, float) else val_loss,
                ])
            else:
                data.append([ckpt_path.name, f"{size_mb:.1f} MB"])
        except Exception as e:
            data.append([ckpt_path.name, f"ERROR: {e}"])

    headers = ["Checkpoint", "Size"] if not verbose else ["Checkpoint", "Size", "Epoch", "Val Loss"]
    print(tabulate(data, headers=headers, tablefmt="grid"))

    # Show latest checkpoint
    latest = checkpoints[-1]
    print(f"\n✓ Latest checkpoint: {latest.name}")
    print(f"  Full path: {latest.absolute()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List model checkpoints")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show epoch and val_loss")
    args = parser.parse_args()

    list_checkpoints(verbose=args.verbose)
