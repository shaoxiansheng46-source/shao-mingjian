"""Independent Phase 4B winding-loss tests.

These tests use hand-computed resistivity/area values for the native model;
they do not use the service output as the expected value.  OpenMagnetics is
covered by the isolated benchmark because the normal test environment does
not require the third-party runtime.
"""

from __future__ import annotations

import math

import pytest

from backend.app.geometry import CoreGeometry, WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.winding_loss import CurrentWaveform, LitzWireSpecification, WindingLossService
from backend.app.winding_loss.service import analyze_current_waveform
from backend.app.providers.openmagnetics.provider import _sum_turn_loss_components


def _core() -> CoreGeometry:
    return CoreGeometry(
        core_id="phase4b-test-core",
        shape_name="test",
        material_name="test-copper-case",
        physical_dimensions_m={},
        effective_area_m2=1e-4,
        effective_length_m=0.1,
        effective_volume_m3=1e-5,
        window_width_m=0.02,
        window_height_m=0.02,
        winding_column_width_m=0.01,
        winding_column_depth_m=0.01,
        bobbin_wall_m=0.001,
        data_status="independent_test_fixture",
    )


def _spec(*, rho: float = 2e-8) -> LitzWireSpecification:
    return LitzWireSpecification(
        manufacturer="independent-test-fixture",
        model="fixture-litz-4x0.5",
        data_source="independent analytical test input",
        strand_bare_diameter_m=0.0005,
        strand_insulated_diameter_m=0.00055,
        number_strands=4,
        finished_outer_diameter_m=0.001,
        conductor_material="copper",
        resistivity_ohm_m=rho,
        conductor_area_m2=1e-6,
        data_status="independent_test_fixture",
        engineering_approved=False,
    )


def _layout(template: str = "PS"):
    wire = WireGeometry("fixture", 0.001, 0.0005, number_conductors=1, data_status="independent_test_fixture")
    specs = [
        WindingSpec("Primary", "primary", 6, wire),
        WindingSpec("Secondary", "secondary", 2, wire),
    ]
    order = ["P", "S"] if template == "PS" else ["P1", "S", "P2"]
    return build_layout(
        _core(),
        specs,
        WindingLayout(template, order, main_insulation_m=0.0005, winding_to_core_clearance_m=0.0005),
        provenance={"data_status": "independent_test_fixture", "synthetic": False, "demo_only": False, "engineering_approved": False},
    )


def _waveforms() -> dict[str, CurrentWaveform]:
    frequency = 10_000.0
    period = 1.0 / frequency
    times = tuple(period * index / 16.0 for index in range(16))
    return {
        "Primary": CurrentWaveform("Primary", frequency, times, tuple(2.0 + math.sqrt(2.0) * math.sin(2.0 * math.pi * frequency * time) for time in times)),
        "Secondary": CurrentWaveform("Secondary", frequency, times, tuple(0.5 for _ in times)),
    }


def test_litz_record_does_not_infer_finished_outer_diameter():
    record = {
        "name": "record-with-range-only",
        "manufacturer": "fixture",
        "type": "litz",
        "number_conductors": 100,
        "conducting_diameter_m": 20e-6,
        "outer_diameter_m": {"minimum": 1e-3, "maximum": 1.2e-3, "nominal": None},
    }
    spec = LitzWireSpecification.from_provider_record(record)
    assert spec.finished_outer_diameter_m is None
    assert "finished_outer_diameter_nominal" in spec.missing_parameters
    with pytest.raises(ValueError, match="MISSING_LITZ_PARAMETER"):
        spec.geometry_diameter_m()
    assert spec.geometry_diameter_m(policy="database_maximum") == pytest.approx(1.2e-3)


def test_waveform_harmonics_use_independent_dc_and_rms_values():
    spectrum = analyze_current_waveform(_waveforms()["Primary"], harmonic_limit=8)
    assert spectrum.dc_a == pytest.approx(2.0, abs=1e-12)
    assert spectrum.rms_a == pytest.approx(math.sqrt(5.0), abs=1e-12)
    assert spectrum.ac_rms_a == pytest.approx(1.0, abs=1e-12)
    fundamental = next(item for item in spectrum.components if item.order == 1)
    assert fundamental.rms_a == pytest.approx(1.0, abs=1e-12)


def test_native_dc_matches_independent_length_resistance_formula():
    layout = _layout("PS")
    spec = _spec()
    result = WindingLossService().calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=_waveforms(), model="native_dc", temperature_c=20.0)
    assert result["status"] == "ok"
    expected_total = 0.0
    for block in layout.blocks:
        lead_per_branch = max(block.branch_length_m - block.mean_turn_length_m, 0.0)
        branch_length = sum(turn.length_m for turn in block.turns_geometry) / block.parallels + lead_per_branch
        expected_r = spec.resistivity_ohm_m * branch_length / spec.bare_copper_area_m2 / block.parallels
        # The primary waveform is DC + one sine: RMS^2 = 2^2 + 1^2.
        current_square = 5.0 if block.role == "primary" else 0.25
        assert result["windings"][block.name]["rdc_ohm"] == pytest.approx(expected_r)
        expected_total += current_square * expected_r
    assert result["ohmic_loss_w"] == pytest.approx(expected_total)


def test_temperature_increases_rdc_and_loss():
    layout = _layout("PS")
    spec = _spec()
    low = WindingLossService().calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=_waveforms(), model="native_dc", temperature_c=20.0)
    high = WindingLossService().calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=_waveforms(), model="native_dc", temperature_c=80.0)
    expected_ratio = 1.0 + spec.temperature_coefficient_per_c * 60.0
    assert high["ohmic_loss_w"] / low["ohmic_loss_w"] == pytest.approx(expected_ratio)


def test_psp_primary_segments_are_series_once():
    layout = _layout("PSP")
    result = WindingLossService().calculate(layout, wire_specs={"Primary": _spec(), "Secondary": _spec()}, waveforms=_waveforms(), model="native_dc", temperature_c=20.0)
    assert result["status"] == "ok"
    primary = result["electrical_windings"]["Primary"]
    assert primary["blocks"] == ["P1", "P2"]
    assert primary["rdc_ohm"] == pytest.approx(sum(result["windings"][name]["rdc_ohm"] for name in ("P1", "P2")))
    assert primary["ohmic_loss_w"] == pytest.approx(sum(result["windings"][name]["ohmic_loss_w"] for name in ("P1", "P2")))


def test_missing_litz_specification_is_not_zero():
    result = WindingLossService().calculate(_layout("PS"), wire_specs={}, waveforms=_waveforms(), model="native_dc")
    assert result["status"] == "partial"
    assert result["value"] is None
    assert any(item["code"] == "MISSING_LITZ_SPECIFICATION" for item in result["diagnostics"])


def test_openmagnetics_model_requires_operating_point():
    class AvailableProvider:
        available = True

    result = WindingLossService(provider=AvailableProvider()).calculate(_layout("PS"), wire_specs={"Primary": _spec(), "Secondary": _spec()}, waveforms=_waveforms(), model="openmagnetics_skin")
    assert result["status"] == "input_invalid"
    assert result["value"] is None
    assert any(item["code"] == "MISSING_OPERATING_POINT" for item in result["diagnostics"])


def test_mkf_turn_loss_component_aggregation_preserves_harmonic_values():
    output = {
        "windingLossesPerTurn": [
            {"proximityEffectLosses": {"lossesPerHarmonic": [0.0, 1.25e-6]}},
            {"proximityEffectLosses": {"lossesPerHarmonic": [0.0, 0.75e-6]}},
            {"proximityEffectLosses": None},
        ]
    }
    value, count = _sum_turn_loss_components(output, "proximityEffectLosses")
    assert value == pytest.approx(2.0e-6)
    assert count == 2
