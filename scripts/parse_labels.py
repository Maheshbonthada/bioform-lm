#!/usr/bin/env python3
"""
Parse harvested FDA label DESCRIPTION sections into structured formulations.

Extraction is deterministic: regular expressions over the stored source text plus
a fixed table of molar masses. Nothing is inferred, and every parsed row keeps
the verbatim composition sentence in `source_text`, so any value can be audited
against the label. Fields the label does not state are left missing rather than
defaulted -- the placeholder descriptors in BioFormBench v2 are exactly the
failure this avoids.

Labels state composition in three interchangeable styles, all handled here:

    A  "L-histidine (3 mg), polysorbate 80 (1 mg), trehalose dihydrate (98 mg)"
    B  "136.2 mg alpha,alpha-trehalose dihydrate, 0.6 mg polysorbate 20"
    C  "histidine (8 mM), polysorbate 20 (0.01%)"

Styles A and B give mass per container, so a molar concentration needs the fill
volume: mM = (mg / molar_mass) / volume_mL * 1000, and % w/v = mg / (volume_mL * 10).
Style C is already a concentration and is taken as printed. Sentence splitting
must not break on decimal points, so it splits only at a period followed by
whitespace and a capital letter.
"""
import json
import re
from pathlib import Path

import pandas as pd

# ---- molar masses (g/mol); hydrate forms matter because labels specify them ----
MW = {
    "histidine hydrochloride monohydrate": 209.63,
    "histidine monohydrochloride monohydrate": 209.63,
    "histidine hcl monohydrate": 209.63,
    "histidine hydrochloride": 191.62,
    "histidine": 155.15,
    "sodium citrate dihydrate": 294.10,
    "citrate dihydrate": 294.10,
    "trisodium citrate dihydrate": 294.10,
    "sodium citrate": 258.07,
    "citric acid monohydrate": 210.14,
    "citric acid": 192.12,
    "sodium phosphate monobasic monohydrate": 137.99,
    "monobasic sodium phosphate monohydrate": 137.99,
    "sodium phosphate monobasic dihydrate": 156.01,
    "sodium phosphate monobasic": 119.98,
    "sodium phosphate dibasic dihydrate": 177.99,
    "dibasic sodium phosphate dihydrate": 177.99,
    "sodium phosphate dibasic heptahydrate": 268.07,
    "sodium phosphate dibasic anhydrous": 141.96,
    "sodium phosphate dibasic": 141.96,
    "sodium phosphate": 141.96,
    "potassium phosphate monobasic": 136.09,
    "sodium acetate trihydrate": 136.08,
    "sodium acetate": 82.03,
    "glacial acetic acid": 60.05,
    "acetic acid": 60.05,
    "succinic acid": 118.09,
    "sodium succinate hexahydrate": 270.14,
    "disodium succinate hexahydrate": 270.14,
    "sucrose": 342.30,
    "trehalose dihydrate": 378.33,
    "trehalose": 342.30,
    "sorbitol": 182.17,
    "mannitol": 182.17,
    "glycine": 75.07,
    "arginine hydrochloride": 210.66,
    "arginine hcl": 210.66,
    "arginine": 174.20,
    "methionine": 149.21,
    "proline": 115.13,
    "lysine hydrochloride": 182.65,
    "glutamic acid": 147.13,
    "glutamate": 147.13,
    "sodium chloride": 58.44,
    "edetate disodium dihydrate": 372.24,
    "edetate disodium": 336.21,
}

BUFFER_KEYS = [("histidine", "histidine"), ("citrate", "citrate"),
               ("citric", "citrate"), ("phosphate", "phosphate"),
               ("acetate", "acetate"), ("acetic", "acetate"),
               ("succinate", "succinate"), ("succinic", "succinate"),
               ("tris", "tris"), ("glutamate", "glutamate"),
               ("glutamic", "glutamate")]
SUGARS = ("sucrose", "trehalose", "sorbitol", "mannitol")
AMINO = ("glycine", "arginine", "methionine", "proline", "lysine")

# style A: "trehalose dihydrate (98 mg)" / "histidine (8 mM)" / "polysorbate 80 (0.01%)"
STYLE_A = re.compile(
    r"([A-Za-z][A-Za-z0-9\-\s,\.']{2,55}?)\s*\(\s*(\d+(?:\.\d+)?)\s*"
    r"(mg|g|mcg|mM|%|% ?w/v)\s*\)", re.I)
# style B: "136.2 mg alpha,alpha-trehalose dihydrate"
STYLE_B = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg|g|mcg)\s+(?:of\s+)?"
    r"([A-Za-z][A-Za-z0-9,\-\s\.']{2,55}?)"
    r"(?=\s*(?:,|;|\band\b|\bat\b|\bper\b|\bin\b|\.\s+[A-Z]|$))", re.I)

PH = re.compile(r"pH\s*(?:of\s*)?(?:approximately|about|approx\.?|ca\.?|~)?\s*"
                r"(\d(?:\.\d+)?)(?:\s*(?:to|-|–)\s*(\d(?:\.\d+)?))?", re.I)
MWKDA = re.compile(r"molecular weight of (?:approximately\s*)?"
                   r"(\d[\d,]*(?:\.\d+)?)\s*(kilodalton|kda|dalton)", re.I)
# volume of the container: "Each 2 mL single-dose vial", "per 0.8 mL", "in 1 mL"
VOL_EACH = re.compile(r"each\s+(\d+(?:\.\d+)?)\s*mL", re.I)
VOL_PER = re.compile(r"(?:per|in|delivers?|withdraw(?:able)?|yields?)\s+"
                     r"(?:a\s+)?(\d+(?:\.\d+)?)\s*mL", re.I)
CONC_SLASH = re.compile(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*(\d+(?:\.\d+)?)?\s*mL", re.I)


def sentences(txt):
    return re.split(r"(?<=\.)\s+(?=[A-Z])", txt)


def norm(raw):
    s = raw.lower().strip(" .,;:-")
    s = s.replace("α", "").replace("β", "").replace("–", "-")
    s = re.sub(r"\b(l|d|dl)\s*-\s*", "", s)
    s = re.sub(r"[,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def lookup_mw(name):
    for k in sorted(MW, key=len, reverse=True):
        if k in name:
            return MW[k]
    return None


def composition_sentences(txt):
    """Sentences that actually enumerate excipients."""
    keys = ("polysorbate", "sucrose", "trehalose", "histidine", "sorbitol",
            "arginine", "mannitol", "citrate", "phosphate", "acetate",
            "sodium chloride", "poloxamer", "glycine", "methionine")
    return [s for s in sentences(txt)
            if sum(k in s.lower() for k in keys) >= 2
            and re.search(r"\d", s)]


def presentation_chunks(span):
    """
    A single label often describes several presentations ("Each 75 mg/mL pen
    contains ... Each 150 mg/mL pen contains ..."), which are genuinely different
    formulations of the same protein and become separate rows.
    """
    starts = [m.start() for m in re.finditer(r"\bEach\b", span)]
    if len(starts) < 2:
        return [span]
    bounds = starts + [len(span)]
    parts = [span[bounds[i]:bounds[i + 1]].strip() for i in range(len(starts))]
    parts = [q for q in parts if len(q) > 40 and re.search(r"\d", q)]
    return parts or [span]


def chunk_volume(chunk):
    """
    Fill volume in mL. Preferred order: an explicit volume, then mass divided by
    stated concentration ("Each 75 mg/mL pen contains 75 mg alirocumab" -> 1 mL).
    """
    for rx in (VOL_EACH, VOL_PER):
        hits = [float(x.group(1)) for x in rx.finditer(chunk)]
        if hits:
            return hits[0]
    for cm in CONC_SLASH.finditer(chunk):
        if cm.group(2):
            return float(cm.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*mL", chunk, re.I)
    if m:
        conc = float(m.group(1))
        m2 = re.search(r"contains?\s+(?:about\s+)?(\d+(?:\.\d+)?)\s*mg", chunk, re.I)
        if m2 and conc > 0:
            return float(m2.group(1)) / conc
    return None


def parse_one(rec):
    """Return one row per presentation described in this label."""
    txt = rec["description"]
    base = {"inn": rec["inn"], "setid": rec["setid"], "title": rec["title"],
            "published": rec.get("published")}

    m = MWKDA.search(txt)
    if m:
        v = float(m.group(1).replace(",", ""))
        base["label_mw_kda"] = v / 1000.0 if m.group(2).lower() == "dalton" and v > 5000 else v

    base["route"] = ("subcutaneous" if re.search(r"subcutaneous", txt, re.I)
                     else "intravenous" if re.search(r"intravenous", txt, re.I) else None)
    base["lyophilized"] = bool(re.search(r"lyophiliz|lyophilis", txt, re.I))

    doc_ph = PH.search(txt)

    comp = composition_sentences(txt)
    if not comp:
        return [base]

    rows = []
    for ci, chunk in enumerate(presentation_chunks(" ".join(comp))):
        out = dict(base)
        out["presentation_index"] = ci
        out["source_text"] = chunk[:1000]

        # Provenance matters: a pH stated inside the composition sentence is the
        # formulation pH, whereas a document-level fallback may be a
        # reconstitution or diluent pH. Downstream analysis stratifies on this.
        m_chunk = PH.search(chunk)
        m = m_chunk or doc_ph
        if m:
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else None
            out["ph"] = round((lo + hi) / 2, 2) if hi else lo
            out["ph_is_range"] = bool(hi)
            out["ph_from_composition"] = m_chunk is not None

        vol = chunk_volume(chunk)
        out["fill_volume_ml"] = vol

        cm = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*mL", chunk, re.I)
        if cm:
            out["protein_conc_mg_ml"] = float(cm.group(1))
        else:
            cs = CONC_SLASH.search(chunk)
            if cs and cs.group(2):
                out["protein_conc_mg_ml"] = round(float(cs.group(1)) / float(cs.group(2)), 2)

        found = {}
        for am in STYLE_A.finditer(chunk):
            found[norm(am.group(1))] = (float(am.group(2)), am.group(3).lower())
        for bm in STYLE_B.finditer(chunk):
            n = norm(bm.group(3))
            if n and n not in found:
                found[n] = (float(bm.group(1)), bm.group(2).lower())

        buf_species, buf_mm, n_used = None, 0.0, 0
        for name, (amt, unit) in found.items():
            if not name or len(name) < 3:
                continue
            if rec["inn"][:8] in name or "water for injection" in name:
                continue
            mm = pct = None
            if unit == "mm":
                mm = amt
            elif unit in ("%", "% w/v"):
                pct = amt
            elif vol and vol > 0:
                mg = amt * (1000 if unit == "g" else 0.001 if unit == "mcg" else 1)
                mmass = lookup_mw(name)
                if mmass:
                    mm = mg / mmass / vol * 1000.0
                pct = mg / (vol * 10.0)
            if mm is None and pct is None:
                continue
            n_used += 1

            for key, canon in BUFFER_KEYS:
                if key in name:
                    if mm is not None:
                        buf_mm += mm
                        buf_species = canon if buf_species in (None, canon) else                             (buf_species if canon in buf_species.split("+")
                             else f"{buf_species}+{canon}")
                    break
            for sg in SUGARS:
                if sg in name:
                    if mm is not None:
                        out[f"{sg}_mm"] = round(mm, 2)
                    if pct is not None:
                        out[f"{sg}_pct_wv"] = round(pct, 4)
            for a in AMINO:
                if a in name and mm is not None:
                    out[f"{a}_mm"] = round(mm, 2)
            if "polysorbate" in name or "poloxamer" in name:
                out["surfactant"] = ("polysorbate 80" if "80" in name else
                                     "polysorbate 20" if "20" in name else "poloxamer 188")
                if pct is not None:
                    out["surfactant_pct_wv"] = round(pct, 5)
            if "sodium chloride" in name and mm is not None:
                out["nacl_mm"] = round(mm, 2)

        out["n_ingredients_parsed"] = n_used
        if buf_species:
            out["buffer_species"] = buf_species
            out["buffer_conc_mm"] = round(buf_mm, 2)
        rows.append(out)
    return rows


def main():
    recs = json.loads(Path("data/raw_labels/label_descriptions.json").read_text())
    rows = []
    for r in recs:
        rows.extend(parse_one(r))
    df = pd.DataFrame(rows)
    if "buffer_species" not in df:
        df["buffer_species"] = None
    df["usable"] = df.ph.notna() & df.buffer_species.notna() & (df.buffer_conc_mm > 0)
    out = Path("data/raw_labels/parsed_formulations.csv")
    df.to_csv(out, index=False)

    def cnt(c):
        return int(df[c].notna().sum()) if c in df else 0

    print(f"parsed {len(recs)} labels -> {len(df)} presentation rows -> {out}")
    for c in ("ph", "buffer_species", "surfactant", "nacl_mm", "sucrose_mm",
              "trehalose_mm", "protein_conc_mg_ml", "label_mw_kda"):
        print(f"  {c:22s}: {cnt(c)}")
    u = df[df.usable]
    print(f"  USABLE (pH+buffer)    : {len(u)} rows, {u.inn.nunique()} distinct INNs")
    if len(u):
        print("buffer:", u.buffer_species.value_counts().head(10).to_dict())
        print("pH: min %.1f mean %.2f max %.1f" % (u.ph.min(), u.ph.mean(), u.ph.max()))
        print("route:", u.route.value_counts().to_dict())


if __name__ == "__main__":
    main()
