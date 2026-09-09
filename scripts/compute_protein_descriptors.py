#!/usr/bin/env python3
"""
Compute protein descriptors from variable-domain sequence.

BioFormBench v2 carried placeholder descriptors: four different antibodies all
recorded as 150.0 kDa / pI 7.2, and trastuzumab listed at pI 7.2 against a
published cIEF value of 9.03. Any protein-conditional result measured on those
descriptors was testing whether the model could distinguish molecules that the
data represented identically -- which it cannot, by construction.

Here descriptors are computed from the actual VH/VL sequences in Thera-SAbDab.
Within an isotype the constant regions are identical across antibodies, so the
variable domains are precisely the part that distinguishes one therapeutic from
another; descriptors are therefore reported at Fv level and labelled as such,
rather than guessing whole-molecule values.

Validation anchor: the Fv pI of trastuzumab is reported as 8.4 in the analytical
literature, so the computed value for trastuzumab is checked against it.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from Bio.SeqUtils.ProtParam import ProteinAnalysis

AA = set("ACDEFGHIKLMNPQRSTVWY")


def clean(s):
    if not isinstance(s, str):
        return ""
    return "".join(c for c in s.upper().strip() if c in AA)


def charge_at(seq, ph):
    """Net charge from Henderson-Hasselbalch over ionisable groups (EMBOSS pKa)."""
    pos = {"K": 10.8, "R": 12.5, "H": 6.5}
    neg = {"D": 3.9, "E": 4.1, "C": 8.5, "Y": 10.1}
    q = 0.0
    for a, pk in pos.items():
        q += seq.count(a) * (1.0 / (1.0 + 10 ** (ph - pk)))
    for a, pk in neg.items():
        q -= seq.count(a) * (1.0 / (1.0 + 10 ** (pk - ph)))
    q += 1.0 / (1.0 + 10 ** (ph - 8.6))    # N-terminus
    q -= 1.0 / (1.0 + 10 ** (3.6 - ph))    # C-terminus
    return q


def descriptors(vh, vl):
    fv = vh + vl
    if len(fv) < 100:
        return None
    pa = ProteinAnalysis(fv)
    d = {
        "fv_len": len(fv),
        "fv_mw_kda": pa.molecular_weight() / 1000.0,
        "fv_pi": pa.isoelectric_point(),
        "fv_gravy": pa.gravy(),
        "fv_aromaticity": pa.aromaticity(),
        "fv_instability": pa.instability_index(),
        "fv_charge_ph5": charge_at(fv, 5.0),
        "fv_charge_ph6": charge_at(fv, 6.0),
        "fv_charge_ph7": charge_at(fv, 7.0),
    }
    for aa in "DEKRHNQCWY":
        d[f"frac_{aa}"] = fv.count(aa) / len(fv)
    hyd = sum(fv.count(a) for a in "AVLIMFWY") / len(fv)
    d["fv_hydrophobic_frac"] = hyd
    d["fv_net_charge_density"] = d["fv_charge_ph6"] / len(fv)
    return d


def main():
    tsa = pd.read_csv("data/raw_labels/therasabdab.csv")
    col = "Highest_Clin_Trial (Feb '25)"
    ap = tsa[tsa[col].astype(str).str.contains("Approved", case=False, na=False)].copy()

    rows = []
    for r in ap.itertuples():
        vh, vl = clean(r.HeavySequence), clean(r.LightSequence)
        d = descriptors(vh, vl)
        if d is None:
            continue
        d["inn"] = str(r.Therapeutic).lower().strip()
        d["format"] = r.Format
        d["isotype"] = getattr(r, "_2", None) or r[3]
        d["light_chain"] = r[4]
        d["target"] = r.Target
        d["vh_len"], d["vl_len"] = len(vh), len(vl)
        rows.append(d)

    df = pd.DataFrame(rows)
    out = Path("data/protein_descriptors_seq.csv")
    df.to_csv(out, index=False)
    print(f"{len(df)} approved antibodies with sequence-derived descriptors -> {out}")

    print("\nfv_pi   range %.2f - %.2f   sd %.2f" %
          (df.fv_pi.min(), df.fv_pi.max(), df.fv_pi.std()))
    print("fv_mw   range %.1f - %.1f kDa" % (df.fv_mw_kda.min(), df.fv_mw_kda.max()))
    print("gravy   range %.3f - %.3f" % (df.fv_gravy.min(), df.fv_gravy.max()))

    # --- validation against published values ---
    print("\nvalidation vs published Fv pI:")
    for name, published in [("trastuzumab", 8.4)]:
        hit = df[df.inn == name]
        if len(hit):
            got = float(hit.fv_pi.iloc[0])
            print(f"  {name}: computed {got:.2f}  published {published}  "
                  f"delta {got - published:+.2f}")
    for name in ("adalimumab", "omalizumab", "bevacizumab", "pembrolizumab"):
        hit = df[df.inn == name]
        if len(hit):
            print(f"  {name}: fv_pi {float(hit.fv_pi.iloc[0]):.2f}  "
                  f"charge@pH6 {float(hit.fv_charge_ph6.iloc[0]):+.1f}")


if __name__ == "__main__":
    main()
