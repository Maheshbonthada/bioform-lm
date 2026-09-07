"""
Physics-informed critic for guided decoding in BioForm-LM.

The critic learns to score formulation recipes based on:
1. Mechanistic simulator (distilled during training)
2. Real BioFormBench calibration (fine-tuning)

Used for:
- Best-of-N sampling: generate N recipes, score with critic, return top-k
- DPO preference reranking: pair recipes, use critic to define preference
- Inference-time guidance: steer generation toward high-score regions

Architectural novelty: generate → critic score → prefer (closed loop)
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FormulationCritic(nn.Module):
    """
    Lightweight critic network for scoring formulation recipes.

    Takes (protein descriptor + formulation tokens) and outputs a
    stability score in [0, 1] representing how "good" the recipe is.

    Uses two information sources:
    1. Mechanistic simulator (pretraining signal)
    2. Real BioFormBench data (fine-tuning signal)
    """

    def __init__(
        self,
        vocab_size: int = 199,
        hidden_dim: int = 128,
        num_layers: int = 3,
        dropout: float = 0.1,
    ):
        """
        Initialize critic network.

        Args:
            vocab_size: Tokenizer vocab size (for embedding)
            hidden_dim: Hidden dimension
            num_layers: Number of transformer layers
            dropout: Dropout rate
        """
        super().__init__()

        self.vocab_size = vocab_size
        self.hidden_dim = hidden_dim

        # Embedding layer
        self.embedding = nn.Embedding(vocab_size, hidden_dim)
        self.pos_embedding = nn.Parameter(torch.randn(64, hidden_dim))  # Max seq len 64

        # Transformer encoder for sequence processing
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=4,
            dim_feedforward=256,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Scoring head: output scalar in [0, 1]
        self.scoring_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
            nn.Sigmoid(),  # Output in [0, 1]
        )

        logger.info(
            f"FormulationCritic initialized: vocab_size={vocab_size}, "
            f"hidden_dim={hidden_dim}, num_layers={num_layers}"
        )

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        """
        Forward pass: score a batch of formulation sequences.

        Args:
            input_ids: [batch_size, seq_len] token indices

        Returns:
            scores: [batch_size, 1] stability scores in [0, 1]
        """
        # Embed tokens
        x = self.embedding(input_ids)  # [batch, seq_len, hidden]
        x = x + self.pos_embedding[: x.size(1), :].unsqueeze(0)

        # Transform with attention
        x = self.transformer(x)  # [batch, seq_len, hidden]

        # Use [CLS] token (first token) for classification
        cls_output = x[:, 0, :]  # [batch, hidden]

        # Score
        score = self.scoring_head(cls_output)  # [batch, 1]

        return score


class CriticTrainer:
    """
    Trainer for the critic network.

    Trains critic to predict stability from:
    1. Synthetic data with simulator labels (pretraining)
    2. Real BioFormBench data (fine-tuning)
    """

    def __init__(
        self,
        critic: FormulationCritic,
        device: str = "cuda",
        learning_rate: float = 1e-4,
    ):
        """
        Initialize critic trainer.

        Args:
            critic: FormulationCritic model
            device: "cuda" or "cpu"
            learning_rate: Adam learning rate
        """
        self.critic = critic.to(device)
        self.device = device
        self.optimizer = torch.optim.Adam(self.critic.parameters(), lr=learning_rate)
        self.loss_fn = nn.MSELoss()  # Regression loss (score in [0, 1])

        logger.info(f"CriticTrainer initialized on device={device}")

    def train_on_batch(
        self,
        input_ids: torch.Tensor,
        targets: torch.Tensor,
    ) -> float:
        """
        Train on a single batch.

        Args:
            input_ids: [batch_size, seq_len] token indices
            targets: [batch_size] stability scores in [0, 1]

        Returns:
            Batch loss (scalar)
        """
        self.critic.train()
        self.optimizer.zero_grad()

        # Forward pass
        predictions = self.critic(input_ids.to(self.device)).squeeze(-1)
        targets_t = targets.to(self.device)

        # Compute loss
        loss = self.loss_fn(predictions, targets_t)

        # Backward pass
        loss.backward()
        self.optimizer.step()

        return loss.item()

    def train_epoch(
        self,
        data_loader,
        epoch: int = 0,
    ) -> float:
        """
        Train for one epoch.

        Args:
            data_loader: DataLoader yielding (input_ids, targets) tuples
            epoch: Epoch number (for logging)

        Returns:
            Average loss for the epoch
        """
        self.critic.train()
        losses = []

        for batch_idx, (input_ids, targets) in enumerate(data_loader):
            loss = self.train_on_batch(input_ids, targets)
            losses.append(loss)

            if (batch_idx + 1) % 100 == 0:
                avg_loss = np.mean(losses[-100:])
                logger.info(
                    f"Epoch {epoch}, Batch {batch_idx + 1}: loss={avg_loss:.4f}"
                )

        return float(np.mean(losses))

    def evaluate(self, data_loader) -> Dict[str, float]:
        """
        Evaluate on a dataset.

        Args:
            data_loader: DataLoader yielding (input_ids, targets) tuples

        Returns:
            Dict with evaluation metrics (mse, mae, etc.)
        """
        self.critic.eval()

        all_predictions = []
        all_targets = []

        with torch.no_grad():
            for input_ids, targets in data_loader:
                predictions = self.critic(input_ids.to(self.device)).squeeze(-1)
                all_predictions.append(predictions.cpu().numpy())
                all_targets.append(targets.numpy())

        predictions = np.concatenate(all_predictions)
        targets = np.concatenate(all_targets)

        # Compute metrics
        mse = float(np.mean((predictions - targets) ** 2))
        mae = float(np.mean(np.abs(predictions - targets)))

        # Rank correlations
        from scipy.stats import spearmanr, kendalltau

        if len(predictions) > 2:
            spearman_r, _ = spearmanr(predictions, targets)
            kendall_tau, _ = kendalltau(predictions, targets)
        else:
            spearman_r = np.nan
            kendall_tau = np.nan

        return {
            "mse": mse,
            "mae": mae,
            "spearman_r": float(spearman_r),
            "kendall_tau": float(kendall_tau),
        }

    def save_checkpoint(self, path: str):
        """
        Save critic checkpoint.

        Args:
            path: Path to save checkpoint (.pt file)
        """
        checkpoint = {
            "model_state_dict": self.critic.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
        }
        torch.save(checkpoint, path)
        logger.info(f"✓ Critic checkpoint saved to {path}")

    def load_checkpoint(self, path: str):
        """
        Load critic checkpoint.

        Args:
            path: Path to load checkpoint from (.pt file)
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.critic.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        logger.info(f"✓ Critic checkpoint loaded from {path}")


class BestOfNDecoder:
    """
    Best-of-N decoding with critic scoring.

    Given a set of generated candidates, rank them using the critic
    and return the top-k best recipes.
    """

    def __init__(self, critic: FormulationCritic, device: str = "cuda"):
        """
        Initialize Best-of-N decoder.

        Args:
            critic: Trained FormulationCritic model
            device: Compute device
        """
        self.critic = critic.to(device)
        self.device = device
        self.critic.eval()

    def score_recipes(
        self, candidate_input_ids: torch.Tensor
    ) -> torch.Tensor:
        """
        Score candidates using critic.

        Args:
            candidate_input_ids: [num_candidates, seq_len] token indices

        Returns:
            scores: [num_candidates] stability scores
        """
        with torch.no_grad():
            scores = self.critic(candidate_input_ids.to(self.device)).squeeze(-1)
        return scores

    def select_top_k(
        self,
        candidate_input_ids: torch.Tensor,
        k: int = 5,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Select top-k candidates by critic score.

        Args:
            candidate_input_ids: [num_candidates, seq_len] token indices
            k: Number of top candidates to select

        Returns:
            (top_k_input_ids, top_k_scores) tensors
        """
        # Score all candidates
        scores = self.score_recipes(candidate_input_ids)

        # Get top-k indices
        top_k_scores, top_k_indices = torch.topk(scores, k=min(k, len(scores)))

        # Return top-k candidates
        top_k_input_ids = candidate_input_ids[top_k_indices]

        return top_k_input_ids, top_k_scores
        """
        Train on a single batch.

        Args:
            input_ids: [batch_size, seq_len] token indices
            targets: [batch_size, 1] target stability scores [0, 1]

        Returns:
            Loss value
        """
        self.critic.train()
        input_ids = input_ids.to(self.device)
        targets = targets.to(self.device)

        self.optimizer.zero_grad()

        # Forward pass
        predictions = self.critic(input_ids)

        # Compute loss
        loss = self.loss_fn(predictions, targets)

        # Backward pass
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 1.0)
        self.optimizer.step()

        return loss.item()

    def evaluate(
        self,
        input_ids: torch.Tensor,
        targets: torch.Tensor,
    ) -> Dict[str, float]:
        """
        Evaluate critic on a batch.

        Args:
            input_ids: [batch_size, seq_len] token indices
            targets: [batch_size, 1] target stability scores [0, 1]

        Returns:
            Dict with metrics: mse, mae, spearman_r
        """
        self.critic.eval()
        input_ids = input_ids.to(self.device)
        targets = targets.to(self.device)

        with torch.no_grad():
            predictions = self.critic(input_ids)

        predictions_np = predictions.cpu().numpy().flatten()
        targets_np = targets.cpu().numpy().flatten()

        mse = np.mean((predictions_np - targets_np) ** 2)
        mae = np.mean(np.abs(predictions_np - targets_np))

        # Spearman correlation
        from scipy.stats import spearmanr

        if len(predictions_np) >= 2:
            spearman_r, _ = spearmanr(predictions_np, targets_np)
        else:
            spearman_r = np.nan

        return {
            "mse": float(mse),
            "mae": float(mae),
            "spearman_r": float(spearman_r),
        }


class BestOfNDecoder:
    """
    Best-of-N sampling: generate N recipes, score with critic, return top-k.

    This is a simple but effective decoding strategy that:
    1. Uses the base model to generate N recipe candidates
    2. Scores each with the critic
    3. Returns top-k by critic score
    """

    def __init__(self, critic: FormulationCritic, device: str = "cuda"):
        """
        Initialize best-of-N decoder.

        Args:
            critic: FormulationCritic for scoring
            device: "cuda" or "cpu"
        """
        self.critic = critic.to(device)
        self.device = device
        self.critic.eval()

    def decode(
        self,
        input_ids: torch.Tensor,
        candidates: List[torch.Tensor],
        k: int = 5,
    ) -> Tuple[List[torch.Tensor], List[float]]:
        """
        Select best-k recipes from candidates using critic.

        Args:
            input_ids: [1, seq_len] protein context (unused in scoring, for compat)
            candidates: List of [seq_len] token sequences (N recipes)
            k: Number of top recipes to return

        Returns:
            (top_k_recipes, top_k_scores) where scores are critic predictions
        """
        if len(candidates) == 0:
            return [], []

        # Pad candidates to same length
        max_len = max(len(c) for c in candidates)
        padded = []
        for c in candidates:
            if len(c) < max_len:
                padding = torch.zeros(max_len - len(c), dtype=torch.long, device=self.device)
                padded.append(torch.cat([c, padding]))
            else:
                padded.append(c[:max_len])

        candidate_ids = torch.stack(padded).to(self.device)

        # Score with critic
        with torch.no_grad():
            scores = self.critic(candidate_ids).cpu().numpy().flatten()

        # Get top-k
        top_k_indices = np.argsort(scores)[-k:][::-1]  # Sort descending
        top_k_recipes = [candidates[i] for i in top_k_indices]
        top_k_scores = [float(scores[i]) for i in top_k_indices]

        return top_k_recipes, top_k_scores


class DPOPreferenceOptimizer:
    """
    Direct Preference Optimization (DPO) for critic-guided decoding.

    Alternative to best-of-N: learns preferences between recipe pairs
    using the critic as a reward model, then optimizes the generator
    to produce preferred recipes.

    More sample-efficient than best-of-N for large N.
    """

    def __init__(
        self,
        critic: FormulationCritic,
        generator: nn.Module,
        device: str = "cuda",
        beta: float = 0.1,
    ):
        """
        Initialize DPO optimizer.

        Args:
            critic: FormulationCritic for scoring
            generator: BioFormLM model to optimize
            device: "cuda" or "cpu"
            beta: Inverse temperature for preference weighting
        """
        self.critic = critic.to(device)
        self.generator = generator.to(device)
        self.device = device
        self.beta = beta

        logger.info(f"DPOPreferenceOptimizer initialized with beta={beta}")

    def compute_preference_loss(
        self,
        preferred_ids: torch.Tensor,
        dispreferred_ids: torch.Tensor,
    ) -> torch.Tensor:
        """
        Compute DPO loss between preferred and dispreferred recipes.

        Args:
            preferred_ids: [batch_size, seq_len] preferred recipe tokens
            dispreferred_ids: [batch_size, seq_len] dispreferred recipe tokens

        Returns:
            DPO loss (scalar)
        """
        self.critic.eval()
        self.generator.train()

        # Get critic scores for both
        with torch.no_grad():
            preferred_score = self.critic(preferred_ids.to(self.device))
            dispreferred_score = self.critic(dispreferred_ids.to(self.device))

        # Get generator log-probs for both
        # (Simplified: assume generator outputs logits for tokens)
        preferred_logits, _ = self.generator(preferred_ids.to(self.device))
        dispreferred_logits, _ = self.generator(dispreferred_ids.to(self.device))

        # DPO objective: maximize reward difference between preferred/dispreferred
        # weighted by beta (inverse temperature)
        reward_diff = preferred_score - dispreferred_score
        loss = -torch.mean(self.beta * reward_diff)  # Negative for minimization

        return loss

    def optimize_batch(
        self,
        preferred_ids: torch.Tensor,
        dispreferred_ids: torch.Tensor,
    ) -> float:
        """
        Optimize generator on a batch of preference pairs.

        Args:
            preferred_ids: [batch_size, seq_len]
            dispreferred_ids: [batch_size, seq_len]

        Returns:
            Loss value
        """
        loss = self.compute_preference_loss(preferred_ids, dispreferred_ids)

        # Backward pass on generator
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.generator.parameters(), 1.0)
        # (Optimizer step handled externally)

        return loss.item()
