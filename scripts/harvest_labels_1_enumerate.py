#!/usr/bin/env python3
"""
Step 1 of BioFormBench-Marketed: enumerate approved biologic products on DailyMed.

Approved product labels are the authoritative primary source for what formulation
expert developers actually selected for a specific protein. Unlike a screening
table, every row is a real, regulator-reviewed decision, and every molecule is a
named entity whose descriptors can be looked up rather than guessed.

We keep generic (name_type G) names carrying an INN stem for a protein
therapeutic: -mab (antibody), -cept (Fc fusion), -kin/-kinra (interleukin),
plus a small explicit list of protein drugs whose INN predates the stem system.
"""
import json, re, sys, time
from pathlib import Path
from urllib.request import urlopen

BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
STEM = re.compile(r"(mab|mab-\w+|cept|cept-\w+|kinra|kin)\b", re.I)
EXTRA = re.compile(r"\b(insulin|somatropin|etanercept|abatacept|aflibercept|"
                   r"romiplostim|filgrastim|pegfilgrastim|epoetin|darbepoetin|"
                   r"interferon|asparaginase|rasburicase|alteplase|factor)\b", re.I)


def fetch(url, tries=4):
    for k in range(tries):
        try:
            with urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def main():
    page, keep, seen = 1, [], set()
    while True:
        d = fetch(f"{BASE}/drugnames.json?pagesize=1000&page={page}")
        rows = d.get("data", [])
        if not rows:
            break
        for r in rows:
            n = r["drug_name"].strip()
            if r.get("name_type", "").startswith("G") is False and "G" not in r.get("name_type", ""):
                continue
            low = n.lower()
            if low in seen:
                continue
            if STEM.search(low) or EXTRA.search(low):
                seen.add(low)
                keep.append(n)
        meta = d["metadata"]
        if page % 20 == 0:
            print(f"  page {page}/{meta['total_pages']}  kept {len(keep)}", flush=True)
        if page >= meta["total_pages"]:
            break
        page += 1
    out = Path("data/raw_labels/biologic_names.json")
    out.write_text(json.dumps(sorted(keep), indent=1))
    print(f"kept {len(keep)} candidate biologic generic names -> {out}")


if __name__ == "__main__":
    main()
