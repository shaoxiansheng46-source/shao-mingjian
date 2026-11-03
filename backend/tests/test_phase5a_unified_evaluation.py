from __future__ import annotations

import math

import pytest

from backend.app.evaluation import (
    EvaluationCandidate,
    EvaluationContext,
    OperatingPointSnapshot,
    UnifiedEvaluationService,
)
from backend.app.geometry import CoreGeometry, WireGeometry, WindingSpec, build_layout
from backend.app.winding_loss import CurrentWaveform, LitzWireSpecification


def _core(*, window_width_m: float = 0.03) -> CoreGeometry:
    return CoreGeometry(
        core_id="phase5a-test-core",
        shape_name="TEST_SHAPE",
        material_name="TEST_MATERIAL",
        physical_dimensions_m={"outer_width_m": 0.04},
        effective_area_m2=2.8e-4,
        effective_length_m=0.129,
        effective_volume_m3=3.6e-5,
        window_width_m=window_width_m,
        window_height_m=0.03,
        winding_column_width_m=0.01,
        winding_column_depth_m=0.01,
        bobbin_wall_m=0.001,
        gap_m=0.0,
        mass_kg=1.0,
        data_status="independent_test_fixture",
    )


def _wire() -> WireGeometry:
    return WireGeometry(
        wire_id="PHASE5A_WIRE",
        outer_diameter_m=0.001,
        conducting_diameter_m=0.0005,
        resistance_ohm_per_m=0.08,
        number_conductors=1,
        data_status="independent_test_fixture",
    )


def _litz() -> LitzWireSpecification:
    return LitzWireSpecification(
        manufacturer="independent-test-fixture",
        model="phase5a-litz",
        data_source="independent analytical test input",
        strand_bare_diameter_m=0.0005,
        strand_insulated_diameter_m=0.00055,
        number_strands=4,
        finished_outer_diameter_m=0.001,
        conductor_material="copper",
        resistivity_ohm_m=2.0e-8,
        conductor_area_m2=1.0e-6,
        data_status="independent_test_fixture",
    )


def _layout(template: str = "PS", *, width: float = 0.03):
    wire = _wire()
    return build_layout(
        _core(window_width_m=width),
        [WindingSpec("Primary", "primary", 20, wire), WindingSpec("Secondary", "secondary", 5, wire)],
        template,
        provenance={
            "data_status": "independent_test_fixture",
            "synthetic": False,
            "demo_only": False,
            "engineering_approved": False,
        },
    )


def _waveforms() -> dict[str, CurrentWaveform]:
    frequency = 10_000.0
    period = 1.0 / frequency
    times = tuple(period * index / 16.0 for index in range(17))
    return {
        "Primary": CurrentWaveform("Primary", frequency, times, tuple(1.0 for _ in times)),
        "Secondary": CurrentWaveform("Secondary", frequency, times, tuple(-4.0 for _ in times)),
    }


def _operating_point(*, current_primary: float = 1.0) -> OperatingPointSnapshot:
    return OperatingPointSnapshot(
        point_id="rated",
        voltage_primary_v=800.0,
        voltage_secondary_v=400.0,
        power_w=1000.0,
        frequency_hz=10_000.0,
        ambient_c=40.0,
        currents_rms_a={"Primary": current_primary, "Secondary": -4.0},
        current_waveforms=_waveforms(),
    )


def _candidate(template: str = "PS", *, width: float = 0.03) -> EvaluationCandidate:
    layout = _layout(template, width=width)
    return EvaluationCandidate(
        layout=layout,
        wire_specs={"Primary": _litz(), "Secondary": _litz()},
        data_snapshot={"data_version": "phase5a-fixture", "data_hashes": {"fixture": "fixed"}},
        record_ids={"core": "phase5a-test-core", "wire_primary": "phase5a-litz", "wire_secondary": "phase5a-litz"},
    )


def _service() -> UnifiedEvaluationService:
    return UnifiedEvaluationService()


def test_unified_evaluation_uses_one_candidate_and_excitation_snapshot() -> None:
    result = _service().evaluate(
        _candidate(),
        _operating_point(),
        context=EvaluationContext(
            data_snapshot={"data_version": "phase5a-fixture", "data_hashes": {"fixture": "fixed"}},
            constraints={"current_density_A_per_mm2": {"primary_max": 3.0, "secondary_max": 3.0}},
        ),
    )

    assert result["status"] == "ok"
    assert result["result_grade"] == "hybrid_unqualified"
    assert result["engineering_approved"] is False
    assert result["geometry"]["value"] is True
    assert result["electromagnetic"]["leakage"]["status"] == "ok"
    assert result["losses"]["winding"]["status"] == "ok"
    assert result["thermal"]["hotspot_C"] is None
    assert result["candidate_hash"]
    assert result["excitation_hash"]
    assert result["evaluation_key"]


def test_same_inputs_are_reproducible_and_changed_excitation_invalidates_key() -> None:
    service = _service()
    candidate = _candidate()
    first = service.evaluate(candidate, _operating_point())
    second = service.evaluate(candidate, _operating_point())
    changed = service.evaluate(candidate, _operating_point(current_primary=1.1))
    assert first["evaluation_key"] == second["evaluation_key"]
    assert first["candidate_hash"] == second["candidate_hash"]
    assert first["excitation_hash"] != changed["excitation_hash"]
    assert first["evaluation_key"] != changed["evaluation_key"]
    assert changed["status"] == "input_invalid"
    assert any(item["code"] == "CURRENT_WAVEFORM_RMS_MISMATCH" for item in changed["diagnostics"])


def test_psp_is_evaluated_as_one_primary_with_two_physical_series_blocks() -> None:
    result = _service().evaluate(_candidate("PSP"), _operating_point())
    assert result["status"] == "ok"
    winding = result["losses"]["winding"]
    assert winding["electrical_windings"]["Primary"]["blocks"] == ["P1", "P2"]
    assert winding["electrical_windings"]["Primary"]["ohmic_loss_w"] == pytest.approx(
        winding["windings"]["P1"]["ohmic_loss_w"] + winding["windings"]["P2"]["ohmic_loss_w"]
    )
    assert result["electromagnetic"]["leakage"]["turns"] == {"P1": 10, "S": 5, "P2": 10}


def test_openmagnetics_does_not_synthesize_voltage_waveform() -> None:
    result = _service().evaluate(
        _candidate(),
        _operating_point(),
        include_openmagnetics=True,
    )
    assert result["openmagnetics"]["status"] == "unavailable"
    assert any(item["code"] == "OPENMAGNETICS_SERVICE_NOT_CONFIGURED" for item in result["openmagnetics"]["diagnostics"])


def test_provider_snapshot_keeps_explicit_voltage_and_current_waveform_fields() -> None:
    point = _operating_point()
    point = OperatingPointSnapshot(
        **{
            **point.__dict__,
            "voltage_waveforms": {
                "Primary": {"data": [800.0, -800.0, 800.0, -800.0], "time": [0.0, 2.5e-5, 5e-5, 7.5e-5]},
                "Secondary": {"data": [400.0, -400.0, 400.0, -400.0], "time": [0.0, 2.5e-5, 5e-5, 7.5e-5]},
            },
        }
    )
    provider_input, diagnostics = point.provider_operating_point(["Primary", "Secondary"])
    assert not diagnostics
    assert provider_input["excitationsPerWinding"][0]["current"]["waveform"]["data"] == [1.0] * 17
    assert provider_input["excitationsPerWinding"][0]["voltage"]["waveform"]["data"] == [800.0, -800.0, 800.0, -800.0]


def test_candidate_and_context_data_snapshots_must_match() -> None:
    result = _service().evaluate(
        _candidate(),
        _operating_point(),
        context=EvaluationContext(data_snapshot={"data_version": "different"}),
    )
    assert result["status"] == "input_invalid"
    assert result["losses"] == {}
    assert result["diagnostics"][0]["code"] == "DATA_SNAPSHOT_MISMATCH"


def test_infeasible_geometry_stops_child_calculations() -> None:
    result = _service().evaluate(_candidate(width=0.0025), _operating_point())
    assert result["status"] == "infeasible"
    assert result["losses"] == {}
    assert result["electromagnetic"] == {}
    assert any(item["code"] == "WINDOW_RADIAL_OVERFLOW" for item in result["diagnostics"])


def test_constraint_report_is_structured_and_does_not_add_thermal_claims() -> None:
    result = _service().evaluate(
        _candidate(),
        _operating_point(),
        context=EvaluationContext(
            data_snapshot={"data_version": "phase5a-fixture", "data_hashes": {"fixture": "fixed"}},
            constraints={"volume_max_m3": 1e-12, "mass_max_kg": 0.001},
        ),
    )
    assert result["constraints"]["status"] == "fail"
    assert result["constraints"]["failed_count"] == 2
    assert result["thermal"]["status"] == "not_implemented"
