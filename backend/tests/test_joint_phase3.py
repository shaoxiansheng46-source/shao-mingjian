from __future__ import annotations

from backend.app.geometry import CoreGeometry, JointCalculationService, WireGeometry, WindingSpec, build_layout


class _FakeProvider:
    def status(self):
        return {"available": True, "provenance": {"third_party_version": "test-double"}}

    def calculate_core_data(self, core):
        return {"status": "ok", "value": {"effective_area_m2": 1.0}}

    def calculate_inductance(self, core, coil, operating_point, models):
        return {"status": "ok", "value": 1e-3, "unit": "H"}

    def calculate_core_losses(self, core, coil, inputs, models):
        return {"status": "ok", "value": 1.0, "unit": "W"}

    def calculate_winding_losses(self, magnetic, operating_point, temperature):
        return {"status": "ok", "value": 2.0, "unit": "W"}

    def calculate_ohmic_losses(self, coil, operating_point, temperature):
        return {"status": "ok", "value": 1.5, "unit": "W"}

    def wind(self, coil):
        return {"status": "ok", "value": {"section_count": 3}}


def _layout():
    core = CoreGeometry(
        core_id="c", shape_name="shape", material_name="material", physical_dimensions_m={},
        effective_area_m2=1e-4, effective_length_m=0.1, effective_volume_m3=1e-5,
        window_width_m=0.02, window_height_m=0.03, winding_column_width_m=0.01,
        winding_column_depth_m=0.01, bobbin_wall_m=0.001, gap_m=0.0001,
    )
    wire = WireGeometry("wire", 0.0005, 0.00045)
    return build_layout(core, [WindingSpec("P", "primary", 10, wire), WindingSpec("S", "secondary", 5, wire)], "PS")


def test_joint_service_keeps_geometry_only_when_waveforms_are_missing():
    result = JointCalculationService(_FakeProvider()).calculate(_layout())
    assert result["status"] == "geometry_only"
    assert result["calculations"]["openmagnetics"]["core_losses"]["status"] == "skipped"
    assert result["calculations"]["openmagnetics"]["core_losses"]["value"] is None


def test_joint_service_runs_provider_boundary_with_complete_waveforms():
    op = {
        "excitationsPerWinding": [
            {"name": "P", "voltage": {"waveform": {"data": [1, -1], "time": [0.0, 0.00001]}}, "current": {"waveform": {"data": [1, 1], "time": [0.0, 0.00001]}}},
            {"name": "S", "voltage": {"waveform": {"data": [1, -1], "time": [0.0, 0.00001]}}, "current": {"waveform": {"data": [1, 1], "time": [0.0, 0.00001]}}},
        ]
    }
    result = JointCalculationService(_FakeProvider()).calculate(_layout(), operating_point=op, inputs={})
    assert result["status"] == "ok"
    assert result["mas_validation"]["valid"]
    assert result["calculations"]["openmagnetics"]["winding_losses"]["value"] == 2.0


def test_joint_service_rejects_waveforms_bound_to_physical_psp_segments():
    op = {
        "excitationsPerWinding": [
            {"name": "P1", "voltage": {"waveform": {"data": [1, -1], "time": [0.0, 0.00001]}}, "current": {"waveform": {"data": [1, 1], "time": [0.0, 0.00001]}}},
            {"name": "S", "voltage": {"waveform": {"data": [1, -1], "time": [0.0, 0.00001]}}, "current": {"waveform": {"data": [1, 1], "time": [0.0, 0.00001]}}},
            {"name": "P2", "voltage": {"waveform": {"data": [1, -1], "time": [0.0, 0.00001]}}, "current": {"waveform": {"data": [1, 1], "time": [0.0, 0.00001]}}},
        ]
    }
    result = JointCalculationService(_FakeProvider()).calculate(_layout(), operating_point=op, inputs={})
    assert result["status"] == "input_invalid"
    assert result["errors"][0]["code"] == "WINDING_EXCITATION_BINDING_MISMATCH"
