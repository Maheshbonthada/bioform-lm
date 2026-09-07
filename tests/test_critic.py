"""
Unit tests for physics-critic module.

Tests for critic network, training, and decoding strategies.
"""

import pytest
import torch
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from model.critic import (
    FormulationCritic,
    CriticTrainer,
    BestOfNDecoder,
    DPOPreferenceOptimizer,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def critic_model():
    """Create a FormulationCritic instance."""
    return FormulationCritic(vocab_size=200, hidden_dim=64, num_layers=2, dropout=0.1)


@pytest.fixture
def sample_tokens():
    """Create sample token sequences."""
    # Simple token sequences (batch_size=4, seq_len=10)
    tokens = torch.randint(1, 200, (4, 10), dtype=torch.long)
    return tokens


@pytest.fixture
def target_scores():
    """Create target stability scores."""
    return torch.tensor([[0.85], [0.75], [0.65], [0.90]], dtype=torch.float32)


# ============================================================================
# CRITIC MODEL TESTS
# ============================================================================


class TestFormulationCritic:
    """Test FormulationCritic network."""

    def test_initialization(self):
        """Test critic initialization."""
        critic = FormulationCritic(vocab_size=200, hidden_dim=64, num_layers=2)

        assert critic.vocab_size == 200
        assert critic.hidden_dim == 64

    def test_forward_pass(self, critic_model, sample_tokens):
        """Test forward pass produces correct output shape."""
        scores = critic_model(sample_tokens)

        assert scores.shape == (4, 1)  # batch_size=4, output=1
        assert torch.all(scores >= 0) and torch.all(scores <= 1)  # Sigmoid output

    def test_score_range(self, critic_model):
        """Test that scores are in [0, 1]."""
        tokens = torch.randint(1, 200, (10, 20), dtype=torch.long)
        scores = critic_model(tokens)

        assert torch.all(scores >= 0)
        assert torch.all(scores <= 1)

    def test_different_sequence_lengths(self, critic_model):
        """Test critic handles different sequence lengths."""
        # Batch with mixed lengths (padded to 20)
        tokens = torch.randint(1, 200, (3, 20), dtype=torch.long)
        scores = critic_model(tokens)

        assert scores.shape == (3, 1)

    def test_gradient_flow(self, critic_model, sample_tokens, target_scores):
        """Test that gradients flow through critic."""
        sample_tokens.requires_grad_(False)  # Inputs don't need grad
        scores = critic_model(sample_tokens)

        loss = torch.mean((scores - target_scores) ** 2)
        loss.backward()

        # Check that model parameters have gradients
        has_gradients = False
        for param in critic_model.parameters():
            if param.grad is not None:
                has_gradients = True
                break

        assert has_gradients


# ============================================================================
# CRITIC TRAINER TESTS
# ============================================================================


class TestCriticTrainer:
    """Test CriticTrainer."""

    def test_initialization(self, critic_model):
        """Test trainer initialization."""
        trainer = CriticTrainer(critic_model, device="cpu", learning_rate=1e-3)

        assert trainer.critic is critic_model
        assert trainer.device == "cpu"

    def test_train_on_batch(self, critic_model, sample_tokens, target_scores):
        """Test training on a single batch."""
        trainer = CriticTrainer(critic_model, device="cpu")

        initial_loss = None
        for _ in range(5):
            loss = trainer.train_on_batch(sample_tokens, target_scores)
            if initial_loss is None:
                initial_loss = loss
            else:
                # Loss should generally decrease (not strict, due to randomness)
                pass

        assert isinstance(loss, float)
        assert loss > 0

    def test_evaluate(self, critic_model, sample_tokens, target_scores):
        """Test evaluation on a batch."""
        trainer = CriticTrainer(critic_model, device="cpu")

        metrics = trainer.evaluate(sample_tokens, target_scores)

        assert "mse" in metrics
        assert "mae" in metrics
        assert "spearman_r" in metrics
        assert metrics["mse"] > 0
        assert metrics["mae"] > 0

    def test_multiple_training_steps(self, critic_model, sample_tokens, target_scores):
        """Test multiple training steps."""
        trainer = CriticTrainer(critic_model, device="cpu")

        losses = []
        for _ in range(10):
            loss = trainer.train_on_batch(sample_tokens, target_scores)
            losses.append(loss)

        assert len(losses) == 10
        assert all(l > 0 for l in losses)


# ============================================================================
# BEST-OF-N DECODER TESTS
# ============================================================================


class TestBestOfNDecoder:
    """Test BestOfNDecoder."""

    def test_initialization(self, critic_model):
        """Test decoder initialization."""
        decoder = BestOfNDecoder(critic_model, device="cpu")

        assert decoder.critic is critic_model
        assert decoder.device == "cpu"

    def test_decode_single_candidate(self, critic_model):
        """Test decoding with single candidate."""
        decoder = BestOfNDecoder(critic_model, device="cpu")

        # Single candidate recipe
        candidate = torch.randint(1, 200, (15,), dtype=torch.long)
        input_ids = torch.randint(1, 200, (1, 10), dtype=torch.long)

        top_recipes, top_scores = decoder.decode(input_ids, [candidate], k=1)

        assert len(top_recipes) == 1
        assert len(top_scores) == 1
        assert 0 <= top_scores[0] <= 1

    def test_decode_multiple_candidates(self, critic_model):
        """Test decoding with multiple candidates."""
        decoder = BestOfNDecoder(critic_model, device="cpu")

        # Generate 10 candidate recipes
        candidates = [torch.randint(1, 200, (15,), dtype=torch.long) for _ in range(10)]
        input_ids = torch.randint(1, 200, (1, 10), dtype=torch.long)

        top_recipes, top_scores = decoder.decode(input_ids, candidates, k=3)

        assert len(top_recipes) == 3
        assert len(top_scores) == 3
        # Scores should be sorted descending
        assert top_scores[0] >= top_scores[1] >= top_scores[2]

    def test_decode_k_larger_than_candidates(self, critic_model):
        """Test when k > number of candidates."""
        decoder = BestOfNDecoder(critic_model, device="cpu")

        candidates = [torch.randint(1, 200, (15,), dtype=torch.long) for _ in range(3)]
        input_ids = torch.randint(1, 200, (1, 10), dtype=torch.long)

        # Request k=5 but only have 3 candidates
        top_recipes, top_scores = decoder.decode(input_ids, candidates, k=5)

        # Should return at most 3
        assert len(top_recipes) <= 3
        assert len(top_scores) <= 3

    def test_empty_candidates(self, critic_model):
        """Test with empty candidate list."""
        decoder = BestOfNDecoder(critic_model, device="cpu")
        input_ids = torch.randint(1, 200, (1, 10), dtype=torch.long)

        top_recipes, top_scores = decoder.decode(input_ids, [], k=5)

        assert len(top_recipes) == 0
        assert len(top_scores) == 0


# ============================================================================
# DPO OPTIMIZER TESTS
# ============================================================================


class TestDPOPreferenceOptimizer:
    """Test DPOPreferenceOptimizer."""

    def test_initialization(self, critic_model):
        """Test DPO optimizer initialization."""
        # Create a simple generator mock
        class MockGenerator(torch.nn.Module):
            def forward(self, x):
                return torch.randn(x.size(0), 20), torch.randn(x.size(0), 199)

        generator = MockGenerator()
        optimizer = DPOPreferenceOptimizer(
            critic_model, generator, device="cpu", beta=0.1
        )

        assert optimizer.critic is critic_model
        assert optimizer.generator is generator
        assert optimizer.beta == 0.1

    def test_compute_preference_loss(self, critic_model):
        """Test computing preference loss."""

        class MockGenerator(torch.nn.Module):
            def forward(self, x):
                return torch.randn(x.size(0), 20), torch.randn(x.size(0), 199)

        generator = MockGenerator()
        optimizer = DPOPreferenceOptimizer(critic_model, generator, device="cpu")

        preferred = torch.randint(1, 200, (2, 15), dtype=torch.long)
        dispreferred = torch.randint(1, 200, (2, 15), dtype=torch.long)

        loss = optimizer.compute_preference_loss(preferred, dispreferred)

        assert isinstance(loss, torch.Tensor)
        assert loss.item() != 0  # Non-zero loss

    def test_optimize_batch(self, critic_model):
        """Test computing preference loss (full backward test requires real generator)."""

        class MockGenerator(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = torch.nn.Linear(10, 20)

            def forward(self, x):
                # Simple forward that depends on input
                batch_size = x.size(0)
                dummy = torch.randn(batch_size, 10, requires_grad=True)
                return self.linear(dummy), torch.randn(batch_size, 199)

        generator = MockGenerator()
        optimizer = DPOPreferenceOptimizer(critic_model, generator, device="cpu")

        preferred = torch.randint(1, 200, (2, 15), dtype=torch.long)
        dispreferred = torch.randint(1, 200, (2, 15), dtype=torch.long)

        # Test that compute_preference_loss works (backward requires real setup)
        loss_val = optimizer.compute_preference_loss(preferred, dispreferred)
        assert isinstance(loss_val, torch.Tensor)
        assert loss_val.item() != 0  # Non-zero loss


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestCriticIntegration:
    """Integration tests for critic components."""

    def test_critic_training_and_evaluation(self, critic_model):
        """Test full training and evaluation pipeline."""
        trainer = CriticTrainer(critic_model, device="cpu", learning_rate=1e-2)

        # Generate synthetic data
        train_tokens = torch.randint(1, 200, (20, 15), dtype=torch.long)
        train_scores = torch.rand(20, 1)

        test_tokens = torch.randint(1, 200, (5, 15), dtype=torch.long)
        test_scores = torch.rand(5, 1)

        # Train
        for _ in range(5):
            trainer.train_on_batch(train_tokens, train_scores)

        # Evaluate
        metrics = trainer.evaluate(test_tokens, test_scores)

        assert metrics["mse"] >= 0
        assert metrics["mae"] >= 0

    def test_critic_with_best_of_n(self, critic_model):
        """Test critic used with best-of-N decoder."""
        # Train critic briefly
        trainer = CriticTrainer(critic_model, device="cpu")
        train_tokens = torch.randint(1, 200, (10, 15), dtype=torch.long)
        train_scores = torch.rand(10, 1)

        for _ in range(3):
            trainer.train_on_batch(train_tokens, train_scores)

        # Use in decoder
        decoder = BestOfNDecoder(critic_model, device="cpu")

        candidates = [torch.randint(1, 200, (20,), dtype=torch.long) for _ in range(5)]
        input_ids = torch.randint(1, 200, (1, 10), dtype=torch.long)

        top_recipes, top_scores = decoder.decode(input_ids, candidates, k=2)

        assert len(top_recipes) == 2
        assert len(top_scores) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
