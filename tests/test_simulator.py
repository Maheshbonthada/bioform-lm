"""
Unit Tests for BiologicsFormulationSimulator
Tests all sub-models, physics validation, and edge cases.
Run with: pytest tests/test_simulator.py -v
"""

import pytest
import numpy as np
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.mechanistic_sim import (
    BiologicsFormulationSimulator,
    ProteinDescriptor,
    FormulationComposition,
    SimulationOutput,
)


class TestProteinDescriptor:
    """Test protein descriptor validation."""

    def test_valid_descriptor(self):
        """Valid protein descriptor should instantiate."""
        protein = ProteinDescriptor(
            mw_kda=100.0,
            pi=7.0,
            hydrophobicity=0.5,
            tm_baseline_c=65.0,
        )
        assert protein.mw_kda == 100.0
        assert protein.pi == 7.0

    def test_invalid_mw_too_small(self):
        """MW < 1 kDa should raise."""
        with pytest.raises(AssertionError):
            ProteinDescriptor(
                mw_kda=0.5,
                pi=7.0,
                hydrophobicity=0.5,
                tm_baseline_c=65.0,
            )

    def test_invalid_mw_too_large(self):
        """MW > 500 kDa should raise."""
        with pytest.raises(AssertionError):
            ProteinDescriptor(
                mw_kda=600.0,
                pi=7.0,
                hydrophobicity=0.5,
                tm_baseline_c=65.0,
            )

    def test_invalid_pi(self):
        """pI out of range should raise."""
        with pytest.raises(AssertionError):
            ProteinDescriptor(
                mw_kda=100.0,
                pi=0.5,  # too low
                hydrophobicity=0.5,
                tm_baseline_c=65.0,
            )

    def test_invalid_tm(self):
        """Tm out of range should raise."""
        with pytest.raises(AssertionError):
            ProteinDescriptor(
                mw_kda=100.0,
                pi=7.0,
                hydrophobicity=0.5,
                tm_baseline_c=10.0,  # too low
            )


class TestFormulationComposition:
    """Test formulation composition validation."""

    def test_valid_formulation(self):
        """Valid formulation should instantiate."""
        form = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=300.0,
            stabilizers={"polysorbate_80": 0.2},
        )
        assert form.ph == 6.0

    def test_invalid_ph(self):
        """pH out of range should raise."""
        with pytest.raises(AssertionError):
            FormulationComposition(
                buffer_species="histidine",
                buffer_conc_mm=20.0,
                ph=1.0,  # too low
                ionic_strength_mm=150.0,
                osmolarity_mosm_kg=300.0,
                stabilizers={},
            )

    def test_invalid_osmolarity(self):
        """Osmolarity out of range should raise."""
        with pytest.raises(AssertionError):
            FormulationComposition(
                buffer_species="histidine",
                buffer_conc_mm=20.0,
                ph=6.0,
                ionic_strength_mm=150.0,
                osmolarity_mosm_kg=20.0,  # too low
                stabilizers={},
            )


class TestSimulator:
    """Test BiologicsFormulationSimulator."""

    @pytest.fixture
    def simulator(self):
        """Initialize simulator."""
        return BiologicsFormulationSimulator()

    @pytest.fixture
    def antibody(self):
        """Standard antibody (IgG-like)."""
        return ProteinDescriptor(
            mw_kda=150.0,
            pi=8.0,
            hydrophobicity=0.4,
            tm_baseline_c=70.0,
            name="TestAntibody"
        )

    @pytest.fixture
    def good_formulation(self):
        """Optimized formulation (should be stable)."""
        return FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={
                "polysorbate_80": 0.2,
                "sucrose": 5.0,
            },
            temperature_c=25.0,
        )

    @pytest.fixture
    def bad_formulation(self):
        """Poor formulation (should be unstable)."""
        return FormulationComposition(
            buffer_species="acetate",
            buffer_conc_mm=5.0,
            ph=10.0,  # far from pI=8
            ionic_strength_mm=50.0,  # too low
            osmolarity_mosm_kg=100.0,  # hypotonic
            stabilizers={},
            temperature_c=40.0,  # high temp
        )

    def test_simulator_initialization(self, simulator):
        """Simulator should initialize."""
        assert simulator is not None
        assert simulator.hamaker_constant > 0
        assert simulator.ph_penalty > 0

    def test_prediction_returns_output(self, simulator, antibody, good_formulation):
        """Predict should return valid SimulationOutput."""
        output = simulator.predict(antibody, good_formulation)
        assert isinstance(output, SimulationOutput)
        assert 0 <= output.stability_score <= 1
        assert 0 <= output.aggregation_risk_combined <= 1

    def test_good_formulation_is_stable(self, simulator, antibody, good_formulation):
        """Good formulation should result in less aggregation than poor formulation."""
        output_good = simulator.predict(antibody, good_formulation)

        # Bad formulation: high temperature + hypotonic + no stabilizers
        bad_form = FormulationComposition(
            buffer_species="phosphate",
            buffer_conc_mm=10.0,
            ph=7.0,
            ionic_strength_mm=50.0,  # low IS
            osmolarity_mosm_kg=150.0,  # hypotonic
            stabilizers={},  # no stabilizers
            temperature_c=37.0,  # warm storage
        )
        output_bad = simulator.predict(antibody, bad_form)

        # Good should have less aggregation
        assert output_good.predicted_aggregation_percent < output_bad.predicted_aggregation_percent, \
            f"Good formulation should have less aggregation: {output_good.predicted_aggregation_percent}% vs {output_bad.predicted_aggregation_percent}%"

    def test_bad_formulation_is_unstable(self, simulator, antibody, bad_formulation):
        """Bad formulation should have lower aggregation than good formulation."""
        output_bad = simulator.predict(antibody, bad_formulation)

        good_form = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={"sucrose": 5.0},
            temperature_c=25.0,
        )
        output_good = simulator.predict(antibody, good_form)

        assert output_bad.predicted_aggregation_percent > output_good.predicted_aggregation_percent, \
            f"Bad formulation should have more aggregation"

    def test_ph_effect_on_stability(self, simulator, antibody):
        """Lumry-Eyring Tm should decrease when pH is far from optimal pI."""
        formulation_near_pi = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=8.0,  # == pI, optimal for Lumry-Eyring
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={"sucrose": 5.0},
            temperature_c=25.0,
        )

        formulation_far_pi = FormulationComposition(
            buffer_species="acetate",
            buffer_conc_mm=20.0,
            ph=4.0,  # far from pI=8, suboptimal
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={"sucrose": 5.0},  # same stabilizer
            temperature_c=25.0,
        )

        out_near = simulator.predict(antibody, formulation_near_pi)
        out_far = simulator.predict(antibody, formulation_far_pi)

        # Tm shift should be larger (less negative) at optimal pH
        assert out_near.tm_shift_c > out_far.tm_shift_c, \
            f"Tm shift should be larger at optimal pH: {out_near.tm_shift_c} vs {out_far.tm_shift_c}"

    def test_stabilizer_effect_positive(self, simulator, antibody):
        """Stabilizers should increase Tm shift."""
        form_no_stab = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=7.0,  # closer to optimal
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={},
        )

        form_with_stab = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=7.0,  # same pH
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={"sucrose": 5.0, "polysorbate_80": 0.2},
        )

        out_no = simulator.predict(antibody, form_no_stab)
        out_yes = simulator.predict(antibody, form_with_stab)

        assert out_yes.tm_shift_c > out_no.tm_shift_c, \
            f"Stabilizers should increase Tm shift: {out_yes.tm_shift_c} vs {out_no.tm_shift_c}"

    def test_ionic_strength_effect(self, simulator, antibody):
        """Ionic strength should affect electrostatic repulsion."""
        form_low_is = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=20.0,  # very low
            osmolarity_mosm_kg=150.0,
            stabilizers={},
        )

        form_high_is = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=300.0,  # high
            osmolarity_mosm_kg=450.0,
            stabilizers={},
        )

        out_low = simulator.predict(antibody, form_low_is)
        out_high = simulator.predict(antibody, form_high_is)

        # Low ionic strength = stronger electrostatic repulsion
        assert out_low.aggregation_risk_dlvo < out_high.aggregation_risk_dlvo, \
            "Low ionic strength should give lower aggregation risk (stronger repulsion)"

    def test_temperature_effect(self, simulator, antibody, good_formulation):
        """Higher temperature should reduce stability."""
        form_cold = FormulationComposition(
            buffer_species=good_formulation.buffer_species,
            buffer_conc_mm=good_formulation.buffer_conc_mm,
            ph=good_formulation.ph,
            ionic_strength_mm=good_formulation.ionic_strength_mm,
            osmolarity_mosm_kg=good_formulation.osmolarity_mosm_kg,
            stabilizers=good_formulation.stabilizers,
            temperature_c=4.0,
        )

        form_warm = FormulationComposition(
            buffer_species=good_formulation.buffer_species,
            buffer_conc_mm=good_formulation.buffer_conc_mm,
            ph=good_formulation.ph,
            ionic_strength_mm=good_formulation.ionic_strength_mm,
            osmolarity_mosm_kg=good_formulation.osmolarity_mosm_kg,
            stabilizers=good_formulation.stabilizers,
            temperature_c=37.0,
        )

        out_cold = simulator.predict(antibody, form_cold)
        out_warm = simulator.predict(antibody, form_warm)

        assert out_warm.predicted_aggregation_percent > out_cold.predicted_aggregation_percent, \
            "Aggregation should increase at higher temperature"

    def test_output_ranges(self, simulator, antibody, good_formulation):
        """All output values should be in valid ranges."""
        output = simulator.predict(antibody, good_formulation)

        assert 0 <= output.aggregation_risk_dlvo <= 1
        assert 0 <= output.aggregation_risk_lumry <= 1
        assert 0 <= output.aggregation_risk_combined <= 1
        assert 0 <= output.predicted_aggregation_percent <= 100
        assert 0 <= output.stability_score <= 1
        assert output.calibration_uncertainty_c > 0

    def test_to_dict(self, simulator, antibody, good_formulation):
        """Output should convert to dict."""
        output = simulator.predict(antibody, good_formulation)
        d = output.to_dict()
        assert isinstance(d, dict)
        assert "tm_shift_c" in d
        assert "stability_score" in d

    def test_uncertainty_estimation(self, simulator, antibody):
        """Uncertainty should be higher for extreme proteins."""
        form = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={},
        )

        # Normal protein
        normal_protein = ProteinDescriptor(
            mw_kda=100.0,
            pi=7.0,
            hydrophobicity=0.5,
            tm_baseline_c=65.0,
        )

        # Extreme protein
        extreme_protein = ProteinDescriptor(
            mw_kda=10.0,  # very small
            pi=4.0,  # very acidic
            hydrophobicity=0.2,
            tm_baseline_c=45.0,  # low Tm
        )

        out_normal = simulator.predict(normal_protein, form)
        out_extreme = simulator.predict(extreme_protein, form)

        assert out_extreme.calibration_uncertainty_c > out_normal.calibration_uncertainty_c, \
            "Extreme proteins should have higher uncertainty"

    def test_reproducibility(self, simulator, antibody, good_formulation):
        """Same input should give same output."""
        out1 = simulator.predict(antibody, good_formulation)
        out2 = simulator.predict(antibody, good_formulation)

        assert out1.stability_score == out2.stability_score
        assert out1.tm_shift_c == out2.tm_shift_c

    def test_debye_length_calculation(self, simulator):
        """Debye length should decrease with ionic strength."""
        # Low ionic strength → large Debye length
        debye_low = simulator._debye_length_from_ionic_strength(10.0)

        # High ionic strength → small Debye length
        debye_high = simulator._debye_length_from_ionic_strength(500.0)

        assert debye_low > debye_high, "Debye length should decrease with ionic strength"

    def test_protein_radius_calculation(self, simulator):
        """Protein radius should scale with MW."""
        r_small = simulator._protein_radius_from_mw(10.0)  # kDa
        r_large = simulator._protein_radius_from_mw(150.0)  # kDa

        assert r_large > r_small, "Larger proteins should have larger radius"
        assert r_small > 0, "Radius must be positive"

    def test_steric_layer_from_surfactant(self, simulator):
        """Surfactants should increase steric layer thickness."""
        form_no_surf = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={},
        )

        form_with_surf = FormulationComposition(
            buffer_species="histidine",
            buffer_conc_mm=20.0,
            ph=6.0,
            ionic_strength_mm=150.0,
            osmolarity_mosm_kg=310.0,
            stabilizers={"polysorbate_80": 0.5},
        )

        thick_no = simulator._steric_layer_thickness(form_no_surf)
        thick_yes = simulator._steric_layer_thickness(form_with_surf)

        assert thick_yes > thick_no, "Surfactants should increase steric layer"

    def test_batch_predictions(self, simulator, antibody):
        """Should handle multiple formulations."""
        formulations = [
            FormulationComposition(
                buffer_species="histidine",
                buffer_conc_mm=20 + i*10,
                ph=6.0,
                ionic_strength_mm=150.0,
                osmolarity_mosm_kg=310.0,
                stabilizers={},
            )
            for i in range(5)
        ]

        outputs = [simulator.predict(antibody, form) for form in formulations]

        assert len(outputs) == 5
        for out in outputs:
            assert 0 <= out.stability_score <= 1


class TestSimulatorValidation:
    """Test validation against literature data."""

    @pytest.fixture
    def simulator(self):
        return BiologicsFormulationSimulator()

    def test_validation_on_mock_data(self, simulator):
        """Simulator should validate against mock literature data."""
        mock_literature = [
            {
                "protein": {
                    "mw_kda": 100.0,
                    "pi": 7.0,
                    "hydrophobicity": 0.5,
                    "tm_baseline_c": 65.0,
                },
                "formulation": {
                    "buffer_species": "histidine",
                    "buffer_conc_mm": 20.0,
                    "ph": 6.0,
                    "ionic_strength_mm": 150.0,
                    "osmolarity_mosm_kg": 310.0,
                    "stabilizers": {"sucrose": 5.0},
                    "temperature_c": 25.0,
                    "storage_duration_days": 7.0,
                },
                "measured_tm_shift": 2.5,
            },
            {
                "protein": {
                    "mw_kda": 50.0,
                    "pi": 5.0,
                    "hydrophobicity": 0.3,
                    "tm_baseline_c": 60.0,
                },
                "formulation": {
                    "buffer_species": "phosphate",
                    "buffer_conc_mm": 50.0,
                    "ph": 7.0,
                    "ionic_strength_mm": 200.0,
                    "osmolarity_mosm_kg": 350.0,
                    "stabilizers": {},
                    "temperature_c": 25.0,
                    "storage_duration_days": 7.0,
                },
                "measured_tm_shift": 0.5,
            },
            {
                "protein": {
                    "mw_kda": 75.0,
                    "pi": 6.5,
                    "hydrophobicity": 0.4,
                    "tm_baseline_c": 62.0,
                },
                "formulation": {
                    "buffer_species": "tris",
                    "buffer_conc_mm": 25.0,
                    "ph": 7.5,
                    "ionic_strength_mm": 140.0,
                    "osmolarity_mosm_kg": 300.0,
                    "stabilizers": {"polysorbate_80": 0.1},
                    "temperature_c": 25.0,
                    "storage_duration_days": 7.0,
                },
                "measured_tm_shift": 1.0,
            },
        ]

        metrics = simulator.validate_on_literature_data(mock_literature)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert "r2" in metrics
        assert metrics["n_samples"] == 3
        assert metrics["mae"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
