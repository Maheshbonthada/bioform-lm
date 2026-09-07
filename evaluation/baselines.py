"""
Baseline models for comparison against BioForm-LM.

Implements three types of baselines:
1. ExPreSo-style predictive classifiers (RF/SVM/MLP)
   - Predict stability given protein + formulation features
   - No generative component (predict-only)
2. No-in-context ablation
   - BioFormLM trained only on synthetic, no few-shot real-data conditioning
3. No-critic ablation
   - BioFormLM with recipe generation head, no physics-critic guidance

These establish what performance improvement comes from:
- Generative design vs predictive classification
- In-context few-shot learning
- Physics-informed critic guidance
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import logging

from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


# ============================================================================
# PREDICTIVE BASELINES (ExPreSo-style)
# ============================================================================


class FeatureExtractor:
    """
    Extract feature vectors from protein and formulation dicts.

    Features: normalized protein descriptors + quantized formulation params.
    """

    def __init__(self):
        """Initialize feature extractor."""
        self.scaler = StandardScaler()
        self.is_fitted = False

    def extract(self, protein_dict: Dict, formulation_dict: Dict) -> np.ndarray:
        """
        Extract feature vector.

        Args:
            protein_dict: {mw_kda, pi, tm_baseline_c}
            formulation_dict: {buffer_species, ph, ionic_strength_mm, osmolarity_mosm_kg, ...}

        Returns:
            Feature vector (numpy array)
        """
        features = []

        # Protein features (3)
        features.append(protein_dict.get("mw_kda", 50.0))  # MW in kDa
        features.append(protein_dict.get("pi", 7.0))  # pI
        features.append(protein_dict.get("tm_baseline_c", 60.0))  # Tm in Celsius

        # Formulation features (6)
        features.append(formulation_dict.get("ph", 7.0))  # pH
        features.append(formulation_dict.get("ionic_strength_mm", 150.0))  # IS
        features.append(formulation_dict.get("osmolarity_mosm_kg", 300.0))  # Osmol
        features.append(formulation_dict.get("temperature_c", 25.0))  # Temperature

        # Buffer species as categorical (one-hot would be too sparse, use ordinal)
        buffer_map = {
            "histidine": 0,
            "phosphate": 1,
            "acetate": 2,
            "citrate": 3,
        }
        buffer_species = formulation_dict.get("buffer_species", "histidine").lower()
        features.append(float(buffer_map.get(buffer_species, 0)))

        # Stabilizer count
        stabilizers_str = formulation_dict.get("stabilizers_json", "{}")
        try:
            # Try to parse as JSON if stored that way
            if isinstance(stabilizers_str, str) and stabilizers_str.startswith("{"):
                stabilizers = len(stabilizers_str.split(","))
            else:
                stabilizers = 0
        except:
            stabilizers = 0
        features.append(float(stabilizers))

        return np.array(features, dtype=np.float32)

    def fit(self, proteins: List[Dict], formulations: List[Dict], labels: np.ndarray):
        """
        Fit feature scaler on training data.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations
            labels: Array of target labels
        """
        X = np.array([
            self.extract(p, f)
            for p, f in zip(proteins, formulations)
        ])
        self.scaler.fit(X)
        self.is_fitted = True

    def transform(self, proteins: List[Dict], formulations: List[Dict]) -> np.ndarray:
        """
        Transform feature vectors using fitted scaler.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations

        Returns:
            Scaled feature matrix
        """
        if not self.is_fitted:
            raise ValueError("FeatureExtractor must be fit before transform")

        X = np.array([
            self.extract(p, f)
            for p, f in zip(proteins, formulations)
        ])
        return self.scaler.transform(X)


# ============================================================================
# PREDICTIVE BASELINES
# ============================================================================


class RandomForestPredictor:
    """Random Forest classifier baseline."""

    def __init__(self, n_estimators: int = 100, random_state: int = 42):
        """
        Initialize RandomForestPredictor.

        Args:
            n_estimators: Number of trees
            random_state: Random seed
        """
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
        self.feature_extractor = FeatureExtractor()
        self.is_trained = False

    def train(
        self,
        proteins: List[Dict],
        formulations: List[Dict],
        labels: np.ndarray,
    ):
        """
        Train Random Forest on stability classification.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations
            labels: Binary labels (0 = unstable, 1 = stable)
        """
        logger.info("Training RandomForest baseline...")

        # Fit feature scaler
        self.feature_extractor.fit(proteins, formulations, labels)

        # Extract and scale features
        X = self.feature_extractor.transform(proteins, formulations)

        # Train classifier
        self.model.fit(X, labels)
        self.is_trained = True

        logger.info(f"✓ RandomForest trained on {len(proteins)} samples")

    def predict(self, proteins: List[Dict], formulations: List[Dict]) -> np.ndarray:
        """
        Predict stability (probability of high stability).

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations

        Returns:
            Predicted probabilities in [0, 1]
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        X = self.feature_extractor.transform(proteins, formulations)
        return self.model.predict_proba(X)[:, 1]  # Probability of class 1 (stable)


class SVMPredictor:
    """Support Vector Machine classifier baseline."""

    def __init__(self, kernel: str = "rbf", random_state: int = 42):
        """
        Initialize SVMPredictor.

        Args:
            kernel: SVM kernel type
            random_state: Random seed
        """
        self.model = SVC(kernel=kernel, probability=True, random_state=random_state)
        self.feature_extractor = FeatureExtractor()
        self.is_trained = False

    def train(
        self,
        proteins: List[Dict],
        formulations: List[Dict],
        labels: np.ndarray,
    ):
        """
        Train SVM on stability classification.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations
            labels: Binary labels (0 = unstable, 1 = stable)
        """
        logger.info("Training SVM baseline...")

        # Fit feature scaler
        self.feature_extractor.fit(proteins, formulations, labels)

        # Extract and scale features
        X = self.feature_extractor.transform(proteins, formulations)

        # Train classifier
        self.model.fit(X, labels)
        self.is_trained = True

        logger.info(f"✓ SVM trained on {len(proteins)} samples")

    def predict(self, proteins: List[Dict], formulations: List[Dict]) -> np.ndarray:
        """
        Predict stability probability.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations

        Returns:
            Predicted probabilities in [0, 1]
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        X = self.feature_extractor.transform(proteins, formulations)
        return self.model.predict_proba(X)[:, 1]


class MLPPredictor(nn.Module):
    """Multilayer Perceptron baseline."""

    def __init__(self, input_dim: int = 9, hidden_dim: int = 64, dropout: float = 0.1):
        """
        Initialize MLPPredictor.

        Args:
            input_dim: Input feature dimension
            hidden_dim: Hidden layer dimension
            dropout: Dropout rate
        """
        super().__init__()

        self.feature_extractor = FeatureExtractor()
        self.input_dim = input_dim

        self.mlp = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),  # Output probability
        )

        self.is_trained = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: [batch_size, input_dim] feature matrix

        Returns:
            [batch_size, 1] predicted stability probabilities
        """
        return self.mlp(x)

    def train_model(
        self,
        proteins: List[Dict],
        formulations: List[Dict],
        labels: np.ndarray,
        epochs: int = 50,
        learning_rate: float = 1e-3,
        device: str = "cpu",
    ):
        """
        Train MLP baseline.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations
            labels: Binary labels
            epochs: Number of epochs
            learning_rate: Learning rate
            device: Compute device
        """
        logger.info("Training MLP baseline...")

        # Fit feature scaler
        self.feature_extractor.fit(proteins, formulations, labels)

        # Extract and scale features
        X = self.feature_extractor.transform(proteins, formulations)
        y = labels.astype(np.float32)

        # Convert to tensors
        X_tensor = torch.from_numpy(X).to(device)
        y_tensor = torch.from_numpy(y).reshape(-1, 1).to(device)

        # Move model to device
        self.to(device)
        self.train()

        # Training loop
        optimizer = torch.optim.Adam(self.parameters(), lr=learning_rate)
        criterion = nn.BCELoss()

        for epoch in range(epochs):
            optimizer.zero_grad()
            logits = self(X_tensor)
            loss = criterion(logits, y_tensor)
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 10 == 0:
                logger.info(f"  Epoch {epoch + 1}/{epochs}, Loss: {loss.item():.4f}")

        self.is_trained = True
        logger.info(f"✓ MLP trained for {epochs} epochs")

    def predict(
        self, proteins: List[Dict], formulations: List[Dict], device: str = "cpu"
    ) -> np.ndarray:
        """
        Predict stability probability.

        Args:
            proteins: List of protein descriptors
            formulations: List of formulations
            device: Compute device

        Returns:
            Predicted probabilities in [0, 1]
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        X = self.feature_extractor.transform(proteins, formulations)
        X_tensor = torch.from_numpy(X).to(device)

        self.eval()
        with torch.no_grad():
            predictions = self(X_tensor).cpu().numpy()

        return predictions.flatten()

    def fit_transform(self, samples: List[Tuple[Dict, Dict]]) -> np.ndarray:
        """
        Extract and normalize features for training.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples

        Returns:
            Normalized feature matrix
        """
        features_list = []
        for protein_dict, formulation_dict in samples:
            feat = self.extract(protein_dict, formulation_dict)
            features_list.append(feat)

        X = np.array(features_list, dtype=np.float32)
        X_scaled = self.scaler.fit_transform(X)
        self.is_fitted = True

        return X_scaled

    def transform(self, samples: List[Tuple[Dict, Dict]]) -> np.ndarray:
        """
        Extract and normalize features for inference.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples

        Returns:
            Normalized feature matrix
        """
        if not self.is_fitted:
            raise ValueError("Feature extractor not fitted. Call fit_transform first.")

        features_list = []
        for protein_dict, formulation_dict in samples:
            feat = self.extract(protein_dict, formulation_dict)
            features_list.append(feat)

        X = np.array(features_list, dtype=np.float32)
        return self.scaler.transform(X)


class RandomForestBaseline:
    """Random Forest baseline (predict stability from features)."""

    def __init__(self, n_estimators: int = 100, random_state: int = 42):
        """Initialize RF baseline."""
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model = None
        self.feature_extractor = FeatureExtractor()

    def fit(
        self,
        samples: List[Tuple[Dict, Dict]],
        targets: List[float],
    ) -> None:
        """
        Train random forest on (protein, formulation) → stability.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples
            targets: List of stability scores [0, 1]
        """
        X = self.feature_extractor.fit_transform(samples)
        y = np.array(targets, dtype=np.float32)

        # Quantize targets to 20 bins (match model's classification)
        y_bins = np.digitize(y, bins=np.linspace(0, 1, 20)) - 1
        y_bins = np.clip(y_bins, 0, 19)

        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(X, y_bins)

        logger.info(f"RandomForest trained on {len(samples)} samples")

    def predict(self, samples: List[Tuple[Dict, Dict]]) -> np.ndarray:
        """
        Predict stability bins for samples.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples

        Returns:
            Predicted stability bins [0-19]
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        X = self.feature_extractor.transform(samples)
        return self.model.predict(X)

    def predict_proba(self, samples: List[Tuple[Dict, Dict]]) -> np.ndarray:
        """
        Predict probability over stability bins.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples

        Returns:
            Predicted probabilities [batch_size, 20]
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        X = self.feature_extractor.transform(samples)
        return self.model.predict_proba(X)


class SVMBaseline:
    """Support Vector Machine baseline."""

    def __init__(self, kernel: str = "rbf", random_state: int = 42):
        """Initialize SVM baseline."""
        self.kernel = kernel
        self.random_state = random_state
        self.model = None
        self.feature_extractor = FeatureExtractor()

    def fit(
        self,
        samples: List[Tuple[Dict, Dict]],
        targets: List[float],
    ) -> None:
        """
        Train SVM on (protein, formulation) → stability.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples
            targets: List of stability scores [0, 1]
        """
        X = self.feature_extractor.fit_transform(samples)
        y = np.array(targets, dtype=np.float32)

        # Quantize targets to 20 bins
        y_bins = np.digitize(y, bins=np.linspace(0, 1, 20)) - 1
        y_bins = np.clip(y_bins, 0, 19)

        self.model = SVC(kernel=self.kernel, random_state=self.random_state, probability=True)
        self.model.fit(X, y_bins)

        logger.info(f"SVM ({self.kernel}) trained on {len(samples)} samples")

    def predict(self, samples: List[Tuple[Dict, Dict]]) -> np.ndarray:
        """
        Predict stability bins for samples.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples

        Returns:
            Predicted stability bins [0-19]
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        X = self.feature_extractor.transform(samples)
        return self.model.predict(X)

    def predict_proba(self, samples: List[Tuple[Dict, Dict]]) -> np.ndarray:
        """
        Predict probability over stability bins.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples

        Returns:
            Predicted probabilities [batch_size, 20]
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        X = self.feature_extractor.transform(samples)
        return self.model.predict_proba(X)


class MLPBaseline(nn.Module):
    """MLP baseline (small neural network for comparison)."""

    def __init__(self, input_dim: int = 10, hidden_dim: int = 128, num_classes: int = 20):
        """Initialize MLP."""
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, num_classes),
        )
        self.feature_extractor = FeatureExtractor()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass."""
        return self.net(x)

    def fit(
        self,
        samples: List[Tuple[Dict, Dict]],
        targets: List[float],
        epochs: int = 50,
        batch_size: int = 32,
        device: str = "cpu",
    ) -> None:
        """
        Train MLP on (protein, formulation) → stability.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples
            targets: List of stability scores [0, 1]
            epochs: Number of training epochs
            batch_size: Batch size for training
            device: "cuda" or "cpu"
        """
        X = self.feature_extractor.fit_transform(samples)
        y = np.array(targets, dtype=np.float32)

        # Quantize targets to 20 bins
        y_bins = np.digitize(y, bins=np.linspace(0, 1, 20)) - 1
        y_bins = np.clip(y_bins, 0, 19)

        self.to(device)
        optimizer = torch.optim.Adam(self.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss()

        X_tensor = torch.tensor(X, dtype=torch.float32).to(device)
        y_tensor = torch.tensor(y_bins, dtype=torch.long).to(device)

        for epoch in range(epochs):
            self.train()
            total_loss = 0

            for i in range(0, len(X), batch_size):
                X_batch = X_tensor[i : i + batch_size]
                y_batch = y_tensor[i : i + batch_size]

                optimizer.zero_grad()
                logits = self(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                optimizer.step()

                total_loss += loss.item()

            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(X):.4f}")

    def predict(self, samples: List[Tuple[Dict, Dict]], device: str = "cpu") -> np.ndarray:
        """
        Predict stability bins for samples.

        Args:
            samples: List of (protein_dict, formulation_dict) tuples
            device: "cuda" or "cpu"

        Returns:
            Predicted stability bins [0-19]
        """
        self.eval()
        X = self.feature_extractor.transform(samples)
        X_tensor = torch.tensor(X, dtype=torch.float32).to(device)

        with torch.no_grad():
            logits = self(X_tensor)
            predictions = torch.argmax(logits, dim=1)

        return predictions.cpu().numpy()


# ============================================================================
# ABLATION HARNESSES
# ============================================================================


class NoInContextAblation:
    """
    Ablation: Train BioFormLM on synthetic data only.

    No few-shot real-data conditioning at inference time.
    Tests whether in-context learning provides value.
    """

    def __init__(self):
        """Initialize ablation."""
        logger.info("NoInContextAblation: No few-shot conditioning at inference")

    def note(self) -> str:
        """Return description."""
        return "Trained on synthetic only, no few-shot real-data input at test time"


class NoCriticAblation:
    """
    Ablation: Use recipe generation head output directly.

    No physics-critic guidance or preference reranking.
    Tests whether critic provides value beyond base model.
    """

    def __init__(self):
        """Initialize ablation."""
        logger.info("NoCriticAblation: No physics critic guidance at inference")

    def note(self) -> str:
        """Return description."""
        return "Base model recipe generation without critic guidance/reranking"
