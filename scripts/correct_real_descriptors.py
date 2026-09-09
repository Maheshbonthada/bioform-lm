#!/usr/bin/env python3
"""
Correct protein descriptors in BioFormBench-Real for named, identifiable molecules.

BioFormBench-Real (bioformbench_v3.csv, after the provenance purge) still carries
the same class of defect found and fixed in the marketed-formulation analysis:
several of its molecules are named real antibodies whose recorded pI is a
generic placeholder rather than the molecule's actual value. Concretely,
Trastuzumab, Omalizumab, Adalimumab and a TUR01 (adalimumab biosimilar) row are
ALL recorded at pI 7.2-7.3 -- indistinguishable from each other -- when their
real values span 5.79 to 9.03. Any protein-specificity test run on this
descriptor cannot possibly separate these four molecules, by construction,
exactly as with the marketed-formulation placeholders.

Corrections applied, each with an explicit, checkable source (never inferred):

  Trastuzumab  : pI 7.2 -> 9.03  (cIEF, PMC-indexed mAbs charge-variant survey)
  Omalizumab   : pI 7.2 -> 5.79  (computed from its own Thera-SAbDab Fv sequence;
                                   no published whole-molecule value found)
  Adalimumab   : pI 7.2 -> 8.5   (icIEF main isoform, PMC5240642/PMC7272391)
  Biosimilar_mAb: pI 7.3 -> 8.5  (TUR01 is an adalimumab biosimilar -- regulatory
                                   biosimilarity requires an identical amino-acid
                                   sequence to the reference product, so it
                                   carries adalimumab's pI)
  bispecific_A : pI 6.9 -> 8.52  (stated directly in the source paper, PMC11343937)

Left uncorrected (no independent value could be found, so the existing
placeholder is retained rather than guessed): PGT121 (its own Fv sequence gives
pI 7.06, close to the existing 7.0 -- no meaningful correction), rhIL1ra (own
UniProt sequence gives pI 5.46, close to the existing 5.6 -- likewise), X2Y1
bispecific, mAb2, mAb_aggregation_prone_1/stable_reference/high_viscosity,
A33_Fab, Fab_citrate_*.
"""
import json
from pathlib import Path

import pandas as pd

CORRECTIONS = {
    "Trastuzumab": {"protein_pi": 9.03, "source": "PMC-indexed cIEF survey of 23 therapeutic mAbs"},
    "Omalizumab": {"protein_pi": 5.79, "source": "Fv sequence (Thera-SAbDab), Biopython ProtParam"},
    "Adalimumab": {"protein_pi": 8.50, "source": "icIEF main isoform, PMC5240642/PMC7272391"},
    "Biosimilar_mAb": {"protein_pi": 8.50, "source": "TUR01 = adalimumab biosimilar (identical sequence)"},
    "bispecific_A": {"protein_pi": 8.52, "source": "stated directly, PMC11343937"},
}

# Explicit protein_id -> real-molecule identity map. This replaces the loader's
# (MW, pI) string-match grouping, which is fragile by construction: rounding two
# floats to 2dp and concatenating them as a string collides whenever two
# UNRELATED real proteins happen to share an MW/pI bucket. Concretely, before
# this fix, Trastuzumab (3 rows), Omalizumab (2 rows), mAb2 (2 rows) and a
# generic "mAb" developability-panel row were ALL merged into one fake pooled
# "protein" (key "150.0_7.2", 10 rows) purely because their placeholder pI
# values collided at 7.2 -- meaning the LOPO evaluation was, for that fold,
# training on Trastuzumab's real formulations and testing as if predicting
# Omalizumab's, or vice versa. This map is built directly from each row's
# protein_id prefix (which literally names the source molecule) instead.
IDENTITY_MAP = {
    "A33_Fab": "A33_Fab",
    "Adalimumab": "Adalimumab",
    "Biosimilar_mAb": "Biosimilar_mAb_TUR01",
    "Fab_citrate": "Fab_PMC10155210",          # distinct paper/molecule from A33_Fab
    "Omalizumab": "Omalizumab",
    "PGT121": "PGT121",
    "Trastuzumab": "Trastuzumab",
    "X2Y1_bispecific": "X2Y1_bispecific",
    "bispecific_A": "bispecific_A",
    "mAb2": "mAb2",
    "mAb_aggregation_prone_1": "mAb_devpanel_aggregation_prone",
    "mAb_high_viscosity_1": "mAb_devpanel_high_viscosity",
    "mAb_stable_reference": "mAb_devpanel_stable_reference",
    "rhIL1ra": "rhIL1ra",
}


def identity_of(protein_id: str) -> str:
    pid = str(protein_id)
    # longest-prefix match so e.g. "mAb_aggregation_prone_1" doesn't fall through
    # to a shorter unrelated key
    for key in sorted(IDENTITY_MAP, key=len, reverse=True):
        if pid == key or pid.startswith(key + "_"):
            return IDENTITY_MAP[key]
    raise KeyError(f"no identity mapping for protein_id={pid!r}")


def matches(protein_id: str, key: str) -> bool:
    return protein_id.lower().startswith(key.lower())


def main():
    df = pd.read_csv("data/bioformbench_v3.csv")
    df["protein_pi_original"] = df["protein_pi"]
    df["pi_corrected"] = False
    df["pi_correction_source"] = ""

    n_changed = 0
    for key, info in CORRECTIONS.items():
        mask = df["protein_id"].apply(lambda pid: matches(str(pid), key))
        if mask.sum() == 0:
            print(f"WARNING: no rows matched '{key}'")
            continue
        before = df.loc[mask, "protein_pi"].unique()
        df.loc[mask, "protein_pi"] = info["protein_pi"]
        df.loc[mask, "pi_corrected"] = True
        df.loc[mask, "pi_correction_source"] = info["source"]
        n_changed += mask.sum()
        print(f"{key:16s} ({mask.sum()} rows): pI {before} -> {info['protein_pi']}  [{info['source']}]")

    # Real-molecule identity, independent of any descriptor value, to replace
    # the (MW, pI) string-match key the loader used before this fix.
    df["real_protein_id"] = df["protein_id"].apply(identity_of)

    out = Path("data/bioformbench_v4.csv")
    df.to_csv(out, index=False)
    print(f"\n{n_changed}/{len(df)} rows corrected -> {out}")
    print(f"distinct real molecules: {df['real_protein_id'].nunique()}")

    # Show what the OLD (MW, pI) key would have merged, using the ORIGINAL
    # (pre-correction) pI -- this is the bug as it actually ran.
    old_key = (df["protein_mw_kda"].round(2).astype(str) + "_" +
              df["protein_pi_original"].round(2).astype(str))
    print("\nOLD (MW,pI)-string grouping merged these DIFFERENT real molecules:")
    for k, g in df.groupby(old_key):
        real_ids = sorted(g["real_protein_id"].unique())
        if len(real_ids) > 1:
            print(f"  key={k}: {real_ids}  ({len(g)} rows total) <- BUG")


if __name__ == "__main__":
    main()
