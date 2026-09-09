#!/usr/bin/env python3
"""
Repair the BioFormBench seed CSV.

49 of 67 rows carry two undeclared trailing columns (source article title and
PMC id). Because they exceed the 14-column header, `pandas.read_csv` raises, and
any loader using `on_bad_lines='skip'` silently keeps only the 18 rows that
happen to match the header -- which is exactly the "18 formulations" the
evaluation was run on. Every real literature-mined formulation was dropped.

This declares the provenance columns and pads the rows that lack them, so all 67
rows load. No measurement value is altered.

    python scripts/repair_bioformbench.py
"""
import csv
from pathlib import Path

SRC = Path("data/bioformbench_seed.csv")
DST = Path("data/bioformbench_v2.csv")
PROVENANCE = ["source_title", "source_id"]


def main() -> None:
    rows = list(csv.reader(SRC.open(encoding="utf-8")))
    header, body = rows[0], rows[1:]
    n = len(header)

    for r in body:
        if len(r) > n + len(PROVENANCE):
            raise SystemExit(f"unexpected column count {len(r)}: {r[:2]}")

    new_header = header + PROVENANCE
    out = []
    for r in body:
        r = list(r) + [""] * (len(new_header) - len(r))
        out.append(r)

    with DST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(new_header)
        w.writerows(out)

    have = sum(1 for r in out if r[n])
    print(f"wrote {DST}: {len(out)} rows, {len(new_header)} columns")
    print(f"  rows with provenance: {have}   padded: {len(out) - have}")


if __name__ == "__main__":
    main()
