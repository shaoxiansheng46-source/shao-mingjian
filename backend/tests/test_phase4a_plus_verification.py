from __future__ import annotations

from dataclasses import replace
from math import pi

import pytest

from backend.app.geometry import CoreGeometry, WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.leakage import LeakageInductanceService


MU0 = 4.0 * pi * 1e-7


def _layout(template: str = "PS", primary_turns: int = 20, primary_segments: tuple[int, int] | None = None):
    core = CoreGeometry(
        core_id="phase4a-plus-test-core",
        shape_name="TEST_SHAPE",
        material_name="TEST_MATERIAL",
        physical_dimensions_m={},
        effective_area_m2=2.8e-4,
        effective_length_m=0.129,
        effective_volume_m3=3.6e-5,
        window_width_m=0.02,
        window_height_m=0.036,
        winding_column_width_m=0.011,
        winding_column_depth_m=0.011,
        bobbin_wall_m=0.0015,
    )
    wire = WireGeometry("TEST_WIRE", 0.000524, 0.0005)
    specs = [
        WindingSpec("Primary", "primary", primary_turns, wire),
        WindingSpec("Secondary", "secondary", 5, wire),
    ]
    order = ["P", "S"] if template == "PS" else ["P1", "S", "P2"]
    return build_layout(
        core,
        specs,
        WindingLayout(template, order, main_insulation_m=0.00025),
        primary_segments=primary_segments,
    )


def _mmf_at(x: float, layout, currents: dict[str, float]) -> float:
    value = 0.0
    for block in layout.blocks:
        if x >= block.radial_end_m:
            value += block.turns * currents[block.name]
        elif x > block.radial_start_m:
            fraction = (x - block.radial_start_m) / (block.radial_end_m - block.radial_start_m)
            value += block.turns * currents[block.name] * fraction
    return value


def _independent_piecewise_energy(layout, currents: dict[str, float]) -> float:
    """Independent current-sheet integral used only as a test oracle."""
    boundaries = sorted({value for block in layout.blocks for value in (block.radial_start_m, block.radial_end_m)})
    height = layout.blocks[0].axial_end_m - layout.blocks[0].axial_start_m
    total = 0.0
    for x0, x1 in zip(boundaries, boundaries[1:]):
        if x1 <= x0:
            continue
        f0 = _mmf_at(x0, layout, currents)
        f1 = _mmf_at(x1, layout, currents)
        center = (x0 + x1) / 2.0
        lengths = []
        for block in layout.blocks:
            if block.radial_start_m <= center <= block.radial_end_m:
                lengths.append(block.mean_turn_length_m)
        if not lengths:
            lengths = [block.mean_turn_length_m for block in layout.blocks]
        length = sum(lengths) / len(lengths)
        integral_f2 = (x1 - x0) * (f0 * f0 + f0 * f1 + f1 * f1) / 3.0
        total += MU0 * length * integral_f2 / (2.0 * height)
    return total


def test_native_sectional_matches_independent_energy_oracle_for_ps_and_psp() -> None:
    service = LeakageInductanceService()
    for template, currents in (("PS", {"Primary": 1.0, "Secondary": -4.0}), ("PSP", {"Primary": 1.0, "Secondary": -4.0})):
        layout = _layout(template)
        result = service.calculate(layout, currents_rms=currents)
        expected_energy = _independent_piecewise_energy(layout, {block.name: (1.0 if block.role == "primary" else -4.0) for block in layout.blocks})
        assert result["status"] == "ok"
        assert result["energy_j"] == pytest.approx(expected_energy, rel=1e-12)
        assert result["value"] == pytest.approx(2.0 * expected_energy, rel=1e-12)


def test_profile_reconstructs_total_energy_and_reports_nonnegative_intervals() -> None:
    layout = _layout("PSP", primary_turns=21, primary_segments=(10, 11))
    profile = LeakageInductanceService().field_energy_profile(layout, currents_rms={"Primary": 1.0, "Secondary": -4.2})
    assert profile["status"] == "ok"
    assert sum(item["energy_j"] for item in profile["intervals"]) == pytest.approx(profile["energy_j"], rel=1e-12)
    assert all(item["volume_m3"] > 0 and item["energy_j"] >= 0 for item in profile["intervals"])
    assert {item["zone"] for item in profile["zones"]} >= {"P1.layer_0", "S.layer_0", "P2.layer_0"}


def test_current_amplitude_scaling_does_not_change_linear_leakage() -> None:
    layout = _layout("PSP")
    service = LeakageInductanceService()
    nominal = service.calculate(layout, currents_rms={"Primary": 1.0, "Secondary": -4.0})
    scaled = service.calculate(layout, currents_rms={"Primary": 3.0, "Secondary": -12.0})
    assert scaled["value"] == pytest.approx(nominal["value"], rel=1e-12)
    assert scaled["energy_j"] == pytest.approx(nominal["energy_j"] * 9.0, rel=1e-12)


def test_profile_rejects_out_of_scope_height_change() -> None:
    layout = _layout("PS")
    changed = replace(layout.blocks[1], axial_end_m=layout.blocks[1].axial_end_m - 0.001)
    result = LeakageInductanceService().field_energy_profile(replace(layout, blocks=[layout.blocks[0], changed]), currents_rms={"Primary": 1.0, "Secondary": -4.0})
    assert result["status"] == "OUT_OF_MODEL_SCOPE"
    assert any(item["code"] == "OUT_OF_MODEL_SCOPE" for item in result["diagnostics"])
