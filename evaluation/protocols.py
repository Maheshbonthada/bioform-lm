"""
Cross-validation protocols for BioForm-LM evaluation.

Implements different data-splitting strategies for rigorous evaluation
on real formulation data (BioFormBench).
"""

import numpy as np
from typing import List, Tuple, Dict, Generator
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class LeaveOneProteinOut:
    """
    Leave-one-protein-out (LOPO) cross-validation.

    For each protein in BioFormBench:
    1. Use that protein's data as the test set
    2. Use all other proteins' data (or synthetic data) for training/few-shot conditioning
    3. Evaluate on held-out protein

    This tests generalization to novel proteins with only a few real measurements.
    """

    def __init__(self, bioformbench_df=None):
        """
        Initialize LOPO splitter.

        Args:
            bioformbench_df: pandas DataFrame with protein_id column
        """
        self.bioformbench_df = bioformbench_df
        self.proteins = None
        if bioformbench_df is not None:
            self.proteins = bioformbench_df["protein_id"].unique().tolist()

    def split(self, bioformbench_df=None) -> Generator[Tuple[List[str], str], None, None]:
        """
        Generate LOPO splits.

        Args:
            bioformbench_df: pandas DataFrame with protein_id column

        Yields:
            (train_protein_ids, test_protein_id) tuples
        """
        if bioformbench_df is not None:
            self.bioformbench_df = bioformbench_df
            self.proteins = bioformbench_df["protein_id"].unique().tolist()

        if self.proteins is None:
            raise ValueError("Must provide bioformbench_df to split()")

        logger.info(f"LOPO splits: {len(self.proteins)} proteins, {len(self.proteins)} folds")

        for test_protein in self.proteins:
            train_proteins = [p for p in self.proteins if p != test_protein]
            yield train_proteins, test_protein

    def get_split_data(
        self, bioformbench_df, fold_idx: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get train/test data indices for a specific fold.

        Args:
            bioformbench_df: pandas DataFrame with protein_id column
            fold_idx: Fold index (0 to num_proteins-1)

        Returns:
            (train_indices, test_indices) as numpy arrays
        """
        proteins = bioformbench_df["protein_id"].unique().tolist()
        if fold_idx >= len(proteins):
            raise ValueError(f"fold_idx {fold_idx} out of range [0, {len(proteins)-1}]")

        test_protein = proteins[fold_idx]
        test_mask = bioformbench_df["protein_id"] == test_protein
        train_mask = ~test_mask

        train_indices = np.where(train_mask)[0]
        test_indices = np.where(test_mask)[0]

        return train_indices, test_indices

    def num_folds(self) -> int:
        """Get total number of folds."""
        return len(self.proteins) if self.proteins is not None else 0


class RandomSplit:
    """
    Random train/test split.

    Simple baseline for comparison. Randomly partitions BioFormBench
    into train and test sets with a given ratio.

    Less rigorous than LOPO (test may contain data from training proteins),
    but useful as a quick validation check.
    """

    def __init__(self, train_ratio: float = 0.8, random_state: int = 42):
        """
        Initialize RandomSplit splitter.

        Args:
            train_ratio: Fraction of data to use for training (default: 0.8)
            random_state: Random seed for reproducibility
        """
        self.train_ratio = train_ratio
        self.random_state = random_state

    def split(self, bioformbench_df) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate random train/test split.

        Args:
            bioformbench_df: pandas DataFrame

        Returns:
            (train_indices, test_indices) as numpy arrays
        """
        n_samples = len(bioformbench_df)
        n_train = int(n_samples * self.train_ratio)

        rng = np.random.RandomState(self.random_state)
        all_indices = np.arange(n_samples)
        rng.shuffle(all_indices)

        train_indices = all_indices[:n_train]
        test_indices = all_indices[n_train:]

        logger.info(
            f"RandomSplit: {len(train_indices)} train, {len(test_indices)} test "
            f"(ratio={self.train_ratio})"
        )

        return train_indices, test_indices


class FewShotEval:
    """
    Few-shot evaluation protocol for LOPO.

    Variant of LOPO where:
    1. Test protein is held out
    2. From held-out protein, use k random samples as conditioning set (few-shot)
    3. Remaining samples from held-out protein form test set
    4. All other proteins provide synthetic training data

    This mirrors the practical in-context few-shot setup described in the paper.
    """

    def __init__(self, n_shots: int = 3, random_state: int = 42):
        """
        Initialize few-shot evaluation.

        Args:
            n_shots: Number of real examples to show model for each test protein
            random_state: Random seed
        """
        self.n_shots = n_shots
        self.random_state = random_state

    def get_shot_indices(
        self, bioformbench_df, test_protein_id: str
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get few-shot conditioning and test indices for a protein.

        Args:
            bioformbench_df: pandas DataFrame
            test_protein_id: Protein to evaluate on

        Returns:
            (conditioning_indices, test_indices) as numpy arrays
        """
        test_mask = bioformbench_df["protein_id"] == test_protein_id
        test_indices = np.where(test_mask)[0]

        n_test_samples = len(test_indices)
        if n_test_samples <= self.n_shots:
            logger.warning(
                f"Protein {test_protein_id} has {n_test_samples} samples, "
                f"but n_shots={self.n_shots}. Using all as test."
            )
            return np.array([], dtype=int), test_indices

        rng = np.random.RandomState(self.random_state)
        shot_mask = rng.rand(n_test_samples) < (self.n_shots / n_test_samples)
        shot_indices = test_indices[shot_mask]

        # Ensure we get exactly n_shots
        if len(shot_indices) < self.n_shots:
            remaining = self.n_shots - len(shot_indices)
            remaining_indices = test_indices[~shot_mask]
            shot_indices = np.concatenate(
                [shot_indices, rng.choice(remaining_indices, remaining, replace=False)]
            )

        # Remaining test samples are the evaluation set
        remaining_test = test_indices[~np.isin(test_indices, shot_indices)]

        return shot_indices, remaining_test
