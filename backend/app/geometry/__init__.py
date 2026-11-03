"""Independent Phase 3 parameterized geometry and joint-calculation API.

This package is intentionally not imported by the existing synthetic engine.
It is a research-prototype boundary for generating explicit SI-unit geometry,
mapping it to the Phase 2 MAS adapter, and optionally calling OpenMagnetics.
"""

from .joint import JointCalculationService
from .layout import build_layout
from .mas_geometry import MasGeometryAdapter, validate_mas_geometry
from .models import (
    CoreGeometry,
    InsulationGeometry,
    LayoutGeometry,
    WireGeometry,
    WindingLayout,
    WindingSpec,
)

__all__ = [
    "CoreGeometry",
    "InsulationGeometry",
    "JointCalculationService",
    "LayoutGeometry",
    "MasGeometryAdapter",
    "WireGeometry",
    "WindingLayout",
    "WindingSpec",
    "build_layout",
    "validate_mas_geometry",
]
