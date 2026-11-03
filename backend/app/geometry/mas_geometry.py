"""Map Phase 3 explicit geometry to the MAS-shaped coil description.

The adapter emits the field families observed in the installed
PyOpenMagnetics 1.7.x ``wind`` output.  It validates the application geometry
before a provider call and never changes PSP into PS when a field is missing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import LayoutGeometry, WindingSegmentGeometry


class UnsupportedGeometryError(ValueError):
    code = "UNSUPPORTED_GEOMETRY"


def _point(values: tuple[float, float]) -> list[float]:
    return [float(values[0]), float(values[1])]


def _dimensions(values: tuple[float, float]) -> list[float]:
    return [float(values[0]), float(values[1])]


def _partial(name: str) -> list[dict[str, Any]]:
    return [{"connections": None, "parallelsProportion": [1.0], "winding": name}]


def _electrical_winding_view(layout: LayoutGeometry) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return the electrical MAS view without losing physical block names.

    MAS ``functionalDescription`` describes electrical windings.  In PSP the
    two primary blocks are therefore one 20-turn ``Primary`` winding; the
    physical P1/P2 names remain in section/layer/turn metadata and in the
    application connection record.  Sending P1 and P2 as separate electrical
    windings makes MKF use the first 10-turn block for magnetizing inductance.
    """

    if layout.template.template_id != "PSP":
        mapping = {item.name: item.name for item in layout.blocks}
        windings = [
            {
                "connections": None,
                "name": item.name,
                "numberTurns": item.turns,
                "numberParallels": item.parallels,
                "wire": item.wire.wire_id,
                "isolationSide": "primary" if item.role.lower() in {"primary", "p", "原边"} else "secondary",
                "windingWindow": None,
                "woundWith": None,
            }
            for item in layout.blocks
        ]
        return mapping, windings
    primary_blocks = [item for item in layout.blocks if item.role.lower() in {"primary", "p", "原边"}]
    secondary = next(item for item in layout.blocks if item.role.lower() in {"secondary", "s", "副边"})
    mapping = {item.name: "Primary" for item in primary_blocks}
    mapping[secondary.name] = "Secondary"
    return mapping, [
        {
            "connections": None,
            "name": "Primary",
            "numberTurns": sum(item.turns for item in primary_blocks),
            "numberParallels": primary_blocks[0].parallels,
            "wire": primary_blocks[0].wire.wire_id,
            "isolationSide": "primary",
            "windingWindow": None,
            "woundWith": None,
        },
        {
            "connections": None,
            "name": "Secondary",
            "numberTurns": secondary.turns,
            "numberParallels": secondary.parallels,
            "wire": secondary.wire.wire_id,
            "isolationSide": "secondary",
            "windingWindow": None,
            "woundWith": None,
        },
    ]


class MasGeometryAdapter:
    """Convert a :class:`LayoutGeometry` into an application-owned MAS dict."""

    adapter_version = "sst-mas-geometry-adapter-0.1.0"

    def to_magnetic(self, layout: LayoutGeometry) -> dict[str, Any]:
        unsupported = [item for item in layout.violations if item.code == "UNSUPPORTED_GEOMETRY"]
        if unsupported:
            raise UnsupportedGeometryError(unsupported[0].message)
        if not layout.blocks:
            raise UnsupportedGeometryError("没有可以映射到 MAS 的绕组块。")
        core_fd = {
            "type": "two-piece set",
            "shape": layout.core.shape_name,
            "material": layout.core.material_name,
            "gapping": ([{"type": "subtractive", "length": layout.core.gap_m}] if layout.core.gap_m > 0 else []),
            "numberStacks": int(layout.core.stack_count),
        }
        sections: list[dict[str, Any]] = []
        layers: list[dict[str, Any]] = []
        turns: list[dict[str, Any]] = []
        electrical_map, windings = _electrical_winding_view(layout)
        for order, block in enumerate(layout.blocks):
            section_name = f"{block.name} section {order}"
            electrical_name = electrical_map[block.name]
            section_center = ((block.radial_start_m + block.radial_end_m) / 2.0, 0.0)
            section_dimensions = (block.radial_end_m - block.radial_start_m, block.axial_end_m - block.axial_start_m)
            sections.append({
                "coordinateSystem": "cartesian",
                "coordinates": _point(section_center),
                "dimensions": _dimensions(section_dimensions),
                "fillingFactor": 1.0,
                "group": "Default group",
                "layersAlignment": None,
                "layersOrientation": "overlapping",
                "margin": [0.0, 0.0],
                "name": section_name,
                "numberLayers": None,
                "partialWindings": _partial(electrical_name),
                "type": "conduction",
                "windingOrder": None,
                "windingStyle": "windByConsecutiveTurns",
                "windingWindow": None,
            })
            for layer in block.layers:
                layer_name = f"{section_name} layer {layer.layer_index}"
                layers.append({
                    "additionalCoordinates": None,
                    "coordinateSystem": "cartesian",
                    "coordinates": [(layer.radial_start_m + layer.radial_end_m) / 2.0, 0.0],
                    "dimensions": [layer.radial_end_m - layer.radial_start_m, layer.axial_end_m - layer.axial_start_m],
                    "fillingFactor": 1.0,
                    "insulationMaterial": None,
                    "name": layer_name,
                    "orientation": "overlapping",
                    "partialWindings": _partial(electrical_name),
                    "section": section_name,
                    "turnsAlignment": "centered",
                    "type": "conduction",
                    "windingStyle": "windByConsecutiveTurns",
                })
            for turn in block.turns_geometry:
                turns.append({
                    "additionalCoordinates": None,
                    "angle": None,
                    "coordinateSystem": "cartesian",
                    "coordinates": _point(turn.coordinates_m),
                    "crossSectionalShape": "round",
                    "dimensions": _dimensions(turn.dimensions_m),
                    "layer": f"{section_name} layer {turn.layer_index}",
                    "length": turn.length_m,
                    "name": f"{block.name} parallel {turn.parallel_index} turn {turn.turns_index}",
                    "orientation": "clockwise",
                    "parallel": turn.parallel_index,
                    "rotation": 0.0,
                    "section": section_name,
                    "winding": electrical_name,
                })
        for index, insulation in enumerate(layout.interfaces):
            sections.append({
                "coordinateSystem": "cartesian",
                "coordinates": [(insulation.radial_start_m + insulation.radial_end_m) / 2.0, 0.0],
                "dimensions": [insulation.thickness_m, layout.core.window_height_m],
                "fillingFactor": 1.0,
                "group": "Default group",
                "layersAlignment": None,
                "layersOrientation": "overlapping",
                "margin": None,
                "name": f"{insulation.name} section {index + len(layout.blocks)}",
                "numberLayers": None,
                "partialWindings": [],
                "type": "insulation",
                "windingOrder": None,
                "windingStyle": None,
                "windingWindow": None,
            })
            section_name = f"{insulation.name} section {index + len(layout.blocks)}"
            layers.append({
                "additionalCoordinates": None,
                "coordinateSystem": "cartesian",
                "coordinates": [(insulation.radial_start_m + insulation.radial_end_m) / 2.0, 0.0],
                "dimensions": [insulation.thickness_m, layout.core.window_height_m],
                "fillingFactor": 1.0,
                "insulationMaterial": None,
                "name": f"{section_name} insulation layer 0",
                "orientation": "overlapping",
                "partialWindings": [],
                "section": section_name,
                "turnsAlignment": "spread",
                "type": "insulation",
                "windingStyle": None,
            })
        group_windings: list[str] = []
        for item in layout.blocks:
            name = electrical_map[item.name]
            if name not in group_windings:
                group_windings.append(name)
        groups = [{
            "coordinateSystem": "cartesian",
            "coordinates": [layout.core.bobbin_wall_m + layout.core.window_width_m / 2.0, 0.0],
            "dimensions": [layout.core.window_width_m, layout.core.window_height_m],
            "name": "Default group",
            "partialWindings": [
                {"connections": None, "parallelsProportion": [1.0], "winding": name}
                for name in group_windings
            ],
            "pcb": None,
            "sectionsOrientation": "overlapping",
            "type": "wound",
            "windingWindow": None,
        }]
        coil = {
            "functionalDescription": windings,
            "bobbin": layout.core.bobbin_id,
            "geometrySource": "sst_parameterized_geometry",
            "geometryVersion": layout.geometry_version,
            "sstElectricalWindingMap": electrical_map,
            "sstElectricalConnections": layout.connection,
            "groupsDescription": groups,
            "sectionsDescription": sections,
            "layersDescription": layers,
            "turnsDescription": turns,
        }
        return {"core": {"functionalDescription": core_fd}, "coil": coil}


def validate_mas_geometry(magnetic: Mapping[str, Any], layout: LayoutGeometry) -> dict[str, Any]:
    """Validate the structural invariants needed by the provider boundary."""

    errors: list[dict[str, Any]] = []
    coil = magnetic.get("coil") if isinstance(magnetic, Mapping) else None
    core = magnetic.get("core") if isinstance(magnetic, Mapping) else None
    fd = coil.get("functionalDescription") if isinstance(coil, Mapping) else None
    if not isinstance(core, Mapping) or not isinstance(core.get("functionalDescription"), Mapping):
        errors.append({"code": "MISSING_CORE_DESCRIPTION", "message": "MAS magnetic.core.functionalDescription 缺失。"})
    expected_fd_count = 2 if layout.template.template_id == "PSP" else len(layout.blocks)
    if not isinstance(fd, list) or len(fd) != expected_fd_count:
        errors.append({"code": "WINDING_BLOCK_COUNT_MISMATCH", "message": f"MAS 电气绕组数量与参数化结构不一致，期望 {expected_fd_count}。"})
        fd = []
    electrical_map = coil.get("sstElectricalWindingMap", {}) if isinstance(coil, Mapping) else {}
    if not isinstance(electrical_map, Mapping):
        errors.append({"code": "MISSING_ELECTRICAL_WINDING_MAP", "message": "缺少物理分段到电气绕组的映射。"})
        electrical_map = {}
    expected_electrical: list[tuple[str, int, str]] = []
    if layout.template.template_id == "PSP":
        primary_blocks = [item for item in layout.blocks if item.role.lower() in {"primary", "p", "原边"}]
        secondary = next(item for item in layout.blocks if item.role.lower() in {"secondary", "s", "副边"})
        expected_electrical = [("Primary", sum(item.turns for item in primary_blocks), primary_blocks[0].wire.wire_id), ("Secondary", secondary.turns, secondary.wire.wire_id)]
    else:
        expected_electrical = [
            (item.name, item.turns, item.wire.wire_id)
            for item in layout.blocks
        ]
    actual_names = [item.get("name") for item in fd if isinstance(item, Mapping)]
    if actual_names != [item[0] for item in expected_electrical]:
        errors.append({"code": "ELECTRICAL_WINDING_ORDER_MISMATCH", "message": f"MAS 电气绕组顺序 {actual_names} 不等于 {[item[0] for item in expected_electrical]}。"})
    for item, expected in zip(fd, expected_electrical):
        if not isinstance(item, Mapping):
            continue
        if int(item.get("numberTurns", -1)) != expected[1]:
            errors.append({"code": "ELECTRICAL_TURN_COUNT_MISMATCH", "message": f"{expected[0]} MAS 电气匝数不一致，期望 {expected[1]}。"})
        if item.get("wire") != expected[2]:
            errors.append({"code": "WIRE_ID_MISMATCH", "message": f"{expected[0]} 导线标识不一致。"})
    expected_map = {item.name: ("Primary" if layout.template.template_id == "PSP" and item.role.lower() in {"primary", "p", "原边"} else "Secondary" if layout.template.template_id == "PSP" else item.name) for item in layout.blocks}
    if dict(electrical_map) != expected_map:
        errors.append({"code": "ELECTRICAL_WINDING_MAP_MISMATCH", "message": f"分段电气映射 {dict(electrical_map)} 不等于 {expected_map}。"})
    if layout.template.template_id == "PSP":
        connection = coil.get("sstElectricalConnections") if isinstance(coil, Mapping) else None
        if not isinstance(connection, Mapping) or connection.get("type") != "series" or connection.get("direction") != "same" or connection.get("primary_segments") != ["P1", "P2"]:
            errors.append({"code": "SERIES_CONNECTION_MISSING", "message": "PSP 没有保留 P1/P2 串联同向连接记录。"})
    for item, block in zip(fd, layout.blocks):
        if not isinstance(item, Mapping):
            continue
        if int(item.get("numberTurns", -1)) != block.turns and layout.template.template_id != "PSP":
            errors.append({"code": "TURN_COUNT_MISMATCH", "message": f"{block.name} MAS 匝数不一致。"})
    for field, expected in (("sectionsDescription", len(layout.blocks) + len(layout.interfaces)), ("layersDescription", sum(len(item.layers) for item in layout.blocks) + len(layout.interfaces)), ("turnsDescription", sum(len(item.turns_geometry) for item in layout.blocks))):
        value = coil.get(field) if isinstance(coil, Mapping) else None
        if not isinstance(value, list) or len(value) != expected:
            errors.append({"code": "GEOMETRY_ARRAY_COUNT_MISMATCH", "message": f"{field} 数量不一致，期望 {expected}。"})
    for item in (coil.get("turnsDescription", []) if isinstance(coil, Mapping) else []):
        if not isinstance(item, Mapping):
            errors.append({"code": "INVALID_TURN_GEOMETRY", "message": "turnsDescription 存在非对象项。"})
            continue
        coords = item.get("coordinates")
        dims = item.get("dimensions")
        if not isinstance(coords, list) or len(coords) != 2 or not isinstance(dims, list) or len(dims) != 2 or any(float(value) <= 0 for value in dims):
            errors.append({"code": "INVALID_TURN_GEOMETRY", "message": f"匝 {item.get('name')} 坐标或尺寸无效。"})
    return {
        "valid": not errors,
        "errors": errors,
        "validator": "sst-mas-geometry-structural-validator",
        "validator_version": MasGeometryAdapter.adapter_version,
        "schema_note": "依据已安装 PyOpenMagnetics 1.7.x wind 输出字段进行结构校验；当前版本未暴露独立官方 JSON Schema 校验器。",
    }
