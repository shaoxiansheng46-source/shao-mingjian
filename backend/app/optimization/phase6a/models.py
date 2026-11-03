"""Serializable Phase 6A variable and run configuration models.

The variable names are application-owned.  They are intentionally converted to
pymoo variables only at the optimization boundary, so the rest of the design
and evaluation code never depends on pymoo's internal value objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pymoo.core.variable import Choice, Integer, Real


@dataclass(frozen=True)
class DesignVariableSpace:
    """Finite, explicit mixed-variable search space in SI units."""

    np_bounds: tuple[int, int] = (16, 24)
    ns_bounds: tuple[int, int] = (4, 8)
    p1_bounds: tuple[int, int] = (1, 23)
    interwinding_gap_bounds_m: tuple[float, float] = (0.0004, 0.0015)
    core_clearance_bounds_m: tuple[float, float] = (0.0003, 0.0012)
    interwinding_gap_step_m: float = 0.00005
    core_clearance_step_m: float = 0.00005
    layout_choices: tuple[str, ...] = ("PS", "PSP")
    primary_wire_choices: tuple[str, ...] = ()
    secondary_wire_choices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, bounds in {
            "np_bounds": self.np_bounds,
            "ns_bounds": self.ns_bounds,
            "p1_bounds": self.p1_bounds,
        }.items():
            if len(bounds) != 2 or int(bounds[0]) > int(bounds[1]):
                raise ValueError(f"INVALID_INTEGER_BOUNDS:{name}")
            if int(bounds[0]) < 1:
                raise ValueError(f"INVALID_INTEGER_BOUNDS:{name}")
        for name, bounds in {
            "interwinding_gap_bounds_m": self.interwinding_gap_bounds_m,
            "core_clearance_bounds_m": self.core_clearance_bounds_m,
        }.items():
            if len(bounds) != 2 or float(bounds[0]) <= 0 or float(bounds[0]) > float(bounds[1]):
                raise ValueError(f"INVALID_REAL_BOUNDS:{name}")
        if self.interwinding_gap_step_m <= 0 or self.core_clearance_step_m <= 0:
            raise ValueError("INVALID_MANUFACTURING_RESOLUTION")
        if not self.layout_choices or any(str(item).upper() not in {"PS", "PSP"} for item in self.layout_choices):
            raise ValueError("UNSUPPORTED_LAYOUT_CHOICE")
        if not self.primary_wire_choices or not self.secondary_wire_choices:
            raise ValueError("MISSING_REAL_WIRE_CHOICES")
        if self.np_bounds[1] < 2 and "PSP" in self.layout_choices:
            raise ValueError("PSP_REQUIRES_AT_LEAST_TWO_PRIMARY_TURNS")

    def variables(self) -> dict[str, Any]:
        """Create pymoo 0.6.x mixed variables without exposing them elsewhere."""

        return {
            "Np": Integer(bounds=self.np_bounds),
            "Ns": Integer(bounds=self.ns_bounds),
            "P1": Integer(bounds=self.p1_bounds),
            "interwinding_gap_m": Real(bounds=self.interwinding_gap_bounds_m),
            "core_clearance_m": Real(bounds=self.core_clearance_bounds_m),
            "layout": Choice(options=list(self.layout_choices)),
            "primary_wire": Choice(options=list(self.primary_wire_choices)),
            "secondary_wire": Choice(options=list(self.secondary_wire_choices)),
        }

    def normalize(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize one pymoo dict or JSON dict and reject invalid values."""

        def integer(key: str, bounds: tuple[int, int]) -> int:
            value = values.get(key)
            if isinstance(value, bool) or value is None:
                raise ValueError(f"MISSING_VARIABLE:{key}")
            number = float(value)
            if not number.is_integer():
                raise ValueError(f"NON_INTEGER_VARIABLE:{key}")
            result = int(number)
            if result < bounds[0] or result > bounds[1]:
                raise ValueError(f"VARIABLE_OUT_OF_BOUNDS:{key}")
            return result

        def real(key: str, bounds: tuple[float, float], step: float) -> float:
            value = float(values.get(key))
            if not bounds[0] <= value <= bounds[1]:
                raise ValueError(f"VARIABLE_OUT_OF_BOUNDS:{key}")
            quantized = bounds[0] + round((value - bounds[0]) / step) * step
            return min(bounds[1], max(bounds[0], round(quantized, 12)))

        layout = str(values.get("layout", "")).upper()
        if layout not in {str(item).upper() for item in self.layout_choices}:
            raise ValueError("UNSUPPORTED_LAYOUT_CHOICE")
        primary_wire = str(values.get("primary_wire", ""))
        secondary_wire = str(values.get("secondary_wire", ""))
        if primary_wire not in self.primary_wire_choices or secondary_wire not in self.secondary_wire_choices:
            raise ValueError("UNSUPPORTED_WIRE_CHOICE")
        np_turns = integer("Np", self.np_bounds)
        ns_turns = integer("Ns", self.ns_bounds)
        p1 = integer("P1", self.p1_bounds)
        if layout == "PSP" and not 1 <= p1 < np_turns:
            raise ValueError("PRIMARY_SPLIT_OUT_OF_BOUNDS")
        return {
            "Np": np_turns,
            "Ns": ns_turns,
            # P1/P2 are not electrical variables for PS. Canonicalizing them
            # prevents unused genes from creating duplicate physical
            # candidates or pretending that PS has a hidden split.
            "P1": p1 if layout == "PSP" else 0,
            "P2": np_turns - p1 if layout == "PSP" else np_turns,
            "interwinding_gap_m": real("interwinding_gap_m", self.interwinding_gap_bounds_m, self.interwinding_gap_step_m),
            "core_clearance_m": real("core_clearance_m", self.core_clearance_bounds_m, self.core_clearance_step_m),
            "layout": layout,
            "primary_wire": primary_wire,
            "secondary_wire": secondary_wire,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "integer": {"Np": list(self.np_bounds), "Ns": list(self.ns_bounds), "P1": list(self.p1_bounds)},
            "real_SI": {
                "interwinding_gap_m": list(self.interwinding_gap_bounds_m),
                "core_clearance_m": list(self.core_clearance_bounds_m),
                "manufacturing_resolution_m": {
                    "interwinding_gap_m": self.interwinding_gap_step_m,
                    "core_clearance_m": self.core_clearance_step_m,
                },
            },
            "choice": {
                "layout": list(self.layout_choices),
                "primary_wire": list(self.primary_wire_choices),
                "secondary_wire": list(self.secondary_wire_choices),
            },
            "unsupported_not_exposed": ["winding_height", "winding_thickness", "core_selection"],
        }


@dataclass(frozen=True)
class Phase6AConfig:
    """Optimization limits and research-constraint policy."""

    seed: int = 20261103
    population_size: int = 8
    generations: int = 4
    max_evaluations: int = 64
    timeout_s: float | None = 300.0
    invalid_objective_value: float = 1.0e9
    unknown_constraint_sentinel: float = 1.0e6
    turns_ratio_target: float | None = 4.0
    turns_ratio_tolerance: float = 0.05
    bmax_max_t: float | None = 0.25
    lm_min_h: float | None = 100e-6
    lm_max_h: float | None = 2.0e-3
    leakage_target_h: float | None = None
    leakage_relative_tolerance: float = 0.20
    model_version: str = "sst-phase6a-mixed-optimization-0.1.0"

    def __post_init__(self) -> None:
        if self.population_size < 2 or self.generations < 1 or self.max_evaluations < 1:
            raise ValueError("INVALID_OPTIMIZATION_BUDGET")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError("INVALID_TIMEOUT")
        if self.turns_ratio_tolerance < 0 or self.leakage_relative_tolerance < 0:
            raise ValueError("INVALID_TOLERANCE")

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "population_size": self.population_size,
            "generations": self.generations,
            "max_evaluations": self.max_evaluations,
            "timeout_s": self.timeout_s,
            "invalid_objective_value": self.invalid_objective_value,
            "unknown_constraint_sentinel": self.unknown_constraint_sentinel,
            "turns_ratio_target": self.turns_ratio_target,
            "turns_ratio_tolerance": self.turns_ratio_tolerance,
            "bmax_max_t": self.bmax_max_t,
            "lm_min_h": self.lm_min_h,
            "lm_max_h": self.lm_max_h,
            "leakage_target_h": self.leakage_target_h,
            "leakage_relative_tolerance": self.leakage_relative_tolerance,
            "model_version": self.model_version,
        }
