"""
Unit tests for evaluation module.

Tests for BioFormBench loader, metrics (recall, calibration, diversity),
and cross-validation protocols (LOPO, random split).
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import sys
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.bioformbench import BioFormBench
from evaluation.metrics import RecallMetric, CalibrationMetric, DiversityMetric
from evaluation.protocols import LeaveOneProteinOut, RandomSplit, FewShotEval


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_bioformbench_csv(tmp_path):
    """
    Create a temporary CSV file with sample BioFormBench data.
    """
    data = {
        "protein_id": ["protein_1", "protein_1", "protein_2", "protein_2"],
        "protein_mw_kda": [100.0, 100.0, 50.0, 50.0],
        "protein_pi": [7.0, 7.0, 6.5, 6.5],
        "protein_tm_baseline_c": [65.0, 65.0, 60.0, 60.0],
        "buffer_species": ["histidine", "phosphate", "acetate", "histidine"],
        "buffer_conc_mm": [20.0, 25.0, 15.0, 20.0],
        "ph": [6.0, 6.5, 5.5, 6.0],
        "ionic_strength_mm": [150.0, 200.0, 100.0, 150.0],
        "osmolarity_mosm_kg": [310.0, 350.0, 280.0, 310.0],
        "stabilizers_json": ["{}", '{"sucrose": 5}', '{"trehalose": 10}', '{"sucrose": 5}'],
        "temperature_c": [25.0, 4.0, 25.0, 25.0],
        "stability_score": [0.85, 0.75, 0.65, 0.80],
    }

    csv_path = tmp_path / "test_bioformbench.csv"
    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)

    return csv_path


# ============================================================================
# BIOFORMBENCH TESTS
# ============================================================================


class TestBioFormBench:
    """Test BioFormBench loader."""

    def test_load_valid_csv(self, sample_bioformbench_csv):
        """Test loading valid CSV file."""
        bench = BioFormBench(sample_bioformbench_csv)
        df = bench.load()

        assert len(df) == 4
        assert len(bench.proteins) == 2
        assert "protein_1" in bench.proteins
        assert "protein_2" in bench.proteins
        assert bench.is_loaded is True

    def test_load_missing_file(self):
        """Test error handling for missing file."""
        bench = BioFormBench(Path("/nonexistent/file.csv"))

        with pytest.raises(FileNotFoundError):
            bench.load()

    def test_get_protein_data(self, sample_bioformbench_csv):
        """Test getting data for a specific protein."""
        bench = BioFormBench(sample_bioformbench_csv)
        bench.load()

        protein_1_data = bench.get_protein_data("protein_1")
        assert len(protein_1_data) == 2
        assert (protein_1_data["protein_id"] == "protein_1").all()

    def test_get_protein_descriptor(self, sample_bioformbench_csv):
        """Test getting protein descriptor."""
        bench = BioFormBench(sample_bioformbench_csv)
        bench.load()

        descriptor = bench.get_protein_descriptor("protein_1")
        assert descriptor["mw_kda"] == 100.0
        assert descriptor["pi"] == 7.0
        assert descriptor["tm_baseline_c"] == 65.0

    def test_get_formulations(self, sample_bioformbench_csv):
        """Test getting formulations for a protein."""
        bench = BioFormBench(sample_bioformbench_csv)
        bench.load()

        formulations = bench.get_formulations("protein_1")
        assert len(formulations) == 2
        assert formulations[0]["buffer_species"] in ["histidine", "phosphate"]
        assert "stability_score" in formulations[0]

    def test_get_top_formulations(self, sample_bioformbench_csv):
        """Test getting top-k formulations."""
        bench = BioFormBench(sample_bioformbench_csv)
        bench.load()

        top_1 = bench.get_top_formulations("protein_1", k=1)
        assert len(top_1) == 1
        # protein_1 has stability scores 0.85 and 0.75, so top should be 0.85
        assert top_1[0]["stability_score"] == 0.85

    def test_summary(self, sample_bioformbench_csv):
        """Test summary statistics."""
        bench = BioFormBench(sample_bioformbench_csv)
        bench.load()

        summary = bench.summary()
        assert summary["num_samples"] == 4
        assert summary["num_proteins"] == 2
        assert len(summary["proteins"]) == 2
        assert summary["stability_score_mean"] > 0


# ============================================================================
# RECALL METRIC TESTS
# ============================================================================


class TestRecallMetric:
    """Test top-k recall metric."""

    def test_identical_formulations(self):
        """Test recall with identical formulations."""
        metric = RecallMetric()

        generated = [
            {
                "ph": 6.0,
                "ionic_strength_mm": 150.0,
                "osmolarity_mosm_kg": 310.0,
                "temperature_c": 25.0,
                "buffer_species": "histidine",
                "stabilizers_json": "{}",
            }
        ]

        known_good = generated.copy()

        recall, matches = metric.compute(generated, known_good, k=5)

        # Perfect match should give high recall
        assert recall == 1.0
        assert matches == 1

    def test_different_formulations(self):
        """Test recall with very different formulations."""
        metric = RecallMetric(distance_threshold=0.1)

        generated = [
            {
                "ph": 3.0,  # Very acidic
                "ionic_strength_mm": 10.0,  # Very low IS
                "osmolarity_mosm_kg": 80.0,  # Very low osmolarity
                "temperature_c": -10.0,  # Cold
                "buffer_species": "citrate",
                "stabilizers_json": "{}",
            }
        ]

        known_good = [
            {
                "ph": 9.0,  # Very basic
                "ionic_strength_mm": 500.0,  # High IS
                "osmolarity_mosm_kg": 450.0,  # High osmolarity
                "temperature_c": 40.0,  # Hot
                "buffer_species": "phosphate",
                "stabilizers_json": '{"sucrose": 10}',
            }
        ]

        recall, matches = metric.compute(generated, known_good, k=5)

        # Very different formulations should give low recall
        assert recall < 1.0
        assert matches < 1

    def test_empty_known_good(self):
        """Test recall with empty known-good set."""
        metric = RecallMetric()

        generated = [
            {
                "ph": 6.0,
                "ionic_strength_mm": 150.0,
                "osmolarity_mosm_kg": 310.0,
                "temperature_c": 25.0,
                "buffer_species": "histidine",
                "stabilizers_json": "{}",
            }
        ]

        recall, matches = metric.compute(generated, [], k=5)

        # Empty known-good returns perfect recall (no expectations)
        assert recall == 1.0


# ============================================================================
# CALIBRATION METRIC TESTS
# ============================================================================


class TestCalibrationMetric:
    """Test calibration (predicted vs actual) metric."""

    def test_perfect_calibration(self):
        """Test perfect correlation between predicted and actual."""
        metric = CalibrationMetric()

        predicted = [0.1, 0.3, 0.5, 0.7, 0.9]
        actual = [0.1, 0.3, 0.5, 0.7, 0.9]

        result = metric.compute(predicted, actual)

        # Perfect correlation (use approx for floating point)
        assert result["spearman_r"] == pytest.approx(1.0, abs=1e-6)
        assert result["kendall_tau"] == pytest.approx(1.0, abs=1e-6)
        assert result["mae"] == pytest.approx(0.0, abs=1e-6)
        assert result["rmse"] == pytest.approx(0.0, abs=1e-6)

    def test_anticorrelation(self):
        """Test anticorrelation between predicted and actual."""
        metric = CalibrationMetric()

        predicted = [0.1, 0.3, 0.5, 0.7, 0.9]
        actual = [0.9, 0.7, 0.5, 0.3, 0.1]

        result = metric.compute(predicted, actual)

        # Perfect anticorrelation (use approx for floating point)
        assert result["spearman_r"] == pytest.approx(-1.0, abs=1e-6)
        assert result["kendall_tau"] == pytest.approx(-1.0, abs=1e-6)

    def test_random_correlation(self):
        """Test weak correlation."""
        metric = CalibrationMetric()

        np.random.seed(42)
        predicted = np.random.uniform(0, 1, 20)
        actual = np.random.uniform(0, 1, 20)

        result = metric.compute(predicted.tolist(), actual.tolist())

        # Weak correlation should give r close to 0
        assert abs(result["spearman_r"]) < 0.6

    def test_single_sample(self):
        """Test with single sample (should return NaN)."""
        metric = CalibrationMetric()

        result = metric.compute([0.5], [0.4])

        assert np.isnan(result["spearman_r"])


# ============================================================================
# DIVERSITY METRIC TESTS
# ============================================================================


class TestDiversityMetric:
    """Test diversity metric."""

    def test_identical_formulations(self):
        """Test diversity of identical formulations."""
        metric = DiversityMetric()

        formulations = [
            {
                "ph": 6.0,
                "ionic_strength_mm": 150.0,
                "osmolarity_mosm_kg": 310.0,
                "temperature_c": 25.0,
                "buffer_species": "histidine",
                "stabilizers_json": "{}",
            }
        ] * 5  # 5 identical copies

        result = metric.compute(formulations)

        # Identical formulations should give zero diversity
        assert result["mean_pairwise_distance"] == 0.0

    def test_diverse_formulations(self):
        """Test diversity of diverse formulations."""
        metric = DiversityMetric()

        formulations = [
            {
                "ph": 4.0,
                "ionic_strength_mm": 50.0,
                "osmolarity_mosm_kg": 100.0,
                "temperature_c": 0.0,
                "buffer_species": "acetate",
                "stabilizers_json": "{}",
            },
            {
                "ph": 8.0,
                "ionic_strength_mm": 500.0,
                "osmolarity_mosm_kg": 450.0,
                "temperature_c": 40.0,
                "buffer_species": "tris",
                "stabilizers_json": '{"trehalose": 20}',
            },
        ]

        result = metric.compute(formulations)

        # Diverse formulations should give high mean distance
        assert result["mean_pairwise_distance"] > 0.1
        assert result["coverage"] > 0.0


# ============================================================================
# PROTOCOL TESTS
# ============================================================================


class TestLeaveOneProteinOut:
    """Test LOPO cross-validation protocol."""

    def test_lopo_splits(self, sample_bioformbench_csv):
        """Test LOPO generates correct splits."""
        df = pd.read_csv(sample_bioformbench_csv)
        splitter = LeaveOneProteinOut(df)

        splits = list(splitter.split())

        # Should have one split per protein
        assert len(splits) == 2

        # Each fold should have one test protein
        test_proteins = [test for _, test in splits]
        assert set(test_proteins) == {"protein_1", "protein_2"}

        # Train sets should be complementary
        assert len(splits[0][0]) == 1  # One protein in train (the other one)
        assert len(splits[1][0]) == 1

    def test_lopo_fold_indices(self, sample_bioformbench_csv):
        """Test LOPO get_split_data returns correct indices."""
        df = pd.read_csv(sample_bioformbench_csv)
        splitter = LeaveOneProteinOut(df)

        train_idx, test_idx = splitter.get_split_data(df, fold_idx=0)

        # First fold tests on protein_1, trains on protein_2
        assert len(test_idx) == 2  # protein_1 has 2 samples
        assert len(train_idx) == 2  # protein_2 has 2 samples

    def test_num_folds(self, sample_bioformbench_csv):
        """Test LOPO num_folds."""
        df = pd.read_csv(sample_bioformbench_csv)
        splitter = LeaveOneProteinOut(df)

        assert splitter.num_folds() == 2


class TestRandomSplit:
    """Test random train/test split protocol."""

    def test_random_split_ratio(self, sample_bioformbench_csv):
        """Test random split respects train/test ratio."""
        df = pd.read_csv(sample_bioformbench_csv)
        splitter = RandomSplit(train_ratio=0.75)

        train_idx, test_idx = splitter.split(df)

        # 75% train, 25% test
        assert len(train_idx) == 3
        assert len(test_idx) == 1

    def test_random_split_reproducibility(self, sample_bioformbench_csv):
        """Test random split is reproducible with same seed."""
        df = pd.read_csv(sample_bioformbench_csv)
        splitter1 = RandomSplit(random_state=42)
        splitter2 = RandomSplit(random_state=42)

        train1, test1 = splitter1.split(df)
        train2, test2 = splitter2.split(df)

        assert np.array_equal(train1, train2)
        assert np.array_equal(test1, test2)


class TestFewShotEval:
    """Test few-shot evaluation protocol."""

    def test_few_shot_indices(self, sample_bioformbench_csv):
        """Test few-shot conditioning indices."""
        df = pd.read_csv(sample_bioformbench_csv)
        evaluator = FewShotEval(n_shots=1)

        shot_idx, test_idx = evaluator.get_shot_indices(df, "protein_1")

        # protein_1 has 2 samples, 1 for shots, 1 for test
        assert len(shot_idx) + len(test_idx) == 2

    def test_few_shot_not_overlapping(self, sample_bioformbench_csv):
        """Test few-shot conditioning and test sets don't overlap."""
        df = pd.read_csv(sample_bioformbench_csv)
        evaluator = FewShotEval(n_shots=1)

        shot_idx, test_idx = evaluator.get_shot_indices(df, "protein_1")

        # No overlap between conditioning and test
        assert len(set(shot_idx) & set(test_idx)) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
