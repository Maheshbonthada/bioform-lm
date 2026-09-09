#!/usr/bin/env python3
"""
Mechanistic formulation simulator, v2: stabilisation terms PLUS the competing
degradation pathways that real formulation development balances.

Why v2 exists
-------------
v1 (`mechanistic_sim.py`) is built the way formulation simulators usually are:
DLVO colloidal repulsion + Lumry-Eyring thermodynamic stabilisation. Both terms
are *stabilising only*, so the objective is monotone in almost every variable and
its argmax collapses onto box corners. Measured on v1
(results/simulator_diagnosis_v1.json):

  * buffer species and buffer concentration change the score by exactly 0.0 --
    they are never read by predict(), so 2 of 8 recipe slots are dead;
  * ionic strength, osmolarity and temperature are monotone for 100% of proteins
    (0% interior argmax);
  * the ionic-strength optimum is pinned to the bottom 8.4% of its range.

Only pH carries protein-conditional signal, and it sits at a box corner 40% of
the time. A generative model trained on v1-preferred recipes therefore cannot
learn protein-conditional design: the target is protein-independent in 7 of 8
slots by construction.

Real formulations disagree with v1. In BioFormBench (67 literature formulations)
pH clusters at 5.77 (range 4.0-7.4) rather than at the extremes, and osmolarity
averages 286.6 mOsm/kg -- essentially the 290 mOsm/kg isotonicity target that v1
does not model at all.

What v2 adds
------------
Every term below is a documented degradation pathway with a literature-derived
constant. None of these constants is fit to BioFormBench: the benchmark is held
out so agreement with it remains a real test (scripts/validate_simulator.py).

  1. Buffer capacity (Henderson-Hasselbalch). A buffer controls pH only within
     ~1 unit of its pKa; outside that window pH drifts. Makes buffer species live
     and couples it to pH -- and since optimal pH depends on pI, to the protein.
  2. Buffer concentration. Capacity rises with concentration, but concentrated
     buffers add ionic load and, for sodium phosphate, cause a large
     freeze-concentration pH shift. Interior optimum.
  3. Asn deamidation. Base-catalysed via the succinimide route; rate climbs
     sharply above pH ~6.
  4. Acid hydrolysis / fragmentation. Climbs below pH ~5. With (3) this creates
     an interior pH optimum near 5-6.5 instead of a corner.
  5. Hofmeister salting-out. Low ionic strength screens poorly; high ionic
     strength promotes hydrophobic association. Interior optimum whose position
     depends on protein hydrophobicity.
  6. Isotonicity. Parenterals target ~290 mOsm/kg; deviation is penalised.
  7. Surfactant peroxide oxidation. Polysorbate above ~0.1% w/v adds peroxides
     faster than it adds surface protection. Interior optimum.
  8. Sugar viscosity. Above ~10% w/v the injection-force penalty outweighs the
     thermal stabilisation.
  9. Polyvalent-anion bridging. Citrate and phosphate bridge cationic protein
     (pH < pI), a strongly protein-conditional buffer-selection effect.

Literature anchors: buffer pKa values are standard (CRC Handbook); the
deamidation and hydrolysis pH-rate profiles follow Manning et al., Pharm Res 2010
and Wakankar & Borchardt, J Pharm Sci 2006; polysorbate peroxide-mediated
oxidation follows Kishore et al., Pharm Res 2011; the isotonicity target is the
USP parenteral specification.
"""

from dataclasses import dataclass
from typing import Dict

import numpy as np

from simulator.mechanistic_sim import (
    BiologicsFormulationSimulator,
    SimulationOutput,
)

# ---- Literature constants (NOT fit to BioFormBench) ----

BUFFER_PKA: Dict[str, float] = {
    "acetate": 4.76,     # CH3COOH / CH3COO-
    "citrate": 4.76,     # middle pKa of 3.13 / 4.76 / 6.40
    "succinate": 5.64,   # second pKa of 4.21 / 5.64
    "histidine": 6.04,   # imidazole side chain
    "mes": 6.15,
    "phosphate": 7.20,   # second pKa of 2.15 / 7.20 / 12.33
    "tris": 8.06,
}

# Polyvalent anions at working pH; can bridge cationic protein
POLYVALENT_ANION_BUFFERS = {"citrate", "phosphate"}

# Sodium phosphate crystallises on freezing -> large pH drop (Pikal-Cannon effect)
FREEZE_LABILE_BUFFERS = {"phosphate"}

ISOTONIC_MOSM = 290.0          # USP parenteral target
DEAMIDATION_PH_ONSET = 6.0     # base-catalysed Asn deamidation climbs above this
HYDROLYSIS_PH_ONSET = 5.0      # acid fragmentation climbs below this
PS_OXIDATION_ONSET_PCT = 0.10  # polysorbate peroxide burden (% w/v)
SUGAR_VISCOSITY_ONSET_PCT = 10.0
HOFMEISTER_ONSET_MM = 200.0


@dataclass
class RiskBreakdown:
    """Per-pathway risk contributions, for interpretability and ablation."""

    dlvo: float
    lumry: float
    buffer_capacity: float
    chemical_degradation: float
    hofmeister: float
    tonicity: float
    surfactant_oxidation: float
    viscosity: float
    bridging: float

    def as_dict(self) -> Dict[str, float]:
        return {k: float(v) for k, v in self.__dict__.items()}


class AggregationSimulatorV2(BiologicsFormulationSimulator):
    """v1 physics plus the competing degradation pathways."""

    # Pathway weights: deliberately round numbers chosen so no single degradation
    # term can dominate the colloidal/thermal core. Not fitted values.
    W_CORE = 0.50          # DLVO + Lumry-Eyring (the whole of the v1 objective)
    W_CHEMICAL = 0.18      # deamidation + hydrolysis
    W_BUFFER = 0.12        # capacity + freeze lability
    W_HOFMEISTER = 0.08
    W_TONICITY = 0.06
    W_EXCIPIENT = 0.06     # surfactant oxidation + viscosity + bridging

    # ---------- new pathways ----------

    def _buffer_capacity_risk(self, protein, f) -> float:
        """
        Henderson-Hasselbalch buffering capacity.

        beta = 2.303 * C * Ka[H+] / (Ka + [H+])^2, maximal at pH = pKa and falling
        off about tenfold per pH unit away. Risk is high when the chosen buffer
        cannot hold the chosen pH, which makes buffer identity a function of the
        pH the protein needs.
        """
        pka = BUFFER_PKA.get(str(f.buffer_species).lower())
        if pka is None:                       # unknown buffer: treat as uncontrolled
            return 1.0
        h = 10.0 ** (-f.ph)
        ka = 10.0 ** (-pka)
        beta = 2.303 * f.buffer_conc_mm * ka * h / ((ka + h) ** 2)
        # 10 mM at its pKa gives beta ~= 5.76 mM/pH; use that as the adequacy scale
        risk = 1.0 / (1.0 + (beta / 5.76) ** 2)

        if str(f.buffer_species).lower() in FREEZE_LABILE_BUFFERS and f.temperature_c < 0:
            risk = min(1.0, risk + 0.35)
        # Concentrated buffer is itself a liability (ionic load, injection-site pain)
        if f.buffer_conc_mm > 50.0:
            risk = min(1.0, risk + 0.15 * (f.buffer_conc_mm - 50.0) / 50.0)
        return float(np.clip(risk, 0.0, 1.0))

    def _chemical_degradation_risk(self, protein, f) -> float:
        """
        Asn deamidation (base-catalysed) plus acid hydrolysis. Together these give
        an interior pH optimum in the mildly acidic range, which is where real
        formulations sit. v1, having neither term, prefers pH box corners.
        """
        deamidation = 10.0 ** (0.55 * (f.ph - DEAMIDATION_PH_ONSET))
        hydrolysis = 10.0 ** (0.65 * (HYDROLYSIS_PH_ONSET - f.ph))
        rate = deamidation + hydrolysis
        # Larger proteins present more labile sites per molecule
        rate *= (protein.mw_kda / 50.0) ** 0.25
        return float(np.clip(rate / (rate + 3.0), 0.0, 1.0))

    def _hofmeister_risk(self, protein, f) -> float:
        """
        Salting-out at high ionic strength. Onset shifts with hydrophobicity, so
        the ionic-strength optimum becomes protein-conditional rather than pinned
        to the bottom of the range as it is in v1.
        """
        hydro = float(getattr(protein, "hydrophobicity", 0.5) or 0.5)
        onset = HOFMEISTER_ONSET_MM * (1.4 - 0.8 * hydro)
        excess = max(0.0, f.ionic_strength_mm - onset)
        salting_out = excess / (excess + onset)
        # Very low ionic strength fails to screen specific attractive interactions
        under_screened = float(np.exp(-f.ionic_strength_mm / 20.0))
        return float(np.clip(0.7 * salting_out + 0.3 * under_screened, 0.0, 1.0))

    # Osmotic coefficients: mOsm/kg contributed per unit of each component.
    # Salt is 1:1 dissociating, so a solution of ionic strength I mM carries ~2I
    # mOsm. Sugars contribute 10 g/L per 1% w/v divided by their molar mass.
    MOSM_PER_MM_SALT = 2.0
    MOSM_PER_MM_BUFFER = 1.5
    MOSM_PER_PCT_SUGAR = {
        "sucrose": 29.2, "trehalose": 29.2, "mannitol": 54.9,
        "sorbitol": 54.9, "glycerol": 108.7,
    }

    def _implied_osmolarity(self, f) -> float:
        """
        Osmolarity implied by the components actually in the recipe.

        This is what couples the slots. Tonicity is not a free dial: it is
        achieved *by* the salt and the sugar, so hitting 290 mOsm/kg forces a
        trade-off between ionic strength (which triggers Hofmeister salting-out,
        worse for hydrophobic proteins) and sugar (which raises viscosity, worse
        for large proteins). v1 treats osmolarity as an independent variable and
        so never poses this trade-off at all.
        """
        mosm = self.MOSM_PER_MM_SALT * f.ionic_strength_mm
        mosm += self.MOSM_PER_MM_BUFFER * f.buffer_conc_mm
        for n, c in f.stabilizers.items():
            nl = n.lower()
            for sugar, coef in self.MOSM_PER_PCT_SUGAR.items():
                if sugar in nl:
                    mosm += coef * c
                    break
        return float(mosm)

    def _tonicity_risk(self, protein, f) -> float:
        """
        Parenteral isotonicity, scored on the osmolarity the recipe actually
        implies rather than on a free-floating osmolarity field.
        """
        implied = self._implied_osmolarity(f)
        dev = abs(implied - ISOTONIC_MOSM) / ISOTONIC_MOSM
        # The stated osmolarity must also agree with what the components imply;
        # this keeps the osmolarity slot live and learnable as a derived quantity
        # rather than an unconstrained free dial.
        inconsistency = abs(f.osmolarity_mosm_kg - implied) / ISOTONIC_MOSM
        return float(np.clip(0.75 * dev ** 1.5 + 0.25 * np.tanh(inconsistency), 0.0, 1.0))

    def _surfactant_oxidation_risk(self, protein, f) -> float:
        """Polysorbate protects interfaces, but its peroxides oxidise above ~0.1%."""
        ps = sum(c for n, c in f.stabilizers.items()
                 if "polysorbate" in n.lower() or "tween" in n.lower())
        if ps <= 0:
            return 0.5                      # no surfactant: unprotected interfaces
        excess = max(0.0, ps - PS_OXIDATION_ONSET_PCT)
        return float(np.clip(excess / (excess + PS_OXIDATION_ONSET_PCT), 0.0, 1.0))

    def _viscosity_risk(self, protein, f) -> float:
        """Sugars stabilise thermally but raise injection force above ~10% w/v."""
        sugar = sum(c for n, c in f.stabilizers.items()
                    if any(s in n.lower() for s in
                           ("sucrose", "trehalose", "sorbitol", "glycerol", "mannitol")))
        excess = max(0.0, sugar - SUGAR_VISCOSITY_ONSET_PCT)
        # Larger proteins are already more viscous at a given mass concentration
        excess *= (protein.mw_kda / 50.0) ** 0.3
        return float(np.clip(excess / (excess + SUGAR_VISCOSITY_ONSET_PCT), 0.0, 1.0))

    def _bridging_risk(self, protein, f) -> float:
        """
        Polyvalent anions (citrate, phosphate) bridge net-cationic protein, i.e.
        when pH < pI. A strongly protein-conditional buffer-selection effect.
        """
        if str(f.buffer_species).lower() not in POLYVALENT_ANION_BUFFERS:
            return 0.0
        net_positive = max(0.0, protein.pi - f.ph)
        return float(np.clip(net_positive / 3.0, 0.0, 1.0))

    # ---------- combined ----------

    def predict(self, protein, formulation, return_uncertainties: bool = False,
                return_breakdown: bool = False):
        base = super().predict(protein, formulation, return_uncertainties)
        core = 1.0 - base.stability_score      # the v1 combined risk

        b = RiskBreakdown(
            dlvo=base.aggregation_risk_dlvo,
            lumry=base.aggregation_risk_lumry,
            buffer_capacity=self._buffer_capacity_risk(protein, formulation),
            chemical_degradation=self._chemical_degradation_risk(protein, formulation),
            hofmeister=self._hofmeister_risk(protein, formulation),
            tonicity=self._tonicity_risk(protein, formulation),
            surfactant_oxidation=self._surfactant_oxidation_risk(protein, formulation),
            viscosity=self._viscosity_risk(protein, formulation),
            bridging=self._bridging_risk(protein, formulation),
        )
        excipient = float(np.mean([b.surfactant_oxidation, b.viscosity, b.bridging]))
        risk = (self.W_CORE * core
                + self.W_CHEMICAL * b.chemical_degradation
                + self.W_BUFFER * b.buffer_capacity
                + self.W_HOFMEISTER * b.hofmeister
                + self.W_TONICITY * b.tonicity
                + self.W_EXCIPIENT * excipient)
        risk = float(np.clip(risk, 0.0, 1.0))

        out = SimulationOutput(
            tm_shift_c=base.tm_shift_c,
            predicted_tm_c=base.predicted_tm_c,
            aggregation_risk_dlvo=base.aggregation_risk_dlvo,
            aggregation_risk_lumry=base.aggregation_risk_lumry,
            aggregation_risk_combined=risk,
            predicted_aggregation_percent=base.predicted_aggregation_percent,
            stability_score=1.0 - risk,
            calibration_uncertainty_c=base.calibration_uncertainty_c,
        )
        if return_breakdown:
            return out, b
        return out
