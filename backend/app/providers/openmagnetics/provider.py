"""OpenMagnetics provider implementation.

This module is deliberately independent of the current SST synthetic engine.
It resolves application-level names into PyOpenMagnetics objects internally and
returns only normalized summaries and traceable metric results.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from .mas_adapter import MasAdapterError
from .models import Diagnostic, MetricResult, ProviderProvenance, error_result
from .runtime import load_module, version_info


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, Mapping):
        for key in ("nominal", "minimum", "maximum"):
            if value.get(key) is not None:
                return float(value[key])
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _range_number(value: Any) -> dict[str, float | None]:
    if not isinstance(value, Mapping):
        number = _number(value)
        return {"minimum": number, "nominal": number, "maximum": number}
    return {
        "minimum": _number(value.get("minimum")),
        "nominal": _number(value.get("nominal")),
        "maximum": _number(value.get("maximum")),
    }


def _manufacturer(record: Mapping[str, Any]) -> str | None:
    info = record.get("manufacturerInfo")
    return info.get("name") if isinstance(info, Mapping) else None


def _loss_value(component: Any) -> float | None:
    if isinstance(component, Mapping):
        if component.get("losses") is not None:
            return _number(component.get("losses"))
        values = component.get("lossesPerHarmonic")
        if isinstance(values, Sequence):
            return sum(float(item) for item in values)
    return _number(component)


def _sum_turn_loss_components(output: Mapping[str, Any], field: str) -> tuple[float | None, int]:
    """Extract a component when MKF only exposes it per turn.

    PyOpenMagnetics 1.7.35 returns ``None`` in
    ``windingLossesPerWinding`` for the standalone skin/proximity stages,
    while the same result contains the component in each
    ``windingLossesPerTurn`` item.  Missing values remain missing; this helper
    never converts an absent component to zero.
    """
    values: list[float] = []
    for item in output.get("windingLossesPerTurn", []) or []:
        if not isinstance(item, Mapping):
            continue
        value = _loss_value(item.get(field))
        if value is not None:
            values.append(float(value))
    return (sum(values), len(values)) if values else (None, 0)


def _permeability_real_at(record: Mapping[str, Any], frequency_hz: float) -> float | None:
    permeability = record.get("permeability")
    if not isinstance(permeability, Mapping):
        return None
    complex_data = permeability.get("complex")
    real_values = complex_data.get("real") if isinstance(complex_data, Mapping) else None
    if not isinstance(real_values, Sequence):
        return None
    candidates = [item for item in real_values if isinstance(item, Mapping) and item.get("frequency") is not None and item.get("value") is not None]
    if not candidates:
        return None
    selected = min(candidates, key=lambda item: abs(float(item["frequency"]) - frequency_hz))
    return float(selected["value"])


class OpenMagneticsProvider:
    """Lazy, normalized façade around a real PyOpenMagnetics installation."""

    def __init__(self, module: Any | None = None, *, initialize: bool = True):
        self._module = module
        self._startup_error: dict[str, Any] | None = None
        self._initialized = module is not None
        if initialize and module is None:
            self.initialize()

    @property
    def available(self) -> bool:
        return self._module is not None and self._initialized

    def initialize(self) -> dict[str, Any]:
        module, error = load_module()
        self._module = module
        self._startup_error = error
        self._initialized = module is not None
        return self.status()

    def _provenance(self) -> ProviderProvenance:
        info = version_info(self._module)
        return ProviderProvenance(
            third_party_version=info.get("version"),
            mkf_commit=info.get("mkf_commit"),
            mas_commit=info.get("mas_commit"),
        )

    def status(self) -> dict[str, Any]:
        info = version_info(self._module)
        result: dict[str, Any] = {
            "provider": "OpenMagneticsProvider",
            "available": self.available,
            "initialized": self._initialized,
            "provenance": self._provenance().as_dict(),
            "database_counts": None,
            "errors": [],
        }
        if self._startup_error:
            result["errors"].append(self._startup_error)
        if self.available:
            try:
                result["database_counts"] = {
                    "core_materials": len(self._module.get_core_materials()),
                    "core_shapes": len(self._module.get_core_shapes()),
                    "wires": len(self._module.get_wires()),
                }
            except Exception as exc:  # pragma: no cover - provider/runtime dependent
                result["errors"].append({"code": "DATABASE_QUERY_FAILED", "message": str(exc)})
        result["third_party_version"] = info.get("version")
        return result

    def _unavailable(self, calculation: str, *, material: str | None = None) -> dict[str, Any]:
        diagnostic = Diagnostic(
            code=(self._startup_error or {}).get("code", "OPENMAGNETICS_UNAVAILABLE"),
            message=(self._startup_error or {}).get("message", "OpenMagnetics Provider 未初始化。"),
        )
        return error_result(calculation, diagnostic, self._provenance(), material=material, status="unavailable")

    def _call(self, calculation: str, function: Callable[..., Any], *args: Any, material: str | None = None, model: str | None = None, **kwargs: Any) -> tuple[Any | None, dict[str, Any] | None]:
        if not self.available:
            return None, {"code": "OPENMAGNETICS_UNAVAILABLE", "message": self._unavailable(calculation, material=material)}
        try:
            return function(*args, **kwargs), None
        except Exception as exc:  # PyOM EngineError and validation errors
            return None, {
                "code": "OPENMAGNETICS_CALCULATION_FAILED",
                "message": f"{type(exc).__name__}: {exc}",
                "calculation": calculation,
                "model": model,
            }

    def _failed(self, calculation: str, error: dict[str, Any], *, material: str | None = None, model: str | None = None) -> dict[str, Any]:
        return error_result(
            calculation,
            Diagnostic(code=error.get("code", "OPENMAGNETICS_ERROR"), message=str(error.get("message", error))),
            self._provenance(),
            material=material,
            model=model,
        )

    def _ok(self, calculation: str, value: Any, unit: str | None, *, model: str | None = None, material: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return MetricResult(
            calculation=calculation,
            value=value,
            unit=unit,
            model=model,
            material=material,
            provenance=self._provenance(),
            details=details or {},
        ).as_dict()

    @staticmethod
    def _material_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "name": record.get("name"),
            "commercial_name": record.get("commercialName"),
            "manufacturer": _manufacturer(record),
            "family": record.get("family"),
            "density_kg_m3": _number(record.get("density")),
            "curie_temperature_c": _number(record.get("curieTemperature")),
            "permeability_real_at_100khz": _permeability_real_at(record, 100000.0),
            "data_status": "external_database",
        }

    @staticmethod
    def _shape_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        dimensions: dict[str, Any] = {}
        for key, value in (record.get("dimensions") or {}).items():
            if isinstance(value, Mapping):
                dimensions[key] = {
                    "minimum_m": _number(value.get("minimum")),
                    "nominal_m": _number(value.get("nominal")),
                    "maximum_m": _number(value.get("maximum")),
                }
            else:
                dimensions[key] = value
        return {
            "name": record.get("name"),
            "family": record.get("family"),
            "family_subtype": record.get("familySubtype"),
            "type": record.get("type"),
            "dimensions_m": dimensions,
            "data_status": "external_database",
        }

    @staticmethod
    def _wire_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        outer = record.get("outerDiameter")
        return {
            "name": record.get("name"),
            "type": record.get("type"),
            "standard": record.get("standard"),
            "manufacturer": _manufacturer(record),
            "number_conductors": record.get("numberConductors"),
            "conducting_diameter_m": _number(record.get("conductingDiameter")),
            "outer_diameter_m": _number(outer),
            "data_status": "external_database",
        }

    @staticmethod
    def _litz_wire_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        outer = _range_number(record.get("outerDiameter"))
        coating = record.get("coating") if isinstance(record.get("coating"), Mapping) else {}
        manufacturer = record.get("manufacturerInfo") if isinstance(record.get("manufacturerInfo"), Mapping) else {}
        return {
            "name": record.get("name"),
            "type": record.get("type"),
            "standard": record.get("standard"),
            "manufacturer": manufacturer.get("name"),
            "number_conductors": record.get("numberConductors"),
            "strand": record.get("strand"),
            "twist_pitch_m": _number(record.get("twistPitch")),
            "conducting_area_m2": _number(record.get("conductingArea")),
            "conducting_diameter_m": _number(record.get("conductingDiameter")),
            "outer_diameter_m": outer,
            "outer_width_m": _number(record.get("outerWidth")),
            "outer_height_m": _number(record.get("outerHeight")),
            "coating": {
                "type": coating.get("type"),
                "number_layers": coating.get("numberLayers"),
                "thickness_m": _number(coating.get("thickness")),
                "thickness_layers_m": _number(coating.get("thicknessLayers")),
                "grade": coating.get("grade"),
            },
            "conductor_material": record.get("material"),
            "data_status": "external_database",
        }

    def _list(self, kind: str, function_name: str, summary: Callable[[Mapping[str, Any]], dict[str, Any]], limit: int | None) -> dict[str, Any]:
        if not self.available:
            return {"status": "unavailable", "items": [], "count": 0, "provenance": self._provenance().as_dict(), "errors": [self._unavailable(f"get_{kind}")]}
        try:
            records = list(getattr(self._module, function_name)())
            items = [summary(item) for item in records[:limit] if isinstance(item, Mapping)] if limit else [summary(item) for item in records if isinstance(item, Mapping)]
            return {"status": "ok", "items": items, "count": len(records), "provenance": self._provenance().as_dict(), "errors": []}
        except Exception as exc:
            return {"status": "error", "items": [], "count": 0, "provenance": self._provenance().as_dict(), "errors": [{"code": "DATABASE_QUERY_FAILED", "message": f"{type(exc).__name__}: {exc}"}]}

    def get_core_materials(self, limit: int | None = None) -> dict[str, Any]:
        return self._list("core_materials", "get_core_materials", self._material_summary, limit)

    def get_core_shapes(self, limit: int | None = None) -> dict[str, Any]:
        return self._list("core_shapes", "get_core_shapes", self._shape_summary, limit)

    def get_wires(self, limit: int | None = None) -> dict[str, Any]:
        return self._list("wires", "get_wires", self._wire_summary, limit)

    def _find(self, calculation: str, name: str, function_name: str, summary: Callable[[Mapping[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        if not self.available:
            return self._unavailable(calculation)
        try:
            record = getattr(self._module, function_name)(name)
            if not isinstance(record, Mapping) or not record:
                return self._failed(calculation, {"code": "NOT_FOUND", "message": f"数据库中不存在 {name}。"})
            return self._ok(calculation, summary(record), None, model="OpenMagnetics database lookup", details={"name": name})
        except Exception as exc:
            return self._failed(calculation, {"code": "LOOKUP_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def find_core_material_by_name(self, name: str) -> dict[str, Any]:
        return self._find("core_material_lookup", name, "find_core_material_by_name", self._material_summary)

    def find_core_shape_by_name(self, name: str) -> dict[str, Any]:
        return self._find("core_shape_lookup", name, "find_core_shape_by_name", self._shape_summary)

    def find_wire_by_name(self, name: str) -> dict[str, Any]:
        return self._find("wire_lookup", name, "find_wire_by_name", self._wire_summary)

    def find_litz_wire_by_name(self, name: str) -> dict[str, Any]:
        """Return the detailed normalized Litz record without exposing MKF objects."""
        if not self.available:
            return self._unavailable("litz_wire_lookup")
        try:
            record = self._module.find_wire_by_name(name)
            if not isinstance(record, Mapping) or not record:
                return self._failed("litz_wire_lookup", {"code": "NOT_FOUND", "message": f"数据库中不存在 {name}。"})
            if str(record.get("type", "")).lower() != "litz":
                return self._failed("litz_wire_lookup", {"code": "NOT_LITZ_WIRE", "message": f"{name} 不是 type=litz 的导线。"})
            return self._ok("litz_wire_lookup", self._litz_wire_summary(record), None, model="OpenMagnetics detailed wire lookup", details={"name": name})
        except Exception as exc:
            return self._failed("litz_wire_lookup", {"code": "LOOKUP_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def calculate_wire_dc_resistance_per_meter(self, wire: Mapping[str, Any] | str, temperature_c: float = 25.0) -> dict[str, Any]:
        if not self.available:
            return self._unavailable("wire_dc_resistance_per_meter")
        try:
            resolved = self._module.find_wire_by_name(wire) if isinstance(wire, str) else wire
            if not isinstance(resolved, Mapping):
                raise ValueError("wire 必须是数据库名称或导线对象。")
            value = float(self._module.calculate_dc_resistance_per_meter(resolved, float(temperature_c)))
            return self._ok("wire_dc_resistance_per_meter", value, "ohm/m", model="calculate_dc_resistance_per_meter", details={"temperature_c": float(temperature_c), "wire_name": resolved.get("name")})
        except Exception as exc:
            return self._failed("wire_dc_resistance_per_meter", {"code": "WIRE_DC_RESISTANCE_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def calculate_wire_skin_ac_resistance_per_meter(self, wire: Mapping[str, Any] | str, current: Mapping[str, Any], temperature_c: float = 25.0) -> dict[str, Any]:
        if not self.available:
            return self._unavailable("wire_skin_ac_resistance_per_meter")
        try:
            resolved = self._module.find_wire_by_name(wire) if isinstance(wire, str) else wire
            if not isinstance(resolved, Mapping):
                raise ValueError("wire 必须是数据库名称或导线对象。")
            value = float(self._module.calculate_skin_ac_resistance_per_meter(resolved, current, float(temperature_c)))
            return self._ok("wire_skin_ac_resistance_per_meter", value, "ohm/m", model="calculate_skin_ac_resistance_per_meter", details={"temperature_c": float(temperature_c), "wire_name": resolved.get("name")})
        except Exception as exc:
            return self._failed("wire_skin_ac_resistance_per_meter", {"code": "WIRE_SKIN_RESISTANCE_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def calculate_skin_effect_losses_processed(self, coil: Mapping[str, Any], operating_point: Mapping[str, Any], temperature_c: float = 25.0) -> dict[str, Any]:
        """Run MKF skin loss after the caller supplies processed harmonics.

        MKF returns the accumulated winding loss after its skin stage rather
        than a top-level ``skinEffectLosses`` scalar.  The provider exposes the
        measured increment over the raw ohmic result and never turns missing
        output into zero.
        """
        if not self.available:
            return self._unavailable("skin_effect_losses")
        try:
            resolved_coil = self._resolve_coil(coil)
            ohmic = self._module.calculate_ohmic_losses(resolved_coil, operating_point, float(temperature_c))
            after_skin = self._module.calculate_skin_effect_losses(resolved_coil, ohmic, float(temperature_c))
            ohmic_value = _number(ohmic.get("windingLosses"))
            after_value = _number(after_skin.get("windingLosses"))
            if ohmic_value is None or after_value is None:
                raise ValueError("第三方集肤阶段缺少 windingLosses，不能转换为零。")
            return self._ok(
                "skin_effect_losses",
                after_value - ohmic_value,
                "W",
                model="calculate_skin_effect_losses:increment",
                details={"ohmic_w": ohmic_value, "after_skin_w": after_value, "temperature_c": float(temperature_c)},
            )
        except Exception as exc:
            return self._failed("skin_effect_losses", {"code": "SKIN_LOSSES_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    @staticmethod
    def _bobbin_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        processed = record.get("processedDescription") if isinstance(record.get("processedDescription"), Mapping) else {}
        return {
            "name": record.get("name"),
            "shape": (record.get("functionalDescription") or {}).get("shape") if isinstance(record.get("functionalDescription"), Mapping) else None,
            "processed_description": {
                "column_depth_m": _number(processed.get("columnDepth")),
                "column_thickness_m": _number(processed.get("columnThickness")),
                "column_width_m": _number(processed.get("columnWidth")),
                "wall_thickness_m": _number(processed.get("wallThickness")),
                "winding_windows": copy.deepcopy(processed.get("windingWindows", [])),
            },
            "data_status": "external_database",
        }

    def find_bobbin_by_name(self, name: str) -> dict[str, Any]:
        return self._find("bobbin_lookup", name, "find_bobbin_by_name", self._bobbin_summary)

    def _resolve_core(self, core: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
        functional = core.get("functionalDescription", core)
        if not isinstance(functional, Mapping):
            raise ValueError("core.functionalDescription 必须是对象。")
        shape = functional.get("shape")
        material = functional.get("material")
        if isinstance(shape, str):
            shape = self._module.find_core_shape_by_name(shape)
        if isinstance(material, str):
            material = self._module.find_core_material_by_name(material)
        if not isinstance(shape, Mapping) or not isinstance(material, Mapping):
            raise ValueError("磁芯 shape/material 必须是数据库名称。")
        gapping = []
        for item in functional.get("gapping", []) or []:
            if not isinstance(item, Mapping):
                raise ValueError("gapping 项必须是对象。")
            length = item.get("length", item.get("length_m"))
            if length is None and item.get("length_mm") is not None:
                length = float(item["length_mm"]) * 1e-3
            if length is None:
                raise ValueError("gapping 缺少长度，不能静默视为零。")
            gapping.append({"type": item.get("type", "subtractive"), "length": float(length)})
        return {
            "functionalDescription": {
                "type": functional.get("type", "two-piece set"),
                "shape": shape,
                "material": material,
                "gapping": gapping,
                "numberStacks": int(functional.get("numberStacks", functional.get("number_stacks", 1))),
            }
        }, material.get("name")

    def _resolve_coil(self, coil: Mapping[str, Any]) -> dict[str, Any]:
        functional = coil.get("functionalDescription", coil.get("windings"))
        if not isinstance(functional, Sequence) or isinstance(functional, (str, bytes)):
            raise ValueError("coil.functionalDescription 必须是绕组数组。")
        resolved: dict[str, Any] = {"functionalDescription": []}
        if coil.get("bobbin"):
            bobbin = coil["bobbin"]
            resolved["bobbin"] = self._module.find_bobbin_by_name(bobbin) if isinstance(bobbin, str) else bobbin
        for item in functional:
            if not isinstance(item, Mapping):
                raise ValueError("绕组项必须是对象。")
            wire = item.get("wire")
            if isinstance(wire, str):
                wire = self._module.find_wire_by_name(wire)
            if not isinstance(wire, Mapping):
                raise ValueError("绕组 wire 必须是数据库名称。")
            resolved["functionalDescription"].append(
                {
                    "connections": item.get("connections"),
                    "name": item.get("name", "Winding"),
                    "numberTurns": int(item.get("numberTurns", item.get("number_turns"))),
                    "numberParallels": int(item.get("numberParallels", item.get("number_parallels", 1))),
                    "wire": wire,
                    "isolationSide": item.get("isolationSide", item.get("isolation_side")),
                    "windingWindow": item.get("windingWindow"),
                    "woundWith": item.get("woundWith"),
                }
            )
        # A Phase 3 layout may carry explicit sections/layers/turns.  Preserve
        # those arrays verbatim after resolving only database identifiers.  The
        # previous Phase 2 path remains the default and still calls wind().
        geometry_fields = ("groupsDescription", "sectionsDescription", "layersDescription", "turnsDescription")
        if all(field in coil for field in geometry_fields):
            for field in geometry_fields:
                value = coil.get(field)
                if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                    raise ValueError(f"{field} 必须是数组。")
                resolved[field] = copy.deepcopy(list(value))
            resolved["geometrySource"] = coil.get("geometrySource", "external_parameterized_geometry")
            resolved["geometryVersion"] = coil.get("geometryVersion")
            return resolved
        repetitions = int(coil.get("repetitions", 1))
        proportions = coil.get("proportion_per_winding", coil.get("proportions"))
        if proportions is None:
            proportions = [1.0 / len(resolved["functionalDescription"])] * len(resolved["functionalDescription"])
        pattern = coil.get("pattern", list(range(len(resolved["functionalDescription"]))))
        margin_pairs = coil.get("margin_pairs", [[0.0, 0.0] for _ in resolved["functionalDescription"]])
        return self._module.wind(resolved, repetitions, proportions, pattern, margin_pairs)

    @staticmethod
    def _op_value(operating_point: Mapping[str, Any]) -> Mapping[str, Any]:
        return operating_point

    @staticmethod
    def _inputs_value(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        return inputs

    @staticmethod
    def _material_from_core(core: Mapping[str, Any]) -> str | None:
        fd = core.get("functionalDescription", core)
        material = fd.get("material") if isinstance(fd, Mapping) else None
        return material if isinstance(material, str) else material.get("name") if isinstance(material, Mapping) else None

    def calculate_core_data(self, core: Mapping[str, Any], include_material_data: bool = False) -> dict[str, Any]:
        material_name = self._material_from_core(core)
        if not self.available:
            return self._unavailable("core_data", material=material_name)
        try:
            resolved, resolved_material = self._resolve_core(core)
            calculated = self._module.calculate_core_data(resolved, include_material_data)
            parameters = calculated.get("processedDescription", {}).get("effectiveParameters", {})
            value = {
                "effective_area_m2": _number(parameters.get("effectiveArea")),
                "effective_length_m": _number(parameters.get("effectiveLength")),
                "effective_volume_m3": _number(parameters.get("effectiveVolume")),
                "minimum_area_m2": _number(parameters.get("minimumArea")),
            }
            return self._ok("core_data", value, None, model="calculate_core_data", material=resolved_material, details={"data_status": "external_database", "has_geometry": bool(calculated.get("geometricalDescription"))})
        except Exception as exc:
            return self._failed("core_data", {"code": "CORE_DATA_FAILED", "message": f"{type(exc).__name__}: {exc}"}, material=material_name, model="calculate_core_data")

    def calculate_inductance(self, core: Mapping[str, Any], coil: Mapping[str, Any], operating_point: Mapping[str, Any], models: Mapping[str, Any] | None = None) -> dict[str, Any]:
        material_name = self._material_from_core(core)
        model = (models or {}).get("reluctance", "ZHANG")
        if not self.available:
            return self._unavailable("magnetizing_inductance", material=material_name)
        try:
            resolved_core, resolved_material = self._resolve_core(core)
            resolved_coil = self._resolve_coil(coil)
            value = self._module.calculate_inductance_from_number_turns_and_gapping(resolved_core, resolved_coil, self._op_value(operating_point), {"reluctance": model})
            return self._ok("magnetizing_inductance", float(value), "H", model=f"calculate_inductance_from_number_turns_and_gapping:{model}", material=resolved_material, details={"data_status": "external_database"})
        except Exception as exc:
            return self._failed("magnetizing_inductance", {"code": "INDUCTANCE_FAILED", "message": f"{type(exc).__name__}: {exc}"}, material=material_name, model=str(model))

    def calculate_leakage_inductance(self, magnetic: Mapping[str, Any], frequency_hz: float, *, source_index: int = 0, destination_index: int = 1) -> dict[str, Any]:
        """Run MKF's geometry/field-energy leakage calculation.

        The provider resolves names and processes the core before crossing the
        third-party boundary.  The application receives the requested source
        to destination value plus the complete per-winding output; no failure
        is converted to zero.
        """

        core = magnetic.get("core") if isinstance(magnetic, Mapping) else None
        coil = magnetic.get("coil") if isinstance(magnetic, Mapping) else None
        material_name = self._material_from_core(core or {}) if isinstance(core, Mapping) else None
        if not self.available:
            return self._unavailable("leakage_inductance", material=material_name)
        try:
            if not isinstance(core, Mapping) or not isinstance(coil, Mapping):
                raise ValueError("magnetic.core 和 magnetic.coil 必须提供。")
            resolved_core, resolved_material = self._resolve_core(core)
            resolved_core = self._module.calculate_core_data(resolved_core, False)
            resolved_coil = self._resolve_coil(coil)
            output = self._module.calculate_leakage_inductance({"core": resolved_core, "coil": resolved_coil}, float(frequency_hz), int(source_index))
            raw_values = output.get("leakageInductancePerWinding", []) if isinstance(output, Mapping) else []
            values = []
            for item in raw_values:
                if not isinstance(item, Mapping) or item.get("nominal") is None:
                    values.append(None)
                else:
                    values.append(float(item["nominal"]))
            if destination_index < 0 or destination_index >= len(values) or values[destination_index] is None:
                raise ValueError(f"第三方结果缺少 destination winding {destination_index} 的漏感。")
            return self._ok(
                "leakage_inductance",
                values[destination_index],
                "H",
                model=f"calculate_leakage_inductance:{output.get('methodUsed', 'unknown') if isinstance(output, Mapping) else 'unknown'}",
                material=resolved_material,
                details={"frequency_hz": float(frequency_hz), "source_index": int(source_index), "destination_index": int(destination_index), "per_winding_h": values, "method_used": output.get("methodUsed") if isinstance(output, Mapping) else None},
            )
        except Exception as exc:
            return self._failed("leakage_inductance", {"code": "LEAKAGE_INDUCTANCE_FAILED", "message": f"{type(exc).__name__}: {exc}"}, material=material_name, model="calculate_leakage_inductance")

    def calculate_gap_for_inductance(self, core: Mapping[str, Any], coil: Mapping[str, Any], inputs: Mapping[str, Any], gapping_type: str = "SUBTRACTIVE", decimals: int = 4, models: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Call MKF's gap solver and return only the selected physical gap."""
        material_name = self._material_from_core(core)
        model = (models or {}).get("reluctance", "ZHANG")
        if not self.available:
            return self._unavailable("gap_for_inductance", material=material_name)
        try:
            resolved_core, resolved_material = self._resolve_core(core)
            resolved_core = self._module.calculate_core_data(resolved_core, False)
            resolved_coil = self._resolve_coil(coil)
            result = self._module.calculate_gapping_from_number_turns_and_inductance(resolved_core, resolved_coil, inputs, gapping_type, int(decimals), {"reluctance": model})
            fd = result.get("functionalDescription", {})
            gaps = [{"type": item.get("type"), "length_m": _number(item.get("length"))} for item in fd.get("gapping", []) if isinstance(item, Mapping)]
            if not gaps:
                raise ValueError("第三方结果没有返回气隙，不能静默视为零。")
            return self._ok("gap_for_inductance", gaps, "m", model=f"calculate_gapping_from_number_turns_and_inductance:{model}", material=resolved_material, details={"gapping_type": gapping_type, "decimals": int(decimals)})
        except Exception as exc:
            return self._failed("gap_for_inductance", {"code": "GAP_SOLVER_FAILED", "message": f"{type(exc).__name__}: {exc}"}, material=material_name, model=str(model))

    def calculate_core_losses(self, core: Mapping[str, Any], coil: Mapping[str, Any], inputs: Mapping[str, Any], models: Mapping[str, Any]) -> dict[str, Any]:
        material_name = self._material_from_core(core)
        model = models.get("coreLosses", "IGSE")
        if not self.available:
            return self._unavailable("core_losses", material=material_name)
        try:
            resolved_core, resolved_material = self._resolve_core(core)
            resolved_coil = self._resolve_coil(coil)
            output = self._module.calculate_core_losses(resolved_core, resolved_coil, self._inputs_value(inputs), dict(models))
            value = _number(output.get("coreLosses"))
            if value is None:
                raise ValueError("第三方结果缺少 coreLosses，不能转换为零。")
            details = {"magnetic_flux_density_peak_t": _number(output.get("magneticFluxDensityPeak")), "magnetic_flux_density_ac_peak_t": _number(output.get("magneticFluxDensityAcPeak")), "voltage_rms_v": _number(output.get("voltageRms")), "current_rms_a": _number(output.get("currentRms")), "maximum_core_temperature_c": _number(output.get("maximumCoreTemperature")), "temperature_rise_k": _number(output.get("maximumCoreTemperatureRise"))}
            return self._ok("core_losses", value, "W", model=f"calculate_core_losses:{model}", material=resolved_material, details=details)
        except Exception as exc:
            return self._failed("core_losses", {"code": "CORE_LOSSES_FAILED", "message": f"{type(exc).__name__}: {exc}"}, material=material_name, model=str(model))

    def calculate_ohmic_losses(self, coil: Mapping[str, Any], operating_point: Mapping[str, Any], temperature_c: float = 25.0) -> dict[str, Any]:
        if not self.available:
            return self._unavailable("ohmic_losses")
        try:
            resolved_coil = self._resolve_coil(coil)
            output = self._module.calculate_ohmic_losses(resolved_coil, operating_point, float(temperature_c))
            value = _number(output.get("windingLosses"))
            if value is None:
                raise ValueError("第三方结果缺少 windingLosses，不能转换为零。")
            return self._ok("ohmic_losses", value, "W", model="calculate_ohmic_losses", details={"temperature_c": float(temperature_c)})
        except Exception as exc:
            return self._failed("ohmic_losses", {"code": "OHMIC_LOSSES_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def calculate_winding_losses(self, magnetic: Mapping[str, Any], operating_point: Mapping[str, Any], temperature_c: float = 25.0) -> dict[str, Any]:
        if not self.available:
            return self._unavailable("winding_losses")
        try:
            resolved_core, material_name = self._resolve_core(magnetic["core"])
            # MKF requires effective core parameters for field and winding-loss
            # calculations.  Keep this preprocessing inside the provider so the
            # caller never needs to know about a third-party lifecycle step.
            resolved_core = self._module.calculate_core_data(resolved_core, False)
            resolved_coil = self._resolve_coil(magnetic["coil"])
            output = self._module.calculate_winding_losses({"core": resolved_core, "coil": resolved_coil}, operating_point, float(temperature_c))
            value = _number(output.get("windingLosses"))
            if value is None:
                raise ValueError("第三方结果缺少 windingLosses，不能转换为零。")
            per_winding = []
            for item in output.get("windingLossesPerWinding", []) or []:
                if not isinstance(item, Mapping):
                    continue
                normalized = {"name": item.get("name")}
                for key, result_key in (("ohmic_w", "ohmicLosses"), ("skin_w", "skinEffectLosses"), ("proximity_w", "proximityEffectLosses")):
                    component = item.get(result_key)
                    normalized[key] = _loss_value(component)
                per_winding.append(normalized)
            return self._ok("winding_losses", value, "W", model="calculate_winding_losses", material=material_name, details={"temperature_c": float(temperature_c), "per_winding_w": per_winding})
        except Exception as exc:
            return self._failed("winding_losses", {"code": "WINDING_LOSSES_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def calculate_skin_effect_losses(self, coil: Mapping[str, Any], operating_point: Mapping[str, Any], temperature_c: float = 25.0) -> dict[str, Any]:
        """Run MKF's standalone skin-loss step without exposing its accumulator."""
        if not self.available:
            return self._unavailable("skin_effect_losses")
        try:
            resolved_coil = self._resolve_coil(coil)
            ohmic = self._module.calculate_ohmic_losses(resolved_coil, operating_point, float(temperature_c))
            output = self._module.calculate_skin_effect_losses(resolved_coil, ohmic, float(temperature_c))
            value = _loss_value(output.get("skinEffectLosses"))
            aggregation_scope = "top_level"
            component_count = None
            if value is None:
                value, component_count = _sum_turn_loss_components(output, "skinEffectLosses")
                aggregation_scope = "windingLossesPerTurn"
            if value is None:
                raise ValueError("第三方结果缺少 skinEffectLosses，不能转换为零。")
            return self._ok("skin_effect_losses", value, "W", model="calculate_skin_effect_losses", details={"temperature_c": float(temperature_c), "aggregation_scope": aggregation_scope, "component_count": component_count})
        except Exception as exc:
            return self._failed("skin_effect_losses", {"code": "SKIN_LOSSES_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def calculate_proximity_effect_losses(self, magnetic: Mapping[str, Any], operating_point: Mapping[str, Any], temperature_c: float = 25.0) -> dict[str, Any]:
        """Run MKF's field-dependent proximity-loss path."""
        if not self.available:
            return self._unavailable("proximity_effect_losses")
        try:
            resolved_core, material_name = self._resolve_core(magnetic["core"])
            resolved_core = self._module.calculate_core_data(resolved_core, False)
            resolved_coil = self._resolve_coil(magnetic["coil"])
            ohmic = self._module.calculate_ohmic_losses(resolved_coil, operating_point, float(temperature_c))
            skin = self._module.calculate_skin_effect_losses(resolved_coil, ohmic, float(temperature_c))
            field = self._module.calculate_magnetic_field_strength_field(operating_point, {"core": resolved_core, "coil": resolved_coil})
            output = self._module.calculate_proximity_effect_losses(resolved_coil, float(temperature_c), skin, field)
            value = _loss_value(output.get("proximityEffectLosses"))
            aggregation_scope = "top_level"
            component_count = None
            if value is None:
                value, component_count = _sum_turn_loss_components(output, "proximityEffectLosses")
                aggregation_scope = "windingLossesPerTurn"
            if value is None:
                raise ValueError("第三方结果缺少 proximityEffectLosses，不能转换为零。")
            return self._ok("proximity_effect_losses", value, "W", model="calculate_proximity_effect_losses", material=material_name, details={"temperature_c": float(temperature_c), "aggregation_scope": aggregation_scope, "component_count": component_count})
        except Exception as exc:
            return self._failed("proximity_effect_losses", {"code": "PROXIMITY_LOSSES_FAILED", "message": f"{type(exc).__name__}: {exc}"})

    def wind(self, coil: Mapping[str, Any]) -> dict[str, Any]:
        if not self.available:
            return self._unavailable("winding_geometry")
        try:
            resolved = self._resolve_coil(coil)
            functional = resolved.get("functionalDescription", [])
            return self._ok("winding_geometry", {"winding_blocks": [{"name": item.get("name"), "number_turns": item.get("numberTurns"), "number_parallels": item.get("numberParallels"), "wire": (item.get("wire") or {}).get("name")} for item in functional], "section_count": len(resolved.get("sectionsDescription", [])), "layer_count": len(resolved.get("layersDescription", [])), "turn_count": len(resolved.get("turnsDescription", []))}, None, model="wind")
        except Exception as exc:
            return self._failed("winding_geometry", {"code": "WINDING_FAILED", "message": f"{type(exc).__name__}: {exc}"})
