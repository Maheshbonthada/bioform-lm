#!/usr/bin/env python3
"""
Train a properly documented, auditable "unconditional" control model.

The earlier checkpoint labelled `checkpoints_unconditional` reached statistical
significance on the identity-fixed protein-specificity test (Section on the
identity-merging bug fix) for reasons we could not fully re-verify -- its
training provenance was uncertain. That made it useless as a negative control:
if we cannot rule out that it secretly saw protein-recipe structure during
training, its passing the specificity test proves nothing either way.

This script builds a clean one instead. It takes the EXACT SAME corpus used to
train `checkpoints_conditional` (data/conditional_training_data.parquet) and
independently permutes the three protein-descriptor columns
(protein_mw_kda, protein_pi, protein_tm_baseline_c) as a block, row-for-row,
so that:

  * the marginal distribution of protein descriptors is unchanged (same values,
    same frequency),
  * the marginal distribution of recipes and stability scores is unchanged
    (same rows, same is_preferred flags, same buffer/pH/etc.),
  * but the PAIRING between a given protein descriptor and the recipe/outcome
    it appears next to is now uniformly random.

P(recipe | protein) is therefore provably uninformative in this corpus by
construction: whatever correlation existed between a protein's descriptor and
its simulator-preferred recipe has been destroyed. A model trained on this
corpus cannot learn genuine protein-conditional structure -- it can at most
learn to attend to the descriptor tokens as decoration. This is the clean
negative control the earlier "unconditional" checkpoint should have been.

Everything else (architecture, loss, optimizer, epochs, batch size, seed) is
held identical to scripts/train_generative.py so the comparison isolates
exactly one variable: whether protein and recipe are correlated in training.

    python scripts/train_unconditional_control.py --epochs 30 --batch-size 4096
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model.bioform_lm import BioFormLM, PREFIX_LEN, RECIPE_LEN
from scripts.train_generative import encode_parallel, lm_loss

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("train_unconditional")

SEQ_LEN = PREFIX_LEN + RECIPE_LEN
DESCRIPTOR_COLS = ["protein_mw_kda", "protein_pi", "protein_tm_baseline_c"]


def decorrelate(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Independently permute the descriptor block, breaking protein<->recipe pairing."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(df))
    out = df.copy().reset_index(drop=True)
    shuffled = df[DESCRIPTOR_COLS].reset_index(drop=True).iloc[perm].reset_index(drop=True)
    out[DESCRIPTOR_COLS] = shuffled
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/conditional_training_data.parquet")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lm-weight", type=float, default=1.0)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="experiments/checkpoints_unconditional_v2")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--decorrelate-seed", type=int, default=777)
    a = ap.parse_args()

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(a.data)
    df = decorrelate(df, a.decorrelate_seed)
    log.info(f"decorrelated {len(df):,} rows: protein descriptors permuted "
             f"independently of recipe/outcome (seed={a.decorrelate_seed})")

    # sanity check: descriptor-recipe pairing must now be different from the original
    orig = pd.read_parquet(a.data)
    same_pairing = (orig[DESCRIPTOR_COLS].values == df[DESCRIPTOR_COLS].values).all(axis=1).mean()
    log.info(f"fraction of rows where descriptor accidentally landed back on its own "
             f"recipe: {same_pairing:.5f} (expect ~0)")
    assert same_pairing < 0.01, "decorrelation failed -- pairing not broken"

    t0 = time.time()
    seqs, bins, pref = encode_parallel(df, a.workers)
    log.info(f"encoded {len(seqs):,} sequences (len {seqs.shape[1]}) "
             f"on {a.workers} workers in {time.time()-t0:.0f}s")

    g = torch.Generator().manual_seed(a.seed)
    perm = torch.randperm(len(seqs), generator=g)
    n_val = int(len(seqs) * a.val_frac)
    val_i, tr_i = perm[:n_val], perm[n_val:]
    dev = a.device
    Xtr, Ytr, Wtr = seqs[tr_i].to(dev), bins[tr_i].to(dev), pref[tr_i].to(dev)
    Xva, Yva, Wva = seqs[val_i].to(dev), bins[val_i].to(dev), pref[val_i].to(dev)

    from model.tokenizer import FormulationTokenizer
    vocab_size = FormulationTokenizer().vocab_size
    model = BioFormLM(vocab_size=vocab_size).to(dev)
    log.info(f"model {sum(p.numel() for p in model.parameters()):,} params | "
             f"train {len(Xtr):,} val {len(Xva):,} | batch {a.batch_size}")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = max(1, len(Xtr) // a.batch_size)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=a.lr, total_steps=a.epochs * steps, pct_start=0.1)
    use_amp = dev == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    def run_eval():
        model.eval()
        tot = np.zeros(3); correct = n = 0
        with torch.no_grad():
            for i in range(0, len(Xva), a.batch_size):
                x, y, w = Xva[i:i+a.batch_size], Yva[i:i+a.batch_size], Wva[i:i+a.batch_size]
                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=use_amp):
                    s, r = model(x)
                ls = F.cross_entropy(s.float(), y); ll = lm_loss(r, x, w)
                bs = len(x)
                tot += np.array([(ls + a.lm_weight*ll).item(), ls.item(), ll.item()]) * bs
                correct += (s.argmax(-1) == y).sum().item(); n += bs
        return tot / n, correct / n

    best, hist = float("inf"), []
    for ep in range(1, a.epochs + 1):
        model.train(); t = time.time()
        idx = torch.randperm(len(Xtr), device=dev)
        agg = np.zeros(3); seen = 0
        for i in range(0, len(idx) - a.batch_size + 1, a.batch_size):
            b = idx[i:i+a.batch_size]
            x, y, w = Xtr[b], Ytr[b], Wtr[b]
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=use_amp):
                s, r = model(x)
            ls = F.cross_entropy(s.float(), y)
            ll = lm_loss(r, x, w)
            loss = ls + a.lm_weight * ll
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sched.step()
            agg += np.array([loss.item(), ls.item(), ll.item()]) * len(b); seen += len(b)
        agg /= max(seen, 1)

        v, acc = run_eval()
        log.info(f"epoch {ep:>3}/{a.epochs}  train {agg[0]:.4f}  |  val {v[0]:.4f}  "
                 f"acc {acc:.3f}  ppl {np.exp(v[2]):.3f}  [{time.time()-t:.1f}s]")
        hist.append({"epoch": ep, "train": agg.tolist(), "val": v.tolist(),
                     "stab_acc": acc, "recipe_ppl": float(np.exp(v[2]))})

        if v[0] < best:
            best = v[0]
            torch.save({"epoch": ep, "model_state_dict": model.state_dict(),
                        "val_loss": v[0], "vocab_size": vocab_size,
                        "decorrelate_seed": a.decorrelate_seed,
                        "note": "protein descriptors independently permuted vs "
                                "recipe/outcome; P(recipe|protein) destroyed by "
                                "construction -- see script docstring"},
                       out / "best.pt")

    (out / "history.json").write_text(json.dumps(hist, indent=2))
    log.info(f"done. best val {best:.4f} -> {out/'best.pt'}")


if __name__ == "__main__":
    main()
