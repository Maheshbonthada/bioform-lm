"""
Formulation Tokenizer

Converts formulation recipes into token sequences for the transformer.

Tokenization strategy:
- Protein descriptor tokens: MW, pI, Tm, hydrophobicity (quantized)
- Buffer tokens: buffer species (categorical)
- pH tokens: pH value (quantized to bins)
- Ionic strength tokens: IS value (quantized)
- Stabilizer tokens: identity + concentration pairs
- Outcome tokens: stability score (quantized)

Special tokens:
- <PAD>: padding (id=0)
- <CLS>: classification/start (id=1)
- <SEP>: separator between input/output (id=2)
- <EOS>: end-of-sequence (id=3)
- <UNK>: unknown (id=4)

Vocabulary size: ~1024 tokens total
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenizerConfig:
    """Tokenizer configuration."""
    # Quantization bins
    mw_bins: int = 20  # discretize MW into 20 bins
    pi_bins: int = 16  # discretize pI into 16 bins
    ph_bins: int = 20  # discretize pH into 20 bins
    tm_bins: int = 20  # discretize Tm into 20 bins
    is_bins: int = 20  # discretize ionic strength into 20 bins
    osmol_bins: int = 16
    temp_bins: int = 12
    stability_bins: int = 20  # quantize stability score into bins

    # Ranges for quantization
    mw_range: Tuple = (1, 500)
    pi_range: Tuple = (2, 12)
    ph_range: Tuple = (2, 12)
    tm_range: Tuple = (20, 100)
    is_range: Tuple = (1, 1000)
    osmol_range: Tuple = (50, 500)
    temp_range: Tuple = (-20, 50)
    stability_range: Tuple = (0, 1)

    # Vocabulary
    buffer_types: List[str] = None
    stabilizer_types: List[str] = None

    def __post_init__(self):
        if self.buffer_types is None:
            self.buffer_types = [
                "histidine", "acetate", "phosphate", "tris", "citrate", "succinate"
            ]
        if self.stabilizer_types is None:
            self.stabilizer_types = [
                "sucrose", "sorbitol", "trehalose", "polysorbate_20", "polysorbate_80",
                "glycerol", "bsa", "gelatin"
            ]


class FormulationTokenizer:
    """Tokenizes formulation data for transformer input."""

    # Special tokens
    PAD_TOKEN = "<PAD>"
    CLS_TOKEN = "<CLS>"
    SEP_TOKEN = "<SEP>"
    EOS_TOKEN = "<EOS>"
    UNK_TOKEN = "<UNK>"

    PAD_ID = 0
    CLS_ID = 1
    SEP_ID = 2
    EOS_ID = 3
    UNK_ID = 4

    def __init__(self, config: Optional[TokenizerConfig] = None):
        """Initialize tokenizer."""
        self.config = config or TokenizerConfig()
        self.vocab = self._build_vocab()
        self.vocab_size = len(self.vocab)

        logger.info(f"FormulationTokenizer initialized: vocab_size={self.vocab_size}")

    def _build_vocab(self) -> Dict[str, int]:
        """Build vocabulary for all possible tokens."""
        vocab = {}
        token_id = 5  # Start after special tokens

        # Special tokens
        vocab[self.PAD_TOKEN] = self.PAD_ID
        vocab[self.CLS_TOKEN] = self.CLS_ID
        vocab[self.SEP_TOKEN] = self.SEP_ID
        vocab[self.EOS_TOKEN] = self.EOS_ID
        vocab[self.UNK_TOKEN] = self.UNK_ID

        # Protein descriptor quantized tokens
        for i in range(self.config.mw_bins):
            vocab[f"MW_{i}"] = token_id
            token_id += 1

        for i in range(self.config.pi_bins):
            vocab[f"PI_{i}"] = token_id
            token_id += 1

        for i in range(self.config.tm_bins):
            vocab[f"TM_{i}"] = token_id
            token_id += 1

        # Buffer tokens
        for buffer_type in self.config.buffer_types:
            vocab[f"BUFFER_{buffer_type.upper()}"] = token_id
            token_id += 1

        # Buffer concentration bins
        for i in range(15):  # 0-15 mM bins
            vocab[f"BUFCONC_{i}"] = token_id
            token_id += 1

        # pH tokens
        for i in range(self.config.ph_bins):
            vocab[f"PH_{i}"] = token_id
            token_id += 1

        # Ionic strength tokens
        for i in range(self.config.is_bins):
            vocab[f"IS_{i}"] = token_id
            token_id += 1

        # Osmolarity tokens
        for i in range(self.config.osmol_bins):
            vocab[f"OSMOL_{i}"] = token_id
            token_id += 1

        # Temperature tokens
        for i in range(self.config.temp_bins):
            vocab[f"TEMP_{i}"] = token_id
            token_id += 1

        # Stabilizer identity tokens
        for stab_type in self.config.stabilizer_types:
            vocab[f"STAB_{stab_type.upper()}"] = token_id
            token_id += 1

        # Stabilizer concentration bins (0-20%, in 1% increments)
        for i in range(21):
            vocab[f"STABCONC_{i}"] = token_id
            token_id += 1

        # Outcome/stability tokens (prediction targets)
        for i in range(self.config.stability_bins):
            vocab[f"STABILITY_{i}"] = token_id
            token_id += 1

        return vocab

    def encode_protein(self, mw: float, pi: float, tm: float) -> List[int]:
        """Encode protein descriptor as tokens."""
        tokens = []

        # MW (quantized)
        mw_bin = self._quantize(mw, self.config.mw_range, self.config.mw_bins)
        tokens.append(self.vocab[f"MW_{mw_bin}"])

        # pI (quantized)
        pi_bin = self._quantize(pi, self.config.pi_range, self.config.pi_bins)
        tokens.append(self.vocab[f"PI_{pi_bin}"])

        # Tm (quantized)
        tm_bin = self._quantize(tm, self.config.tm_range, self.config.tm_bins)
        tokens.append(self.vocab[f"TM_{tm_bin}"])

        return tokens

    def encode_formulation(self, formulation_dict: Dict) -> List[int]:
        """Encode formulation composition as tokens."""
        tokens = []

        # Buffer species
        buffer = formulation_dict.get("buffer_species", "histidine").upper()
        buffer_token = f"BUFFER_{buffer}"
        tokens.append(self.vocab.get(buffer_token, self.UNK_ID))

        # Buffer concentration
        buf_conc = min(formulation_dict.get("buffer_conc_mm", 20), 150)
        buf_conc_bin = int((buf_conc / 150.0) * 15)  # 0-15 bins
        tokens.append(self.vocab[f"BUFCONC_{buf_conc_bin}"])

        # pH
        ph = formulation_dict.get("ph", 7.0)
        ph_bin = self._quantize(ph, self.config.ph_range, self.config.ph_bins)
        tokens.append(self.vocab[f"PH_{ph_bin}"])

        # Ionic strength
        is_val = formulation_dict.get("ionic_strength_mm", 150)
        is_bin = self._quantize(is_val, self.config.is_range, self.config.is_bins)
        tokens.append(self.vocab[f"IS_{is_bin}"])

        # Osmolarity
        osmol = formulation_dict.get("osmolarity_mosm_kg", 300)
        osmol_bin = self._quantize(osmol, self.config.osmol_range, self.config.osmol_bins)
        tokens.append(self.vocab[f"OSMOL_{osmol_bin}"])

        # Temperature
        temp = formulation_dict.get("temperature_c", 25.0)
        temp_bin = self._quantize(temp, self.config.temp_range, self.config.temp_bins)
        tokens.append(self.vocab[f"TEMP_{temp_bin}"])

        # Stabilizers (variable length, up to 5)
        stabilizers = formulation_dict.get("stabilizers", {})
        if isinstance(stabilizers, str):
            stabilizers = json.loads(stabilizers)

        for stab_name, stab_conc in list(stabilizers.items())[:5]:  # max 5 stabilizers
            # Stabilizer identity
            stab_upper = stab_name.upper()
            stab_token = f"STAB_{stab_upper}"
            tokens.append(self.vocab.get(stab_token, self.UNK_ID))

            # Stabilizer concentration (quantize to 0-20%)
            conc_bin = min(int(stab_conc), 20)
            tokens.append(self.vocab[f"STABCONC_{conc_bin}"])

        return tokens

    def encode_stability_bin(self, stability_score: float) -> int:
        """Encode stability score as bin index (0-19)."""
        stab_bin = self._quantize(
            stability_score,
            self.config.stability_range,
            self.config.stability_bins,
        )
        return stab_bin

    def encode_stability(self, stability_score: float) -> int:
        """Encode stability score as vocabulary token ID."""
        stab_bin = self.encode_stability_bin(stability_score)
        return self.vocab[f"STABILITY_{stab_bin}"]

    def encode_sample(
        self,
        protein_dict: Dict,
        formulation_dict: Dict,
        outcome_dict: Optional[Dict] = None,
    ) -> Tuple[List[int], Optional[int]]:
        """
        Encode full sample: (protein + formulation) → stability

        Returns:
            (input_tokens, target_bin) — target_bin is the stability class (0-19)
        """
        input_tokens = [self.CLS_ID]

        # Protein
        protein_tokens = self.encode_protein(
            protein_dict["mw_kda"],
            protein_dict["pi"],
            protein_dict["tm_baseline_c"],
        )
        input_tokens.extend(protein_tokens)

        # Separator
        input_tokens.append(self.SEP_ID)

        # Formulation
        form_tokens = self.encode_formulation(formulation_dict)
        input_tokens.extend(form_tokens)

        # Target (if provided): return bin index, not vocabulary token
        target_bin = None
        if outcome_dict is not None:
            target_bin = self.encode_stability_bin(outcome_dict.get("stability_score", 0.5))

        return input_tokens, target_bin

    def decode_tokens(self, token_ids: List[int]) -> List[str]:
        """Decode token IDs back to token strings."""
        # Build reverse vocab
        reverse_vocab = {v: k for k, v in self.vocab.items()}

        tokens = []
        for token_id in token_ids:
            token_str = reverse_vocab.get(token_id, self.UNK_TOKEN)
            tokens.append(token_str)

        return tokens

    def _quantize(
        self,
        value: float,
        value_range: Tuple[float, float],
        num_bins: int,
    ) -> int:
        """Quantize continuous value into bin index."""
        min_val, max_val = value_range
        value = np.clip(value, min_val, max_val)

        # Normalize to [0, 1]
        normalized = (value - min_val) / (max_val - min_val)

        # Map to bin
        bin_idx = int(normalized * (num_bins - 1))
        return np.clip(bin_idx, 0, num_bins - 1)

    def save(self, path: Path) -> None:
        """Save tokenizer configuration."""
        config_dict = {
            "vocab_size": self.vocab_size,
            "config": self.config.__dict__,
            "vocab": self.vocab,
        }

        with open(path, 'w') as f:
            json.dump(config_dict, f, indent=2)

        logger.info(f"Tokenizer saved to {path}")

    @classmethod
    def load(cls, path: Path) -> "FormulationTokenizer":
        """Load tokenizer configuration."""
        with open(path, 'r') as f:
            config_dict = json.load(f)

        tokenizer = cls()
        tokenizer.vocab = config_dict["vocab"]
        tokenizer.vocab_size = config_dict["vocab_size"]

        logger.info(f"Tokenizer loaded from {path} (vocab_size={tokenizer.vocab_size})")
        return tokenizer


if __name__ == "__main__":
    """Test tokenizer."""
    logging.basicConfig(level=logging.INFO)

    tokenizer = FormulationTokenizer()

    # Test encoding
    protein = {
        "mw_kda": 100.0,
        "pi": 7.0,
        "tm_baseline_c": 65.0,
    }

    formulation = {
        "buffer_species": "histidine",
        "buffer_conc_mm": 20.0,
        "ph": 6.0,
        "ionic_strength_mm": 150.0,
        "osmolarity_mosm_kg": 310.0,
        "stabilizers": {"sucrose": 5.0, "polysorbate_80": 0.2},
        "temperature_c": 25.0,
    }

    outcome = {
        "stability_score": 0.75,
    }

    input_tokens, target_token = tokenizer.encode_sample(protein, formulation, outcome)

    print("\n" + "=" * 70)
    print("TOKENIZER TEST")
    print("=" * 70)
    print(f"Vocab size: {tokenizer.vocab_size}")
    print(f"Input tokens: {input_tokens[:20]}... (total {len(input_tokens)})")
    print(f"Target token: {target_token}")

    # Decode
    decoded = tokenizer.decode_tokens(input_tokens[:10])
    print(f"\nDecoded tokens: {decoded}")
    print("=" * 70)
