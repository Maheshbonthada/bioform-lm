#!/usr/bin/env python3
"""
Harvest marketed formulations for approved therapeutic antibodies.

For an approved product the label states the exact formulation that expert
developers selected and a regulator reviewed for that specific protein. That
makes it a far better supervision signal for conditional design than a screening
table: every row is a real decision, and every molecule is a named entity whose
sequence we can look up in Thera-SAbDab.

This step only downloads and stores the DESCRIPTION section verbatim. Parsing
into structured fields happens in scripts/parse_labels.py, so that extraction is
reproducible and auditable against the stored source text.
"""
import json, re, sys, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
NS = "{urn:hl7-org:v3}"
DESCRIPTION_LOINC = "34089-3"
OUT = Path("data/raw_labels")
MAX_SPL_PER_INN = 4


def get(url, tries=4, raw=False):
    for k in range(tries):
        try:
            with urlopen(url, timeout=90) as r:
                b = r.read()
            return b if raw else json.loads(b.decode())
        except Exception:
            if k == tries - 1:
                return None
            time.sleep(1.5 * (k + 1))


def description_of(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None
    for sec in root.iter(NS + "section"):
        c = sec.find(NS + "code")
        if c is not None and c.get("code") == DESCRIPTION_LOINC:
            txt = re.sub(r"\s+", " ", "".join(sec.itertext())).strip()
            if len(txt) > 120:
                return txt
    return None


def work(inn):
    d = get(f"{BASE}/spls.json?drug_name={inn}&pagesize={MAX_SPL_PER_INN}")
    if not d or not d.get("data"):
        return inn, []
    rows = []
    for rec in d["data"][:MAX_SPL_PER_INN]:
        xml = get(f"{BASE}/spls/{rec['setid']}.xml", raw=True)
        if not xml:
            continue
        desc = description_of(xml)
        if desc:
            rows.append({"inn": inn, "setid": rec["setid"],
                         "title": rec["title"], "published": rec.get("published_date"),
                         "description": desc})
        time.sleep(0.15)
    return inn, rows


def main():
    tsa = pd.read_csv(OUT / "therasabdab.csv")
    col = "Highest_Clin_Trial (Feb '25)"
    ap = tsa[tsa[col].astype(str).str.contains("Approved", case=False, na=False)]
    inns = sorted(set(ap.Therapeutic.astype(str).str.lower().str.strip()))
    print(f"{len(inns)} approved INNs to query", flush=True)

    all_rows, done = [], 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, i): i for i in inns}
        for f in as_completed(futs):
            inn, rows = f.result()
            all_rows.extend(rows)
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(inns)} INNs, {len(all_rows)} labels", flush=True)

    out = OUT / "label_descriptions.json"
    out.write_text(json.dumps(all_rows, indent=1))
    n_inn = len({r["inn"] for r in all_rows})
    print(f"\n{len(all_rows)} label DESCRIPTION sections for {n_inn} distinct INNs -> {out}")


if __name__ == "__main__":
    main()
