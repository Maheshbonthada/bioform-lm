"""
BioForm-LM: causal decoder for generative formulation design.

Replaces the earlier `experiments.train.BioFormLM`, which had three defects that
made generation impossible:

  1. `nn.TransformerEncoder` was applied with no attention mask, so every
     position attended to every other one. A next-token objective under full
     bidirectional attention is degenerate -- the target is in the input.
  2. `recipe_head` received no loss term (see the TODO at train.py:223), so its
     51,143 parameters stayed at random initialisation. Comparing checkpoint
     epoch 1 against epoch 33 shows a max weight delta of exactly 0.0.
  3. There was no `generate()` at all.

This module fixes all three: causal masking, a trainable LM head, and
grammar-constrained autoregressive decoding.
"""

from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

# Recipe grammar: the tokenizer always emits these slots, in this order, after
# the "[CLS] MW PI TM [SEP]" conditioning prefix.
RECIPE_SLOTS = [
    ("BUFFER",   61,  67),
    ("BUFCONC",  67,  82),
    ("PH",       82, 102),
    ("IS",      102, 122),
    ("OSMOL",   122, 138),
    ("TEMP",    138, 150),
    ("STAB",    150, 158),
    ("STABCONC",158, 179),
]
PREFIX_LEN = 5          # [CLS] MW PI TM [SEP]
RECIPE_LEN = len(RECIPE_SLOTS)


class BioFormLM(nn.Module):
    """Causal transformer over formulation token sequences."""

    def __init__(
        self,
        vocab_size: int = 199,
        hidden_dim: int = 256,
        num_layers: int = 6,
        num_heads: int = 8,
        feedforward_dim: int = 1024,
        max_seq_len: int = 64,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.vocab_size = vocab_size
        self.max_seq_len = max_seq_len

        self.embedding = nn.Embedding(vocab_size, hidden_dim)
        self.pos_embedding = nn.Parameter(torch.randn(max_seq_len, hidden_dim) * 0.02)

        layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=feedforward_dim,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.ln_f = nn.LayerNorm(hidden_dim)

        # Stability classifier (20 bins) and the language-modelling head.
        self.stability_head = nn.Sequential(
            nn.Linear(hidden_dim, 128), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(128, 20),
        )
        self.recipe_head = nn.Linear(hidden_dim, vocab_size)

    def _causal_mask(self, n: int, device) -> torch.Tensor:
        # Bool mask (True = blocked) so it matches the dtype of
        # src_key_padding_mask; mixing float and bool masks is deprecated.
        return torch.triu(
            torch.ones(n, n, dtype=torch.bool, device=device), diagonal=1
        )

    def forward(
        self, input_ids: torch.Tensor, pad_id: int = 0
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns (stability_logits [B,20], recipe_logits [B,T,V]).

        Attention is causal, so position t sees only positions <= t. Stability is
        read off the last non-pad position rather than [CLS], because under a
        causal mask position 0 can attend to nothing but itself.
        """
        B, T = input_ids.shape
        x = self.embedding(input_ids) + self.pos_embedding[:T].unsqueeze(0)
        x = self.transformer(
            x,
            mask=self._causal_mask(T, input_ids.device),
            src_key_padding_mask=(input_ids == pad_id),
        )
        x = self.ln_f(x)

        lengths = (input_ids != pad_id).sum(dim=1).clamp(min=1) - 1
        pooled = x[torch.arange(B, device=x.device), lengths]

        return self.stability_head(pooled), self.recipe_head(x)

    @torch.no_grad()
    def generate(
        self,
        prefix_ids: torch.Tensor,
        num_candidates: int = 50,
        temperature: float = 1.0,
        top_k: int = 0,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        """
        Grammar-constrained autoregressive sampling.

        `prefix_ids` is [P] -- the conditioning prefix, optionally with in-context
        examples prepended. At every step logits are masked to the single slot the
        grammar permits, so each sampled recipe is structurally valid by
        construction and validity is not a metric that can be gamed.

        Returns [num_candidates, RECIPE_LEN] of recipe token ids.
        """
        self.eval()
        device = next(self.parameters()).device
        seq = prefix_ids.to(device).unsqueeze(0).repeat(num_candidates, 1)

        out = []
        for _, lo, hi in RECIPE_SLOTS:
            if seq.size(1) >= self.max_seq_len:      # keep within learned positions
                seq = seq[:, -(self.max_seq_len - 1):]
            _, logits = self.forward(seq)
            step = logits[:, -1, :] / max(temperature, 1e-6)

            allowed = torch.full_like(step, float("-inf"))
            allowed[:, lo:hi] = step[:, lo:hi]       # restrict to this slot
            if top_k and top_k < (hi - lo):
                kth = allowed.topk(top_k, dim=-1).values[:, -1:]
                allowed = allowed.masked_fill(allowed < kth, float("-inf"))

            probs = F.softmax(allowed, dim=-1)
            nxt = torch.multinomial(probs, 1, generator=generator)
            out.append(nxt)
            seq = torch.cat([seq, nxt], dim=1)

        return torch.cat(out, dim=1)

    @torch.no_grad()
    def score_stability(self, input_ids: torch.Tensor) -> torch.Tensor:
        """Expected stability in [0,1] from the 20-bin head (bin centres)."""
        self.eval()
        logits, _ = self.forward(input_ids)
        p = F.softmax(logits, dim=-1)
        centres = (torch.arange(20, device=p.device, dtype=p.dtype) + 0.5) / 20.0
        return (p * centres).sum(dim=-1)


def decode_recipe(token_ids: List[int], tokenizer) -> Dict[str, object]:
    """Turn generated slot tokens back into a formulation dict."""
    rev = {v: k for k, v in tokenizer.vocab.items()}
    out: Dict[str, object] = {}
    for (name, _, _), tid in zip(RECIPE_SLOTS, token_ids):
        tok = rev.get(int(tid), "<UNK>")
        out[name] = tok.split("_", 1)[1] if "_" in tok else tok
    return out
