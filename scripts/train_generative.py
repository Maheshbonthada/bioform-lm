#!/usr/bin/env python3
"""
Train BioForm-LM with a real generative objective.

The original trainer (experiments/train.py) optimised only the stability
classifier and dropped `recipe_logits` on the floor behind a
"TODO: add recipe generation as auxiliary task", leaving `recipe_head` at random
initialisation -- comparing checkpoints epoch 1 and epoch 33 shows a max weight
delta of exactly 0.0. The model therefore could not generate at all.

This trains both heads under causal attention:

    loss = CE(stability_bins) + lm_weight * CE(next recipe token)

The LM term is masked to simulator-preferred rows, since training it on
uniformly random recipes teaches only the marginal recipe distribution.

Throughput notes: the corpus is small enough to live on the GPU as int16-range
token ids, so batches are sliced on-device and there is no host transfer or
DataLoader worker in the loop. The model is tiny (4.9M params, sequence length
13), which makes it kernel-launch bound rather than compute bound -- large
batches are what keep the GPU busy. Encoding is parallelised across cores.

    python scripts/train_generative.py --epochs 30 --batch-size 8192
"""

import argparse
import json
import logging
import os
import sys
import time
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model.bioform_lm import BioFormLM, PREFIX_LEN, RECIPE_LEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("train")

SEQ_LEN = PREFIX_LEN + RECIPE_LEN


def _encode_shard(records):
    """Encode a list of row-dicts to (ids, stability_bin, is_preferred)."""
    logging.disable(logging.INFO)
    from model.tokenizer import FormulationTokenizer

    tk = FormulationTokenizer()
    seqs, bins, pref = [], [], []
    for r in records:
        ids, _ = tk.encode_sample(
            {"mw_kda": r["protein_mw_kda"], "pi": r["protein_pi"],
             "tm_baseline_c": r["protein_tm_baseline_c"]},
            {"buffer_species": r["buffer_species"],
             "buffer_conc_mm": r["buffer_conc_mm"], "ph": r["ph"],
             "ionic_strength_mm": r["ionic_strength_mm"],
             "osmolarity_mosm_kg": r["osmolarity_mosm_kg"],
             "temperature_c": r["temperature_c"],
             "stabilizers": r["stabilizers_json"]},
        )
        # Keep exactly one stabilizer pair so every sequence matches the slot
        # layout the grammar-constrained decoder expects.
        ids = ids[:SEQ_LEN]
        if len(ids) != SEQ_LEN:
            continue
        seqs.append(ids)
        bins.append(tk.encode_stability_bin(r["stability_score"]))
        pref.append(int(r.get("is_preferred", 1)))
    return seqs, bins, pref


def encode_parallel(df: pd.DataFrame, workers: int):
    records = df.to_dict("records")
    chunks = [records[i::workers] for i in range(workers)]
    chunks = [c for c in chunks if c]
    with Pool(len(chunks)) as pool:
        parts = pool.map(_encode_shard, chunks)
    seqs = [s for p in parts for s in p[0]]
    bins = [b for p in parts for b in p[1]]
    pref = [q for p in parts for q in p[2]]
    return (torch.tensor(seqs, dtype=torch.long),
            torch.tensor(bins, dtype=torch.long),
            torch.tensor(pref, dtype=torch.float))


def lm_loss(recipe_logits, input_ids, weights):
    """
    Next-token CE over recipe slots, restricted to simulator-preferred rows.

    Position t predicts token t+1; recipe tokens begin at PREFIX_LEN. `weights`
    masks the loss to rows the simulator ranked highly for their protein, which
    is where the conditional signal lives.
    """
    logits = recipe_logits[:, PREFIX_LEN - 1: -1, :]
    targets = input_ids[:, PREFIX_LEN:]
    per_tok = F.cross_entropy(
        logits.reshape(-1, logits.size(-1)).float(), targets.reshape(-1),
        reduction="none",
    ).view(targets.shape)
    w = weights.unsqueeze(1).expand_as(per_tok)
    return (per_tok * w).sum() / w.sum().clamp(min=1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/conditional_training_data.parquet")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=8192)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lm-weight", type=float, default=1.0)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--amp", action="store_true", default=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="experiments/checkpoints_generative")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(a.data)
    t0 = time.time()
    seqs, bins, pref = encode_parallel(df, a.workers)
    log.info(f"encoded {len(seqs):,} sequences (len {seqs.shape[1]}) "
             f"on {a.workers} workers in {time.time()-t0:.0f}s")

    # Whole corpus lives on the GPU: ~240k x 13 int64 is a few tens of MB, so
    # batching is a device-side slice with no host transfer per step.
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
             f"train {len(Xtr):,} val {len(Xva):,} | batch {a.batch_size} | "
             f"amp={a.amp and dev == 'cuda'}")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = max(1, len(Xtr) // a.batch_size)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=a.lr, total_steps=a.epochs * steps, pct_start=0.1)
    use_amp = a.amp and dev == "cuda"
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
        log.info(f"epoch {ep:>3}/{a.epochs}  train {agg[0]:.4f} "
                 f"(stab {agg[1]:.4f} lm {agg[2]:.4f})  |  val {v[0]:.4f} "
                 f"(stab {v[1]:.4f} lm {v[2]:.4f})  acc {acc:.3f}  "
                 f"ppl {np.exp(v[2]):.3f}  [{time.time()-t:.1f}s]")
        hist.append({"epoch": ep, "train": agg.tolist(), "val": v.tolist(),
                     "stab_acc": acc, "recipe_ppl": float(np.exp(v[2]))})

        if v[0] < best:
            best = v[0]
            torch.save({"epoch": ep, "model_state_dict": model.state_dict(),
                        "val_loss": v[0], "val_stability_loss": v[1],
                        "val_lm_loss": v[2], "stability_acc": acc,
                        "recipe_perplexity": float(np.exp(v[2])),
                        "vocab_size": vocab_size}, out / "best.pt")

    (out / "history.json").write_text(json.dumps(hist, indent=2))
    log.info(f"done. best val {best:.4f} -> {out/'best.pt'}")


if __name__ == "__main__":
    main()
