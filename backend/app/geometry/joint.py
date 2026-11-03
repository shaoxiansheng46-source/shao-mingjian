"""Independent OpenMagnetics joint-calculation entry point for Phase 3."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .mas_geometry import MasGeometryAdapter, UnsupportedGeometryError, validate_mas_geometry
from .models import LayoutGeometry


def _skipped(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "value": None,
        "unit": None,
        "model": "not_executed",
        "errors": [{"code": code, "message": message, "severity": "error"}],
    }


def _has_waveforms(operating_point: Mapping[str, Any] | None) -> bool:
    if not isinstance(operating_point, Mapping):
        return False
    excitations = operating_point.get("excitationsPerWinding", operating_point.get("excitations_per_winding"))
    if not isinstance(excitations, list) or not excitations:
        return False
    for excitation in excitations:
        if not isinstance(excitation, Mapping):
            return False
        if not excitation.get("voltage") and not excitation.get("voltage_waveform"):
            return False
        if not excitation.get("current") and not excitation.get("current_waveform"):
            return False
    return True


def _excitation_binding_error(magnetic: Mapping[str, Any], operating_point: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Reject a waveform set that cannot bind to the exported electrical windings.

    PSP keeps P1/S/P2 as physical geometry, but exports one electrical Primary
    winding and one electrical Secondary winding.  Accepting P1/S/P2 here
    would let a caller silently apply the wrong voltage or make MKF select one
    half of the primary for the magnetizing calculation.
    """

    if not isinstance(operating_point, Mapping):
        return None
    excitations = operating_point.get("excitationsPerWinding", operating_point.get("excitations_per_winding"))
    if not isinstance(excitations, list) or not excitations:
        return None
    coil = magnetic.get("coil")
    functional = coil.get("functionalDescription") if isinstance(coil, Mapping) else None
    expected = [item.get("name") for item in functional if isinstance(item, Mapping)] if isinstance(functional, list) else []
    actual = [item.get("name") for item in excitations if isinstance(item, Mapping)]
    if actual != expected:
        return {
            "code": "WINDING_EXCITATION_BINDING_MISMATCH",
            "message": f"工况激励绕组 {actual} 无法绑定到 MAS 电气绕组 {expected}；PSP 的 P1/P2 必须作为同一串联 Primary 输入。",
            "expected": expected,
            "actual": actual,
            "severity": "error",
        }
    return None


class JointCalculationService:
    """Map one layout to MAS and run only the requested real-provider calls."""

    service_version = "sst-phase3-joint-service-0.1.0"

    def __init__(self, provider: Any, adapter: MasGeometryAdapter | None = None):
        self.provider = provider
        self.adapter = adapter or MasGeometryAdapter()

    def calculate(
        self,
        layout: LayoutGeometry,
        *,
        operating_point: Mapping[str, Any] | None = None,
        inputs: Mapping[str, Any] | None = None,
        models: Mapping[str, Any] | None = None,
        temperature_c: float = 25.0,
    ) -> dict[str, Any]:
        models = dict(models or {"reluctance": "ZHANG", "coreLosses": "IGSE", "coreTemperature": "MANIKTALA"})
        base = {
            "service": "JointCalculationService",
            "service_version": self.service_version,
            "layout_status": layout.status,
            "geometry_version": layout.geometry_version,
            "provenance": layout.provenance,
            "warnings": list(layout.warnings),
        }
        if not layout.feasible:
            return {
                **base,
                "status": "infeasible",
                "model_status": "geometry_only",
                "geometry": layout.as_dict(),
                "mas": None,
                "calculations": {},
                "errors": [item.as_dict() for item in layout.violations],
            }
        try:
            magnetic = self.adapter.to_magnetic(layout)
        except UnsupportedGeometryError as exc:
            return {
                **base,
                "status": "unsupported",
                "model_status": "unsupported",
                "geometry": layout.as_dict(),
                "mas": None,
                "calculations": {},
                "errors": [{"code": "UNSUPPORTED_GEOMETRY", "message": str(exc), "severity": "error"}],
            }
        validation = validate_mas_geometry(magnetic, layout)
        if not validation["valid"]:
            return {
                **base,
                "status": "invalid_mapping",
                "model_status": "geometry_only",
                "geometry": layout.as_dict(),
                "mas": magnetic,
                "mas_validation": validation,
                "calculations": {},
                "errors": validation["errors"],
            }
        binding_error = _excitation_binding_error(magnetic, operating_point)
        if binding_error:
            return {
                **base,
                "status": "input_invalid",
                "model_status": "geometry_only",
                "geometry": layout.as_dict(),
                "mas": magnetic,
                "mas_validation": validation,
                "calculations": {},
                "errors": [binding_error],
            }
        calculations: dict[str, Any] = {
            "native": {
                "geometry": {
                    "volume_m3": layout.volume_m3,
                    "mass_kg": layout.mass_kg,
                    "block_resistance_ohm": {item.name: item.resistance_ohm for item in layout.blocks},
                    "mean_turn_length_m": {item.name: item.mean_turn_length_m for item in layout.blocks},
                },
                "model": "sst_parameterized_geometry_only",
                "note": "本阶段未把自研几何估算冒充 OpenMagnetics 损耗结果。",
            },
            "openmagnetics": {},
            "comparison": {},
        }
        calculations["openmagnetics"]["core_data"] = self.provider.calculate_core_data(magnetic["core"])
        if isinstance(operating_point, Mapping):
            calculations["openmagnetics"]["magnetizing_inductance"] = self.provider.calculate_inductance(
                magnetic["core"], magnetic["coil"], operating_point, models
            )
        else:
            calculations["openmagnetics"]["magnetizing_inductance"] = _skipped("MISSING_OPERATING_POINT", "缺少 operating_point，未执行励磁电感计算。")
        if not _has_waveforms(operating_point):
            missing = _skipped("MISSING_WAVEFORM", "缺少完整端电压/端电流波形，未执行损耗计算；不能由直流母线电压推造波形。")
            calculations["openmagnetics"]["core_losses"] = missing
            calculations["openmagnetics"]["winding_losses"] = missing
            calculations["openmagnetics"]["ohmic_losses"] = missing
            status = "geometry_and_inductance" if calculations["openmagnetics"]["magnetizing_inductance"].get("status") == "ok" else "geometry_only"
        else:
            calculations["openmagnetics"]["core_losses"] = self.provider.calculate_core_losses(magnetic["core"], magnetic["coil"], inputs or {}, models)
            calculations["openmagnetics"]["winding_losses"] = self.provider.calculate_winding_losses(magnetic, operating_point, temperature_c)
            calculations["openmagnetics"]["ohmic_losses"] = self.provider.calculate_ohmic_losses(magnetic["coil"], operating_point, temperature_c)
            status = "ok"
        geometry_call = self.provider.wind(magnetic["coil"])
        calculations["openmagnetics"]["geometry_call"] = geometry_call
        values = calculations["openmagnetics"]
        if values.get("core_data", {}).get("status") != "ok":
            status = "geometry_only" if status == "ok" else status
        calculation_errors = []
        for name, value in values.items():
            if isinstance(value, Mapping) and value.get("status") in {"error", "unavailable"}:
                calculation_errors.append({"calculation": name, "errors": value.get("errors", [])})
        if calculation_errors:
            status = "partial" if any(value.get("status") == "ok" for value in values.values() if isinstance(value, Mapping)) else "calculation_failed"
        return {
            **base,
            "status": status,
            "model_status": "openmagnetics_joint_reference",
            "geometry": layout.as_dict(),
            "mas": magnetic,
            "mas_validation": validation,
            "calculations": calculations,
            "models": models,
            "temperature_c": float(temperature_c),
            "errors": calculation_errors,
            "traceability": {
                "third_party": "OpenMagnetics via Phase 2 OpenMagneticsProvider",
                "provider_status": self.provider.status(),
                "input_waveforms_used": _has_waveforms(operating_point),
                "engineering_approved": False,
            },
        }
