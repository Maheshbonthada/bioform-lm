"""
Unit tests for baseline models.

Tests for predictive baselines (RF/SVM/MLP) and ablation harnesses.
"""

import pytest
import numpy as np
import torch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.baselines import (
    FeatureExtractor,
    RandomForestBaseline,
    SVMBaseline,
    MLPBaseline,
    NoInContextAblation,
    NoCriticAblation,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_data():
    """Create sample protein/formulation data."""
    proteins = [
        {"mw_kda": 100.0, "pi": 7.0, "tm_baseline_c": 65.0},
        {"mw_kda": 50.0, "pi": 6.5, "tm_baseline_c": 60.0},
        {"mw_kda": 150.0, "pi": 7.5, "tm_baseline_c": 70.0},
        {"mw_kda": 75.0, "pi": 7.2, "tm_baseline_c": 62.0},
        {"mw_kda": 120.0, "pi": 6.8, "tm_baseline_c": 68.0},
    ]

    formulations = [
        {
            "buffer_species": "histidine",
            "ph": 6.0,
            "ionic_strength_mm": 150.0,
            "osmolarity_mosm_kg": 310.0,
            "temperature_c": 25.0,
            "stabilizers": {"sucrose": 5.0},
        },
        {
            "buffer_species": "phosphate",
            "ph": 7.0,
            "ionic_strength_mm": 200.0,
            "osmolarity_mosm_kg": 350.0,
            "temperature_c": 4.0,
            "stabilizers": {"trehalose": 10.0},
        },
        {
            "buffer_species": "acetate",
            "ph": 5.5,
            "ionic_strength_mm": 100.0,
            "osmolarity_mosm_kg": 280.0,
            "temperature_c": 25.0,
            "stabilizers": {},
        },
        {
            "buffer_species": "tris",
            "ph": 7.5,
            "ionic_strength_mm": 250.0,
            "osmolarity_mosm_kg": 380.0,
            "temperature_c": 25.0,
            "stabilizers": {"polysorbate_80": 0.5},
        },
        {
            "buffer_species": "histidine",
            "ph": 6.5,
            "ionic_strength_mm": 180.0,
            "osmolarity_mosm_kg": 320.0,
            "temperature_c": 25.0,
            "stabilizers": {"sucrose": 3.0, "polysorbate_20": 0.1},
        },
    ]

    samples = list(zip(proteins, formulations))
    targets = [0.85, 0.75, 0.65, 0.80, 0.90]  # Stability scores

    return samples, targets


# ============================================================================
# FEATURE EXTRACTOR TESTS
# ============================================================================


class TestFeatureExtractor:
    """Test feature extraction."""

    def test_extract_single_sample(self):
        """Test extracting features from single sample."""
        extractor = FeatureExtractor()

        protein = {"mw_kda": 100.0, "pi": 7.0, "tm_baseline_c": 65.0}
        formulation = {
            "buffer_species": "histidine",
            "ph": 6.0,
            "ionic_strength_mm": 150.0,
            "osmolarity_mosm_kg": 310.0,
            "temperature_c": 25.0,
            "stabilizers": {"sucrose": 5.0},
        }

        features = extractor.extract(protein, formulation)

        assert len(features) == 10  # 3 protein + 4 formulation base + 1 buffer + 1 num_stabs + 1 total_conc
        assert features.dtype == np.float32

    def test_extract_handles_missing_keys(self):
        """Test extraction with missing dict keys."""
        extractor = FeatureExtractor()

        protein = {"mw_kda": 100.0}  # Missing pi, tm_baseline_c
        formulation = {"ph": 6.0}  # Missing other params

        # Should not raise; uses defaults
        features = extractor.extract(protein, formulation)
        assert len(features) == 10

    def test_fit_transform_normalization(self, sample_data):
        """Test that fit_transform normalizes features."""
        samples, targets = sample_data
        extractor = FeatureExtractor()

        X = extractor.fit_transform(samples)

        assert X.shape == (5, 10)
        # After standardization, mean should be ~0, std ~1
        assert np.abs(X.mean()) < 0.1
        assert np.abs(X.std() - 1.0) < 0.3

    def test_transform_consistency(self, sample_data):
        """Test that transform is consistent after fit."""
        samples, targets = sample_data
        extractor = FeatureExtractor()

        # Fit on first 3 samples
        X_fit = extractor.fit_transform(samples[:3])
        assert X_fit.shape == (3, 10)

        # Transform all samples
        X_transform = extractor.transform(samples)
        assert X_transform.shape == (5, 10)


# ============================================================================
# RANDOM FOREST BASELINE TESTS
# ============================================================================


class TestRandomForestBaseline:
    """Test RF baseline."""

    def test_fit_and_predict(self, sample_data):
        """Test RF training and prediction."""
        samples, targets = sample_data
        baseline = RandomForestBaseline(n_estimators=10)

        baseline.fit(samples, targets)
        predictions = baseline.predict(samples)

        assert predictions.shape == (5,)
        assert np.all((predictions >= 0) & (predictions <= 19))  # Valid bin range

    def test_predict_proba(self, sample_data):
        """Test RF probability prediction."""
        samples, targets = sample_data
        baseline = RandomForestBaseline(n_estimators=5)

        baseline.fit(samples, targets)
        proba = baseline.predict_proba(samples)

        # proba should be [n_samples, n_classes] where n_classes <= 20
        assert proba.shape[0] == 5
        assert proba.shape[1] <= 20
        # Probabilities should sum to 1 for each sample
        assert np.allclose(proba.sum(axis=1), 1.0)

    def test_predict_without_fit_raises(self):
        """Test that predict raises error before fitting."""
        baseline = RandomForestBaseline()
        samples = [
            ({"mw_kda": 100.0, "pi": 7.0, "tm_baseline_c": 65.0}, {"ph": 6.0})
        ]

        with pytest.raises(ValueError):
            baseline.predict(samples)

    def test_reproducibility(self, sample_data):
        """Test RF with fixed seed gives same results."""
        samples, targets = sample_data

        baseline1 = RandomForestBaseline(n_estimators=10, random_state=42)
        baseline1.fit(samples, targets)
        pred1 = baseline1.predict(samples)

        baseline2 = RandomForestBaseline(n_estimators=10, random_state=42)
        baseline2.fit(samples, targets)
        pred2 = baseline2.predict(samples)

        assert np.array_equal(pred1, pred2)


# ============================================================================
# SVM BASELINE TESTS
# ============================================================================


class TestSVMBaseline:
    """Test SVM baseline."""

    def test_fit_and_predict(self, sample_data):
        """Test SVM training and prediction."""
        samples, targets = sample_data
        baseline = SVMBaseline(kernel="rbf")

        baseline.fit(samples, targets)
        predictions = baseline.predict(samples)

        assert predictions.shape == (5,)
        assert np.all((predictions >= 0) & (predictions <= 19))

    def test_predict_proba(self, sample_data):
        """Test SVM probability prediction."""
        samples, targets = sample_data
        baseline = SVMBaseline(kernel="linear")

        baseline.fit(samples, targets)
        proba = baseline.predict_proba(samples)

        # proba should be [n_samples, n_classes] where n_classes <= 20
        assert proba.shape[0] == 5
        assert proba.shape[1] <= 20
        # Probabilities should sum to 1 for each sample
        assert np.allclose(proba.sum(axis=1), 1.0)

    def test_different_kernels(self, sample_data):
        """Test SVM with different kernels."""
        samples, targets = sample_data

        for kernel in ["linear", "rbf"]:
            baseline = SVMBaseline(kernel=kernel)
            baseline.fit(samples, targets)
            predictions = baseline.predict(samples)

            assert predictions.shape == (5,)


# ============================================================================
# MLP BASELINE TESTS
# ============================================================================


class TestMLPBaseline:
    """Test MLP baseline."""

    def test_forward_pass(self):
        """Test MLP forward pass."""
        mlp = MLPBaseline(input_dim=10, hidden_dim=64, num_classes=20)

        X = torch.randn(5, 10)
        logits = mlp(X)

        assert logits.shape == (5, 20)

    def test_fit_and_predict(self, sample_data):
        """Test MLP training and prediction."""
        samples, targets = sample_data
        mlp = MLPBaseline(input_dim=10, hidden_dim=64, num_classes=20)

        mlp.fit(samples, targets, epochs=10, batch_size=2, device="cpu")
        predictions = mlp.predict(samples, device="cpu")

        assert predictions.shape == (5,)
        assert np.all((predictions >= 0) & (predictions <= 19))

    def test_multiple_epochs(self, sample_data):
        """Test MLP trains for multiple epochs without error."""
        samples, targets = sample_data
        mlp = MLPBaseline(input_dim=10, hidden_dim=32, num_classes=20)

        # Should complete without error
        mlp.fit(samples, targets, epochs=20, batch_size=2, device="cpu")


# ============================================================================
# ABLATION HARNESS TESTS
# ============================================================================


class TestAblations:
    """Test ablation harnesses."""

    def test_no_in_context_ablation(self):
        """Test no-in-context ablation harness."""
        ablation = NoInContextAblation()
        note = ablation.note()

        assert "no few-shot" in note.lower()
        assert "synthetic" in note.lower()

    def test_no_critic_ablation(self):
        """Test no-critic ablation harness."""
        ablation = NoCriticAblation()
        note = ablation.note()

        assert "no critic" in note.lower() or "without critic" in note.lower()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestBaselineIntegration:
    """Integration tests comparing baselines."""

    def test_all_baselines_on_same_data(self, sample_data):
        """Test all baselines on same training data."""
        samples, targets = sample_data

        # RF
        rf = RandomForestBaseline(n_estimators=5)
        rf.fit(samples, targets)
        rf_pred = rf.predict(samples)

        # SVM
        svm = SVMBaseline()
        svm.fit(samples, targets)
        svm_pred = svm.predict(samples)

        # MLP
        mlp = MLPBaseline()
        mlp.fit(samples, targets, epochs=5, batch_size=2, device="cpu")
        mlp_pred = mlp.predict(samples, device="cpu")

        # All should produce valid predictions
        assert rf_pred.shape == (5,)
        assert svm_pred.shape == (5,)
        assert mlp_pred.shape == (5,)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
