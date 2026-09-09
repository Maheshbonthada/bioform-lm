#!/usr/bin/env python3
"""
Remove unsourced rows from BioFormBench.

18 of the 67 rows in bioformbench_v2.csv carry no source_title/source_id and use
placeholder identifiers (protein_1 ... protein_5) with suspiciously round
descriptors (50.0 kDa / pI 7.2 / Tm 65.0). They are synthetic scaffolding left
over from early development, not literature-mined data, and they are exactly the
18 rows the original buggy CSV parser happened to keep.

A benchmark that mixes them with real data cannot support any claim about real
formulations, so they are dropped. The remaining 49 rows all trace to a PubMed
Central identifier.
"""
import pandas as pd
from pathlib import Path

src = Path("data/bioformbench_v2.csv")
df = pd.read_csv(src)
keep = df[df.source_id.notna() & df.source_title.notna()].copy()

dropped = len(df) - len(keep)
print(f"{len(df)} rows in -> dropped {dropped} unsourced -> {len(keep)} real rows")
print(f"distinct source papers: {keep.source_id.nunique()}")
print(f"distinct protein records: {keep.protein_id.nunique()}")

out = Path("data/bioformbench_v3.csv")
keep.to_csv(out, index=False)
print(f"wrote {out}")
