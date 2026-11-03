"""Deterministic PS/PSP parameterized winding layout generator.

The generator owns only geometry and manufacturing checks.  It does not call
the existing synthetic evaluator or the optimizer.  All coordinates and
lengths are SI units; display conversion belongs outside this module.
"""

from __future__ import annotations

from dataclasses import replace
from math import floor
from typing import Iterable

from .models import (
    CoreGeometry,
    GeometryViolation,
    InsulationGeometry,
    LayerGeometry,
    LayoutGeometry,
    TurnGeometry,
    WireGeometry,
    WindingLayout,
    WindingSegmentGeometry,
    WindingSpec,
)


def _v(code: str, message: str, field: str | None = None, severity: str = "error") -> GeometryViolation:
    return GeometryViolation(code=code, message=message, field=field, severity=severity)


def _default_template(template: str) -> WindingLayout:
    normalized = template.upper().replace("_", "-")
    if normalized == "PS":
        return WindingLayout(template_id="PS", block_order=["P", "S"])
    if normalized == "PSP":
        return WindingLayout(template_id="PSP", block_order=["P1", "S", "P2"])
    return WindingLayout(template_id=normalized, block_order=[], supported=False)


def _normalize_specs(specs: Iterable[WindingSpec], template: WindingLayout, primary_segments: tuple[int, int] | None, violations: list[GeometryViolation]) -> list[WindingSpec]:
    values = list(specs)
    if not values:
        violations.append(_v("MISSING_WINDINGS", "至少需要一个原边和一个副边绕组。", "windings"))
        return []
    primary = next((item for item in values if item.role.lower() in {"primary", "p", "原边"}), None)
    secondary = next((item for item in values if item.role.lower() in {"secondary", "s", "副边"}), None)
    if primary is None or secondary is None:
        violations.append(_v("MISSING_PRIMARY_SECONDARY", "结构生成需要 primary 和 secondary 两类绕组。", "windings"))
        return []
    if primary.turns <= 0 or secondary.turns <= 0:
        violations.append(_v("INVALID_TURNS", "绕组匝数必须为正整数。", "windings.turns"))
        return []
    if primary.parallels <= 0 or secondary.parallels <= 0:
        violations.append(_v("INVALID_PARALLELS", "并联股数必须为正整数。", "windings.parallels"))
        return []
    if template.template_id == "PS":
        if primary_segments is not None:
            violations.append(_v("UNSUPPORTED_SEGMENT_SPLIT", "PS 模板不接受 P1/P2 分段；请使用 PSP。", "primary_segments"))
        return [replace(primary, name=primary.name or "P"), secondary]
    if template.template_id != "PSP":
        violations.append(_v("UNSUPPORTED_GEOMETRY", f"模板 {template.template_id} 没有 Phase 3 参数化规则。", "template"))
        return []
    if primary_segments is None:
        p1 = primary.turns // 2
        p2 = primary.turns - p1
    else:
        p1, p2 = primary_segments
    if p1 <= 0 or p2 <= 0 or p1 + p2 != primary.turns:
        violations.append(_v("PRIMARY_SPLIT_MISMATCH", "P1+P2 必须等于原边总匝数，且两个分段都必须有匝数。", "primary_segments"))
        return []
    return [
        replace(primary, name="P1", turns=p1),
        replace(secondary, name="S"),
        replace(primary, name="P2", turns=p2),
    ]


def _wire_pitch(wire: WireGeometry, template: WindingLayout) -> float:
    return wire.outer_diameter_m + wire.diameter_tolerance_m + template.process_clearance_m


def _turn_length(core: CoreGeometry, radial_center_m: float) -> float:
    # Rectangular two-window approximation corresponding to the existing MLT
    # convention, but expressed in SI and retained as an explicit model name.
    return 2.0 * (core.winding_column_width_m + core.winding_column_depth_m) + 8.0 * radial_center_m


def _segment(
    spec: WindingSpec,
    radial_start_m: float,
    core: CoreGeometry,
    template: WindingLayout,
    violations: list[GeometryViolation],
    segment_index: int,
) -> WindingSegmentGeometry:
    pitch = _wire_pitch(spec.wire, template)
    usable_height = core.window_height_m - 2.0 * template.end_margin_m
    turns_per_layer = floor(usable_height / pitch) if pitch > 0 else 0
    if turns_per_layer < 1:
        violations.append(_v("GEOMETRY_NO_TURN_PER_LAYER", f"{spec.name} 的线径和端部余量无法在窗口高度放置一匝。", f"blocks[{segment_index}]"))
        turns_per_layer = 1
    layer_count = (spec.turns + turns_per_layer - 1) // turns_per_layer
    radial_layer_pitch = spec.parallels * pitch
    radial_end_m = radial_start_m + layer_count * radial_layer_pitch + max(layer_count - 1, 0) * template.layer_insulation_m
    axial_start_m = -usable_height / 2.0
    axial_end_m = usable_height / 2.0
    layers: list[LayerGeometry] = []
    turns: list[TurnGeometry] = []
    remaining = spec.turns
    turn_global = 0
    for layer_index in range(layer_count):
        count = min(turns_per_layer, remaining)
        layer_start = radial_start_m + layer_index * (radial_layer_pitch + template.layer_insulation_m)
        layer_end = layer_start + radial_layer_pitch
        layer_indices: list[int] = []
        for parallel_index in range(spec.parallels):
            for turn_index in range(count):
                axial_center = axial_start_m + (turn_index + 0.5) * pitch
                radial_center = layer_start + (parallel_index + 0.5) * pitch
                length = _turn_length(core, radial_center)
                turns.append(TurnGeometry(
                    winding=spec.name,
                    segment=spec.name,
                    layer_index=layer_index,
                    turn_index=turn_index,
                    parallel_index=parallel_index,
                    turns_index=turn_global,
                    coordinates_m=(radial_center, axial_center),
                    dimensions_m=(pitch, pitch),
                    length_m=length,
                ))
                layer_indices.append(turn_global)
                turn_global += 1
        layers.append(LayerGeometry(
            winding=spec.name,
            segment=spec.name,
            layer_index=layer_index,
            radial_start_m=layer_start,
            radial_end_m=layer_end,
            axial_start_m=axial_start_m,
            axial_end_m=axial_end_m,
            turns_per_parallel=count,
            parallel_count=spec.parallels,
            turn_indices=layer_indices,
        ))
        remaining -= count
    used_turns = len(turns) // spec.parallels
    if used_turns != spec.turns:
        violations.append(_v("TURN_COUNT_MISMATCH", f"{spec.name} 生成匝数 {used_turns} 不等于要求 {spec.turns}。", f"blocks[{segment_index}].turns"))
    mean_turn_length = sum(item.length_m for item in turns) / len(turns) if turns else 0.0
    branch_length = mean_turn_length + (spec.lead_allowance_m or template.lead_allowance_m)
    resistance = None
    if spec.wire.resistance_ohm_per_m is not None:
        resistance = spec.wire.resistance_ohm_per_m * branch_length / spec.parallels
    return WindingSegmentGeometry(
        name=spec.name,
        winding=spec.name,
        role=spec.role,
        turns=spec.turns,
        parallels=spec.parallels,
        wire=spec.wire,
        radial_start_m=radial_start_m,
        radial_end_m=radial_end_m,
        axial_start_m=axial_start_m,
        axial_end_m=axial_end_m,
        layer_count=layer_count,
        turns_per_layer=turns_per_layer,
        mean_turn_length_m=mean_turn_length,
        branch_length_m=branch_length,
        resistance_ohm=resistance,
        copper_area_m2=spec.wire.copper_area_m2,
        layers=layers,
        turns_geometry=turns,
    )


def build_layout(
    core: CoreGeometry,
    windings: Iterable[WindingSpec],
    template: str | WindingLayout = "PS",
    *,
    primary_segments: tuple[int, int] | None = None,
    provenance: dict | None = None,
) -> LayoutGeometry:
    """Generate one explicit PS or PSP layout and all constraint diagnostics."""

    layout_template = _default_template(template) if isinstance(template, str) else template
    violations: list[GeometryViolation] = []
    if not layout_template.supported or layout_template.template_id not in {"PS", "PSP"}:
        violations.append(_v("UNSUPPORTED_GEOMETRY", f"模板 {layout_template.template_id} 尚未实现。", "template"))
        return LayoutGeometry(layout_template, core, [], [], {}, False, violations, model_status="unsupported", provenance=provenance or {})
    if layout_template.radial_or_axial.lower() != "radial":
        violations.append(_v("UNSUPPORTED_GEOMETRY", "当前实现只支持明确的径向分块、轴向匝和径向层排布。", "radial_or_axial"))
        return LayoutGeometry(layout_template, core, [], [], {}, False, violations, model_status="unsupported", provenance=provenance or {})
    specs = _normalize_specs(windings, layout_template, primary_segments, violations)
    if not specs:
        return LayoutGeometry(layout_template, core, [], [], {}, False, violations, provenance=provenance or {})
    actual_names = [item.name for item in specs]
    semantic_order = [item.role.lower() for item in specs]
    expected_semantic = ["primary", "secondary"] if layout_template.template_id == "PS" else ["primary", "secondary", "primary"]
    if layout_template.template_id == "PSP":
        expected_names = ["P1", "S", "P2"]
        if actual_names != expected_names:
            violations.append(_v("BLOCK_ORDER_MISMATCH", f"实际块顺序 {actual_names} 与 PSP 模板 {expected_names} 不一致。", "template.block_order"))
    elif semantic_order != expected_semantic:
        violations.append(_v("BLOCK_ORDER_MISMATCH", f"实际块角色 {semantic_order} 不是径向 P-S 顺序。", "template.block_order"))

    radial_start = core.bobbin_wall_m + layout_template.winding_to_core_clearance_m
    blocks: list[WindingSegmentGeometry] = []
    interfaces: list[InsulationGeometry] = []
    for index, spec in enumerate(specs):
        block = _segment(spec, radial_start, core, layout_template, violations, index)
        blocks.append(block)
        if index < len(specs) - 1:
            next_start = block.radial_end_m + layout_template.main_insulation_m
            interfaces.append(InsulationGeometry(
                name=f"Insulation between {block.name} and {specs[index + 1].name}",
                between=(block.name, specs[index + 1].name),
                thickness_m=layout_template.main_insulation_m,
                radial_start_m=block.radial_end_m,
                radial_end_m=next_start,
                rule_id="parameterized_main_barrier",
            ))
            radial_start = next_start
    available_end = core.window_width_m - core.bobbin_wall_m - layout_template.winding_to_core_clearance_m
    if blocks and blocks[-1].radial_end_m > available_end + 1e-15:
        violations.append(_v("WINDOW_RADIAL_OVERFLOW", f"绕组外缘 {blocks[-1].radial_end_m:.6g} m 超出窗口可用边界 {available_end:.6g} m。", "window_width_m"))
    if core.window_height_m - 2.0 * layout_template.end_margin_m <= 0:
        violations.append(_v("WINDOW_AXIAL_OVERFLOW", "端部余量大于等于窗口高度的一半。", "window_height_m"))
    if layout_template.main_insulation_m <= 0:
        violations.append(_v("INSULATION_NON_POSITIVE", "主绝缘厚度必须大于零，且每个界面均使用完整厚度。", "main_insulation_m"))
    if blocks and blocks[0].radial_start_m < core.bobbin_wall_m + layout_template.winding_to_core_clearance_m - 1e-15:
        violations.append(_v("CORE_CLEARANCE_FAILED", "绕组到骨架/磁芯的径向距离不足。", "winding_to_core_clearance_m"))
    for left, right in zip(blocks, blocks[1:]):
        if left.radial_end_m + layout_template.main_insulation_m > right.radial_start_m + 1e-15:
            violations.append(_v("RADIAL_COLLISION", f"绕组块 {left.name} 与 {right.name} 的几何范围重叠。", "blocks"))
    if layout_template.main_insulation_m < 0:
        violations.append(_v("INSULATION_RULE_FAILED", "主绝缘厚度为负，不满足设计规则。", "main_insulation_m"))
    errors = [item for item in violations if item.severity == "error"]
    volume = None
    if blocks:
        radial_total = max(block.radial_end_m for block in blocks) - min(block.radial_start_m for block in blocks)
        volume = radial_total * core.window_height_m * max(core.winding_column_depth_m, 0.0)
    mass = None
    if core.mass_kg is not None:
        mass = core.mass_kg
    warnings = ["气隙边缘磁通附加损耗未在本阶段计算。", "OpenMagnetics 联合结果属于研发原型，未声明工程认证精度。"]
    return LayoutGeometry(
        template=layout_template,
        core=core,
        blocks=blocks,
        interfaces=interfaces,
        connection={
            "type": "series",
            "direction": "same",
            "primary_segments": [item.name for item in blocks if item.role.lower() in {"primary", "p", "原边"}],
            "constraint": "P1+P2=Np" if layout_template.template_id == "PSP" else None,
        },
        feasible=not errors,
        violations=violations,
        warnings=warnings,
        model_status="parameterized_geometry",
        volume_m3=volume,
        mass_kg=mass,
        provenance=provenance or {
            "data_status": core.data_status,
            "synthetic": core.synthetic,
            "demo_only": core.demo_only,
            "engineering_approved": core.engineering_approved,
        },
    )
