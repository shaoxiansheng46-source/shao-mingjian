"""Domain-owned, SI-unit geometry data structures for Phase 3.

The classes in this module deliberately contain no PyOpenMagnetics objects.
They are serializable application data and keep physical dimensions separate
from effective magnetic parameters obtained from a database/provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import pi
from typing import Any


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return value


@dataclass
class CoreGeometry:
    """Physical core/bobbin geometry plus effective magnetic parameters."""

    core_id: str
    shape_name: str
    material_name: str
    physical_dimensions_m: dict[str, float]
    effective_area_m2: float
    effective_length_m: float
    effective_volume_m3: float
    window_width_m: float
    window_height_m: float
    winding_column_width_m: float
    winding_column_depth_m: float
    bobbin_wall_m: float = 0.0
    bobbin_id: str | None = None
    gap_m: float = 0.0
    gap_position: str = "center_leg"
    stack_count: int = 1
    mass_kg: float | None = None
    data_status: str = "external_database"
    synthetic: bool = False
    demo_only: bool = False
    engineering_approved: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = _clean(asdict(self))
        data["effective_parameters"] = {
            "effective_area_m2": self.effective_area_m2,
            "effective_length_m": self.effective_length_m,
            "effective_volume_m3": self.effective_volume_m3,
        }
        data["gap"] = {
            "length_m": self.gap_m,
            "position": self.gap_position,
        }
        return data


@dataclass
class WireGeometry:
    """A real or explicitly supplied conductor definition in SI units."""

    wire_id: str
    outer_diameter_m: float
    conducting_diameter_m: float | None = None
    resistance_ohm_per_m: float | None = None
    diameter_tolerance_m: float = 0.0
    insulation_thickness_m: float = 0.0
    number_conductors: int = 1
    data_status: str = "external_database"
    synthetic: bool = False
    demo_only: bool = False
    engineering_approved: bool = False

    @property
    def copper_area_m2(self) -> float | None:
        diameter = self.conducting_diameter_m or self.outer_diameter_m
        if diameter <= 0:
            return None
        return pi * (diameter / 2.0) ** 2 * max(self.number_conductors, 1)

    def as_dict(self) -> dict[str, Any]:
        data = _clean(asdict(self))
        data["copper_area_m2"] = self.copper_area_m2
        return data


@dataclass
class WindingSpec:
    """Input winding requirement before it is placed in the window."""

    name: str
    role: str
    turns: int
    wire: WireGeometry
    parallels: int = 1
    isolation_side: str | None = None
    lead_allowance_m: float = 0.15
    explicit_segment_names: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = _clean(asdict(self))
        data["wire"] = self.wire.as_dict()
        return data


@dataclass
class WindingLayout:
    """Explicit layout template and manufacturing rules.

    ``block_order`` is a physical radial order, not merely a display string.
    ``axial_turns_radial_layers`` means turns advance along the window height
    and layers advance across the window width.
    """

    template_id: str
    block_order: list[str]
    radial_or_axial: str = "radial"
    orientation: str = "axial_turns_radial_layers"
    process_clearance_m: float = 0.00015
    layer_insulation_m: float = 0.0002
    main_insulation_m: float = 0.001
    winding_to_core_clearance_m: float = 0.001
    end_margin_m: float = 0.003
    lead_allowance_m: float = 0.15
    supported: bool = True

    def as_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class InsulationGeometry:
    """One full physical barrier between adjacent winding blocks."""

    name: str
    between: tuple[str, str]
    thickness_m: float
    radial_start_m: float
    radial_end_m: float
    material_id: str | None = None
    rule_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = _clean(asdict(self))
        data["between"] = list(self.between)
        return data


@dataclass
class TurnGeometry:
    winding: str
    segment: str
    layer_index: int
    turn_index: int
    parallel_index: int
    turns_index: int
    coordinates_m: tuple[float, float]
    dimensions_m: tuple[float, float]
    length_m: float

    def as_dict(self) -> dict[str, Any]:
        data = _clean(asdict(self))
        data["coordinates_m"] = list(self.coordinates_m)
        data["dimensions_m"] = list(self.dimensions_m)
        return data


@dataclass
class LayerGeometry:
    winding: str
    segment: str
    layer_index: int
    radial_start_m: float
    radial_end_m: float
    axial_start_m: float
    axial_end_m: float
    turns_per_parallel: int
    parallel_count: int
    turn_indices: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class WindingSegmentGeometry:
    name: str
    winding: str
    role: str
    turns: int
    parallels: int
    wire: WireGeometry
    radial_start_m: float
    radial_end_m: float
    axial_start_m: float
    axial_end_m: float
    layer_count: int
    turns_per_layer: int
    mean_turn_length_m: float
    branch_length_m: float
    resistance_ohm: float | None
    copper_area_m2: float | None
    layers: list[LayerGeometry] = field(default_factory=list)
    turns_geometry: list[TurnGeometry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = _clean(asdict(self))
        data["wire"] = self.wire.as_dict()
        data["layers"] = [item.as_dict() for item in self.layers]
        data["turns_geometry"] = [item.as_dict() for item in self.turns_geometry]
        return data


@dataclass
class GeometryViolation:
    code: str
    message: str
    field: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class LayoutGeometry:
    template: WindingLayout
    core: CoreGeometry
    blocks: list[WindingSegmentGeometry]
    interfaces: list[InsulationGeometry]
    connection: dict[str, Any]
    feasible: bool
    violations: list[GeometryViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_status: str = "parameterized_geometry"
    geometry_version: str = "sst-geometry-0.1.0"
    volume_m3: float | None = None
    mass_kg: float | None = None
    provenance: dict[str, Any] = field(default_factory=lambda: {
        "data_status": "external_database",
        "synthetic": False,
        "demo_only": False,
        "engineering_approved": False,
    })

    @property
    def status(self) -> str:
        if any(item.code == "UNSUPPORTED_GEOMETRY" for item in self.violations):
            return "unsupported"
        return "feasible" if self.feasible else "infeasible"

    def as_dict(self) -> dict[str, Any]:
        return {
            "template": self.template.as_dict(),
            "core": self.core.as_dict(),
            "blocks": [item.as_dict() for item in self.blocks],
            "interfaces": [item.as_dict() for item in self.interfaces],
            "connection": _clean(self.connection),
            "feasible": self.feasible,
            "status": self.status,
            "violations": [item.as_dict() for item in self.violations],
            "warnings": list(self.warnings),
            "model_status": self.model_status,
            "geometry_version": self.geometry_version,
            "volume_m3": self.volume_m3,
            "mass_kg": self.mass_kg,
            "provenance": _clean(self.provenance),
        }
