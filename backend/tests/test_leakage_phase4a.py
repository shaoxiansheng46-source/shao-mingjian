from __future__ import annotations

from dataclasses import replace
from math import pi

import pytest

from backend.app.geometry import CoreGeometry, WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.leakage import LeakageInductanceService


MU0 = 4 * pi * 1e-7


def _core(width: float = 0.02, height: float = 0.036) -> CoreGeometry:
    return CoreGeometry(
        core_id="phase4a-test-core",
        shape_name="TEST_SHAPE",
        material_name="TEST_MATERIAL",
        physical_dimensions_m={},
        effective_area_m2=2.8e-4,
        effective_length_m=0.129,
        effective_volume_m3=3.6e-5,
        window_width_m=width,
        window_height_m=height,
        winding_column_width_m=0.011,
        winding_column_depth_m=0.011,
        bobbin_wall_m=0.0015,
        gap_m=0.0,
    )


def _wire(outer: float = 0.000524) -> WireGeometry:
    return WireGeometry("TEST_WIRE", outer, outer * 0.95)


def _layout(template: str = "PS", *, primary_turns: int = 20, main_insulation_m: float = 0.00025, primary_segments: tuple[int, int] | None = None, wire_outer_m: float = 0.000524):
    wire = _wire(wire_outer_m)
    specs = [WindingSpec("Primary", "primary", primary_turns, wire), WindingSpec("Secondary", "secondary", 5, wire)]
    return build_layout(
        _core(),
        specs,
        WindingLayout(template, ["P", "S"] if template == "PS" else ["P1", "S", "P2"], main_insulation_m=main_insulation_m),
        primary_segments=primary_segments,
    )


def test_native_basic_matches_independent_uniform_sheet_formula() -> None:
    layout = _layout("PS")
    service = LeakageInductanceService()
    result = service.calculate(layout, model="native_basic", currents_rms={"Primary": 1.0, "Secondary": -4.0})
    primary, secondary = layout.blocks
    h = primary.axial_end_m - primary.axial_start_m
    gap = secondary.radial_start_m - primary.radial_end_m
    mlt = (primary.mean_turn_length_m + secondary.mean_turn_length_m) / 2
    expected = MU0 * primary.turns**2 * mlt / h * ((primary.radial_end_m - primary.radial_start_m) / 3 + gap + (secondary.radial_end_m - secondary.radial_start_m) / 3)
    assert result["status"] == "ok"
    assert result["value"] == pytest.approx(expected, rel=1e-12)
    assert result["energy_j"] == pytest.approx(0.5 * expected, rel=1e-12)


def test_sectional_model_supports_psp_and_preserves_series_current() -> None:
    layout = _layout("PSP")
    result = LeakageInductanceService().calculate(layout, model="native_sectional", currents_rms={"Primary": 1.0, "Secondary": -4.0})
    assert result["status"] == "ok"
    assert result["value"] >= 0
    assert result["turns"] == {"P1": 10, "S": 5, "P2": 10}
    assert {item["zone"] for item in result["zones"]} >= {"P1.layer_0", "S.layer_0", "P2.layer_0"}


def test_spacing_and_psp_split_reach_the_physical_model() -> None:
    close = _layout("PS", main_insulation_m=0.00025)
    far = _layout("PS", main_insulation_m=0.0005)
    thin = _layout("PS", wire_outer_m=0.00045)
    thick = _layout("PS", wire_outer_m=0.00065)
    split_a = _layout("PSP", primary_segments=(10, 10))
    split_b = _layout("PSP", primary_segments=(8, 12))
    service = LeakageInductanceService()
    close_l = service.calculate(close, currents_rms={"Primary": 1.0, "Secondary": -4.0})["value"]
    far_l = service.calculate(far, currents_rms={"Primary": 1.0, "Secondary": -4.0})["value"]
    thin_l = service.calculate(thin, currents_rms={"Primary": 1.0, "Secondary": -4.0})["value"]
    thick_l = service.calculate(thick, currents_rms={"Primary": 1.0, "Secondary": -4.0})["value"]
    split_a_l = service.calculate(split_a, currents_rms={"Primary": 1.0, "Secondary": -4.0})["value"]
    split_b_l = service.calculate(split_b, currents_rms={"Primary": 1.0, "Secondary": -4.0})["value"]
    assert far_l > close_l
    assert thick_l > thin_l
    assert split_a_l != pytest.approx(split_b_l, rel=1e-12)


def test_secondary_reference_is_converted_from_the_same_energy() -> None:
    layout = _layout("PS")
    service = LeakageInductanceService()
    primary = service.calculate(layout, reference_port="primary", currents_rms={"Primary": 1.0, "Secondary": -4.0})
    secondary = service.calculate(layout, reference_port="secondary", currents_rms={"Primary": 1.0, "Secondary": -4.0})
    assert secondary["status"] == "ok"
    assert secondary["value"] == pytest.approx(primary["value"] / 16.0, rel=1e-12)


def test_unbalanced_short_circuit_current_is_rejected() -> None:
    result = LeakageInductanceService().calculate(_layout("PS"), currents_rms={"Primary": 1.0, "Secondary": -3.0})
    assert result["status"] == "input_invalid"
    assert result["diagnostics"][0]["code"] == "MMF_IMBALANCE"


def test_zero_geometry_and_different_heights_are_not_silently_calculated() -> None:
    layout = _layout("PS")
    zero_block = replace(layout.blocks[0], radial_end_m=layout.blocks[0].radial_start_m)
    zero = replace(layout, blocks=[zero_block, layout.blocks[1]])
    zero_result = LeakageInductanceService().calculate(zero, currents_rms={"Primary": 1.0, "Secondary": -4.0})
    assert zero_result["status"] == "INVALID_GEOMETRY"

    different_height = replace(layout.blocks[1], axial_end_m=layout.blocks[1].axial_end_m - 0.001)
    height_result = LeakageInductanceService().calculate(replace(layout, blocks=[layout.blocks[0], different_height]), currents_rms={"Primary": 1.0, "Secondary": -4.0})
    assert height_result["status"] == "OUT_OF_MODEL_SCOPE"
