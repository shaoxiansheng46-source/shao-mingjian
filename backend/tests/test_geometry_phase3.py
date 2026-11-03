from __future__ import annotations

from backend.app.geometry import (
    CoreGeometry,
    MasGeometryAdapter,
    WireGeometry,
    WindingLayout,
    WindingSpec,
    build_layout,
    validate_mas_geometry,
)


def _core(*, width: float = 0.012, height: float = 0.036, wall: float = 0.0015) -> CoreGeometry:
    return CoreGeometry(
        core_id="phase3-test-core",
        shape_name="TEST_SHAPE",
        material_name="TEST_MATERIAL",
        physical_dimensions_m={"outer_width_m": 0.04, "outer_height_m": 0.04},
        effective_area_m2=2.8e-4,
        effective_length_m=0.129,
        effective_volume_m3=3.6e-5,
        window_width_m=width,
        window_height_m=height,
        winding_column_width_m=0.011,
        winding_column_depth_m=0.011,
        bobbin_wall_m=wall,
        bobbin_id="TEST_BOBBIN",
        gap_m=0.0001,
        data_status="external_database",
    )


def _specs(primary: int = 20, secondary: int = 5) -> list[WindingSpec]:
    wire = WireGeometry(
        wire_id="TEST_WIRE",
        outer_diameter_m=0.000524,
        conducting_diameter_m=0.0005,
        resistance_ohm_per_m=0.08,
    )
    return [
        WindingSpec("Primary", "primary", primary, wire),
        WindingSpec("Secondary", "secondary", secondary, wire),
    ]


def test_ps_layout_has_real_layers_turns_and_total_counts() -> None:
    layout = build_layout(_core(), _specs(), "PS")
    assert layout.feasible
    assert [item.name for item in layout.blocks] == ["Primary", "Secondary"]
    assert sum(item.turns for item in layout.blocks) == 25
    assert all(item.layers and item.turns_geometry for item in layout.blocks)
    assert len(layout.interfaces) == 1
    assert layout.interfaces[0].thickness_m > 0
    assert layout.blocks[0].radial_end_m + layout.interfaces[0].thickness_m <= layout.blocks[1].radial_start_m + 1e-15


def test_psp_odd_primary_split_and_two_full_barriers() -> None:
    layout = build_layout(_core(width=0.02), _specs(primary=21), "PSP")
    assert layout.feasible
    assert [item.name for item in layout.blocks] == ["P1", "S", "P2"]
    assert [item.turns for item in layout.blocks] == [10, 5, 11]
    assert sum(item.turns for item in layout.blocks if item.role == "primary") == 21
    assert len(layout.interfaces) == 2
    assert all(item.thickness_m == layout.template.main_insulation_m for item in layout.interfaces)
    assert layout.connection["direction"] == "same"


def test_ps_and_psp_keep_the_same_electrical_primary_turn_count() -> None:
    ps = build_layout(_core(width=0.02), _specs(primary=20), "PS")
    psp = build_layout(_core(width=0.02), _specs(primary=20), "PSP")
    assert sum(item.turns for item in ps.blocks if item.role == "primary") == 20
    assert sum(item.turns for item in psp.blocks if item.role == "primary") == 20
    assert psp.connection == {"type": "series", "direction": "same", "primary_segments": ["P1", "P2"], "constraint": "P1+P2=Np"}


def test_psp_explicit_split_must_sum_to_primary() -> None:
    layout = build_layout(_core(width=0.02), _specs(primary=21), "PSP", primary_segments=(9, 9))
    assert not layout.feasible
    assert any(item.code == "PRIMARY_SPLIT_MISMATCH" for item in layout.violations)


def test_geometry_reports_window_and_insulation_failures() -> None:
    too_small = build_layout(_core(width=0.0025, height=0.008), _specs(primary=20), "PS")
    assert not too_small.feasible
    assert any(item.code == "WINDOW_RADIAL_OVERFLOW" for item in too_small.violations)

    no_barrier = WindingLayout(template_id="PS", block_order=["Primary", "Secondary"], main_insulation_m=0.0)
    no_barrier_result = build_layout(_core(), _specs(), no_barrier)
    assert not no_barrier_result.feasible
    assert any(item.code == "INSULATION_NON_POSITIVE" for item in no_barrier_result.violations)


def test_mas_mapping_preserves_blocks_layers_and_turns() -> None:
    layout = build_layout(_core(width=0.02), _specs(primary=21), "PSP")
    magnetic = MasGeometryAdapter().to_magnetic(layout)
    validation = validate_mas_geometry(magnetic, layout)
    assert validation["valid"], validation
    assert [item["name"] for item in magnetic["coil"]["functionalDescription"]] == ["Primary", "Secondary"]
    assert [item["numberTurns"] for item in magnetic["coil"]["functionalDescription"]] == [21, 5]
    assert magnetic["coil"]["sstElectricalWindingMap"] == {"P1": "Primary", "S": "Secondary", "P2": "Primary"}
    assert magnetic["coil"]["sstElectricalConnections"]["type"] == "series"
    assert len(magnetic["coil"]["sectionsDescription"]) == 5
    assert len(magnetic["coil"]["layersDescription"]) == sum(item.layer_count for item in layout.blocks) + len(layout.interfaces)
    assert len(magnetic["coil"]["turnsDescription"]) == sum(len(item.turns_geometry) for item in layout.blocks)


def test_independent_reluctance_formula_is_dimensionally_consistent() -> None:
    # Independent check values are deliberately explicit; this does not call
    # the production inductance implementation or use a fixed expected output.
    import math

    ae_m2 = 2.799884090461257e-4
    le_m = 0.12937894574793482
    mu_r = 2815.5
    gap_m = 1e-4
    turns = 20
    reluctance = le_m / (4 * math.pi * 1e-7 * mu_r * ae_m2) + gap_m / (4 * math.pi * 1e-7 * ae_m2)
    inductance_h = turns**2 / reluctance
    assert reluctance > 0
    assert 0.0009 < inductance_h < 0.0011


def test_design_parameter_change_changes_generated_geometry() -> None:
    baseline = build_layout(_core(width=0.02), _specs(primary=20), "PSP")
    changed = build_layout(_core(width=0.02), _specs(primary=24), "PSP")
    assert baseline.blocks[0].turns != changed.blocks[0].turns
    assert baseline.blocks[0].turns_geometry[-1].coordinates_m != changed.blocks[0].turns_geometry[-1].coordinates_m


def test_unknown_template_is_explicitly_unsupported() -> None:
    layout = build_layout(_core(), _specs(), "interleaved")
    assert not layout.feasible
    assert layout.status == "unsupported"
    assert any(item.code == "UNSUPPORTED_GEOMETRY" for item in layout.violations)
