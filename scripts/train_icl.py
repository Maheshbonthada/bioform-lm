#!/usr/bin/env python3
"""
Train BioForm-LM for in-context learning.

The paper's Stage 2 claims the model adapts to a novel protein from a handful of
real measurements supplied in context, with no weight update. The previous
training could not deliver that: every training sequence was a single
(protein, recipe) pair, so the model never saw a multi-example context. Supplying
examples at inference then pushed it off-distribution, and the ablation showed it
-- likelihood percentile was *higher* without context (0.856) than with it
(0.797). In-context learning has to be trained for; it does not appear by itself.

Each sequence here is

    [CLS] MW pI Tm [SEP]  (recipe_1 stability_1) ... (recipe_K stability_K)  recipe_target

with all K examples drawn from the *same* protein as the target. The LM loss is
applied only to `recipe_target`, so the model is explicitly optimised to read the
examples and propose a further recipe for that protein. K is varied per sequence
so the model handles any context size at inference.

    python scripts/train_icl.py --epochs 40 --max-shots 3
"""

import argparse
import json
import logging
import os
import sys
import time
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
log = logging.getLogger("icl")

EX_LEN = RECIPE_LEN + 1          # recipe slots + its stability token


def _build_shard(args):
    """Build ICL sequences for one shard of proteins."""
    groups, max_shots, seqs_per_protein, seed = args
    logging.disable(logging.INFO)
    from model.tokenizer import FormulationTokenizer

    tk = FormulationTokenizer()
    rng = np.random.default_rng(seed)

    def enc(r):
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
        return ids[:PREFIX_LEN], ids[PREFIX_LEN:PREFIX_LEN + RECIPE_LEN]

    out_seq, out_bin, out_ctx = [], [], []
    for rows in groups:
        pref = [r for r in rows if r.get("is_preferred", 1) == 1]
        if len(pref) < 2:
            continue
        for _ in range(seqs_per_protein):
            k = int(rng.integers(1, min(max_shots, len(pref) - 1) + 1))
            pick = rng.choice(len(pref), size=k + 1, replace=False)
            shots = [pref[i] for i in pick[:k]]
            target = pref[pick[k]]

            prefix, _ = enc(target)
            if len(prefix) != PREFIX_LEN:
                continue
            seq = list(prefix)
            ok = True
            for s in shots:
                _, rec = enc(s)
                if len(rec) != RECIPE_LEN:
                    ok = False
                    break
                seq += rec + [tk.encode_stability(float(s["stability_score"]))]
            if not ok:
                continue
            _, tgt_rec = enc(target)
            if len(tgt_rec) != RECIPE_LEN:
                continue
            seq += tgt_rec

            out_seq.append(seq)
            out_bin.append(tk.encode_stability_bin(target["stability_score"]))
            out_ctx.append(k)
    return out_seq, out_bin, out_ctx


def build_dataset(df, max_shots, seqs_per_protein, workers, seed):
    # Group by protein in the parent. Striding the flat row list across workers
    # would scatter each protein's recipes, leaving no worker with enough rows of
    # the same protein to form a context.
    by_protein = {}
    for r in df.to_dict("records"):
        by_protein.setdefault(
            (round(r["protein_mw_kda"], 6), round(r["protein_pi"], 6)), []).append(r)
    groups = list(by_protein.values())
    chunks = [groups[i::workers] for i in range(workers)]
    tasks = [(c, max_shots, seqs_per_protein, seed + i)
             for i, c in enumerate(chunks) if c]
    with Pool(len(tasks)) as pool:
        parts = pool.map(_build_shard, tasks)

    seqs = [s for p in parts for s in p[0]]
    bins = [b for p in parts for b in p[1]]
    ctx = [c for p in parts for c in p[2]]
    maxlen = max(len(s) for s in seqs)
    padded = np.zeros((len(seqs), maxlen), dtype=np.int64)   # PAD_ID == 0
    tgt_start = np.zeros(len(seqs), dtype=np.int64)
    for i, s in enumerate(seqs):
        padded[i, :len(s)] = s
        tgt_start[i] = len(s) - RECIPE_LEN
    # cross_entropy targets must be int64
    return (torch.from_numpy(padded),
            torch.tensor(bins, dtype=torch.long),
            torch.tensor(ctx, dtype=torch.long),
            torch.from_numpy(tgt_start))


def target_lm_loss(recipe_logits, input_ids, tgt_start):
    """
    Next-token CE over the target recipe only; context tokens are conditioning.

    Only RECIPE_LEN positions per sequence carry loss, so the logits for those
    positions are gathered before the softmax rather than computing CE across all
    T-1 positions and masking afterwards. At batch 8192 x length 40 the masked
    form materialises a [8192, 39, 199] float32 tensor and runs the GPU out of
    memory; gathering first cuts that to [8192, 8, 199].
    """
    B = recipe_logits.size(0)
    dev = recipe_logits.device
    off = torch.arange(RECIPE_LEN, device=dev).unsqueeze(0)     # [1, R]
    tgt_pos = tgt_start.unsqueeze(1) + off                      # [B, R] positions to predict
    src_pos = tgt_pos - 1                                       # logits that predict them

    idx = src_pos.unsqueeze(-1).expand(-1, -1, recipe_logits.size(-1))
    logits = recipe_logits.gather(1, idx).float()               # [B, R, V]
    targets = input_ids.gather(1, tgt_pos)                      # [B, R]
    return F.cross_entropy(
        logits.reshape(-1, logits.size(-1)), targets.reshape(-1)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/icl_training_data.parquet")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lm-weight", type=float, default=1.0)
    ap.add_argument("--max-shots", type=int, default=3)
    ap.add_argument("--seqs-per-protein", type=int, default=4)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="experiments/checkpoints_icl")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(a.data)
    t0 = time.time()
    X, Y, C, S = build_dataset(df, a.max_shots, a.seqs_per_protein, a.workers, a.seed)
    log.info(f"built {len(X):,} ICL sequences (len {X.shape[1]}, shots 1-{a.max_shots}) "
             f"in {time.time()-t0:.0f}s")

    g = torch.Generator().manual_seed(a.seed)
    perm = torch.randperm(len(X), generator=g)
    n_val = int(len(X) * a.val_frac)
    vi, ti = perm[:n_val], perm[n_val:]
    dev = a.device
    Xtr, Ytr, Str = X[ti].to(dev), Y[ti].to(dev), S[ti].to(dev)
    Xva, Yva, Sva, Cva = X[vi].to(dev), Y[vi].to(dev), S[vi].to(dev), C[vi].to(dev)

    from model.tokenizer import FormulationTokenizer
    vocab = FormulationTokenizer().vocab_size
    model = BioFormLM(vocab_size=vocab, max_seq_len=max(64, X.shape[1] + 2)).to(dev)
    log.info(f"model {sum(p.numel() for p in model.parameters()):,} params | "
             f"train {len(Xtr):,} val {len(Xva):,}")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = max(1, len(Xtr) // a.batch_size)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=a.lr, total_steps=a.epochs * steps, pct_start=0.1)
    scaler = torch.cuda.amp.GradScaler(enabled=(dev == "cuda"))

    best, hist = float("inf"), []
    for ep in range(1, a.epochs + 1):
        model.train()
        t = time.time()
        idx = torch.randperm(len(Xtr), device=dev)
        agg = np.zeros(3)
        seen = 0
        for i in range(0, len(idx) - a.batch_size + 1, a.batch_size):
            b = idx[i:i + a.batch_size]
            x, y, s = Xtr[b], Ytr[b], Str[b]
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=(dev == "cuda")):
                sl, rl = model(x)
            ls = F.cross_entropy(sl.float(), y)
            ll = target_lm_loss(rl, x, s)
            loss = ls + a.lm_weight * ll
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sched.step()
            agg += np.array([loss.item(), ls.item(), ll.item()]) * len(b)
            seen += len(b)
        agg /= max(seen, 1)

        model.eval()
        v = np.zeros(3); n = 0; correct = 0
        by_k = {}
        with torch.no_grad():
            for i in range(0, len(Xva), a.batch_size):
                x, y, s, c = Xva[i:i+a.batch_size], Yva[i:i+a.batch_size], \
                             Sva[i:i+a.batch_size], Cva[i:i+a.batch_size]
                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=(dev == "cuda")):
                    sl, rl = model(x)
                ls = F.cross_entropy(sl.float(), y)
                ll = target_lm_loss(rl, x, s)
                bs = len(x)
                v += np.array([(ls + a.lm_weight*ll).item(), ls.item(), ll.item()]) * bs
                correct += (sl.argmax(-1) == y).sum().item(); n += bs
                for k in c.unique().tolist():
                    sel = c == k
                    by_k.setdefault(k, []).append(
                        target_lm_loss(rl[sel], x[sel], s[sel]).item())
        v /= n

        ks = "  ".join(f"k={k}:{np.mean(vv):.3f}" for k, vv in sorted(by_k.items()))
        log.info(f"epoch {ep:>3}/{a.epochs}  train {agg[0]:.4f}  |  val {v[0]:.4f} "
                 f"(stab {v[1]:.4f} lm {v[2]:.4f})  acc {correct/n:.3f}  "
                 f"ppl {np.exp(v[2]):.3f}  [{ks}]  [{time.time()-t:.0f}s]")
        hist.append({"epoch": ep, "val": v.tolist(), "acc": correct/n,
                     "ppl": float(np.exp(v[2])),
                     "lm_by_shots": {int(k): float(np.mean(vv)) for k, vv in by_k.items()}})

        if v[0] < best:
            best = v[0]
            torch.save({"epoch": ep, "model_state_dict": model.state_dict(),
                        "val_loss": v[0], "recipe_perplexity": float(np.exp(v[2])),
                        "stability_acc": correct/n, "vocab_size": vocab,
                        "max_seq_len": max(64, X.shape[1] + 2)}, out / "best.pt")

    (out / "history.json").write_text(json.dumps(hist, indent=2))
    log.info(f"done. best val {best:.4f} -> {out/'best.pt'}")


if __name__ == "__main__":
    main()
