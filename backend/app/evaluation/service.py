"""Phase 5A orchestration for one candidate and one excitation snapshot.

This module is intentionally an adapter/composition layer.  It does not copy
the legacy evaluator, change the NSGA-II implementation, or provide a hidden
thermal fallback.  Every child calculation receives the same ``LayoutGeometry``
and the same ``OperatingPointSnapshot``; hashes in the result make accidental
cross-task mixing visible.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from ..geometry import JointCalculationService
from ..leakage import LeakageInductanceService
from ..winding_loss import WindingLossService
from .models import EvaluationCandidate, EvaluationContext, OperatingPointSnapshot, canonical_hash, canonical_payload


MODEL_VERSION = "sst-phase5a-unified-evaluation-0.1.0"
_PRIMARY_ROLES = {"primary", "p", "原边"}
_SECONDARY_ROLES = {"secondary", "s", "副边"}


def _diagnostic(code: str, message: str, *, field: str | None = None, severity: str = "error") -> dict[str, Any]:
    return {"code": code, "message": message, "field": field, "severity": severity}


def _status_from_children(*statuses: str) -> str:
    if any(status in {"error", "input_invalid", "infeasible", "unsupported"} for status in statuses):
        return "partial"
    if all(status in {"ok", "not_requested"} for status in statuses):
        return "ok"
    return "partial"


class UnifiedEvaluationService:
    """Evaluate a candidate through existing domain services without optimizing."""

    service_version = MODEL_VERSION

    def __init__(
        self,
        *,
        leakage_service: LeakageInductanceService | None = None,
        winding_loss_service: WindingLossService | None = None,
        joint_service: JointCalculationService | None = None,
    ):
        self.leakage_service = leakage_service or LeakageInductanceService()
        self.winding_loss_service = winding_loss_service or WindingLossService()
        self.joint_service = joint_service

    @staticmethod
    def _electrical_name(layout: Any, block: Any) -> str:
        if layout.template.template_id == "PSP" and block.role.lower() in _PRIMARY_ROLES:
            return "Primary"
        if layout.template.template_id == "PSP" and block.role.lower() in _SECONDARY_ROLES:
            return "Secondary"
        return block.name

    @staticmethod
    def _result_grade(candidate: EvaluationCandidate, context: EvaluationContext) -> str:
        provenance = dict(candidate.layout.provenance)
        if provenance.get("synthetic") or provenance.get("demo_only") or provenance.get("data_status") == "synthetic":
            return "demo_only"
        if context.provider == "openmagnetics":
            return "reference_only"
        return "hybrid_unqualified"

    @staticmethod
    def _candidate_hash(candidate: EvaluationCandidate) -> str:
        return canonical_hash({
            "layout": candidate.layout.as_dict(),
            "wire_specs": {str(key): value.as_dict() for key, value in sorted(candidate.wire_specs.items())},
            "record_ids": candidate.record_ids,
        })

    @staticmethod
    def _current_value(mapping: Mapping[str, Any], layout: Any, block: Any) -> float | None:
        aliases = [block.name, block.winding]
        if block.role.lower() in _PRIMARY_ROLES:
            aliases += ["Primary", "primary", "P"]
        elif block.role.lower() in _SECONDARY_ROLES:
            aliases += ["Secondary", "secondary", "S"]
        for alias in aliases:
            if alias in mapping:
                try:
                    return float(mapping[alias])
                except (TypeError, ValueError):
                    return None
        lowered = {str(key).lower(): value for key, value in mapping.items()}
        for alias in aliases:
            if str(alias).lower() in lowered:
                try:
                    return float(lowered[str(alias).lower()])
                except (TypeError, ValueError):
                    return None
        return None

    def _validate_current_snapshot(
        self,
        candidate: EvaluationCandidate,
        operating_point: OperatingPointSnapshot,
        winding_result: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        windings = winding_result.get("windings", {})
        for block in candidate.layout.blocks:
            supplied = self._current_value(operating_point.currents_rms_a, candidate.layout, block)
            if supplied is None:
                diagnostics.append(_diagnostic("MISSING_SIGNED_CURRENT", f"缺少 {block.name} 的有符号 RMS 电流。", field=f"currents_rms_a.{block.name}"))
                continue
            if not isfinite(supplied) or supplied == 0:
                diagnostics.append(_diagnostic("INVALID_SIGNED_CURRENT", f"{block.name} 的有符号 RMS 电流必须为有限非零值。", field=f"currents_rms_a.{block.name}"))
                continue
            calculated = windings.get(block.name, {}).get("current_rms_a") if isinstance(windings.get(block.name), Mapping) else None
            if calculated is None:
                continue
            if abs(abs(supplied) - float(calculated)) > max(1e-7, abs(float(calculated)) * 0.02):
                diagnostics.append(_diagnostic(
                    "CURRENT_WAVEFORM_RMS_MISMATCH",
                    f"{block.name} 的显式 RMS={supplied:.9g} A 与同一快照波形计算 RMS={float(calculated):.9g} A 不一致；未强行覆盖。",
                    field=f"currents_rms_a.{block.name}",
                ))
        return diagnostics

    @staticmethod
    def _constraint_report(candidate: EvaluationCandidate, context: EvaluationContext, leakage: Mapping[str, Any], winding: Mapping[str, Any]) -> dict[str, Any]:
        constraints: list[dict[str, Any]] = []
        limits = context.constraints
        volume_limit = limits.get("volume_max_m3")
        if volume_limit is not None and candidate.layout.volume_m3 is not None:
            value = float(candidate.layout.volume_m3)
            limit = float(volume_limit)
            constraints.append({"id": "geometry.volume", "value": value, "limit": limit, "residual": value - limit, "status": "pass" if value <= limit else "fail", "unit": "m3"})
        mass_limit = limits.get("mass_max_kg")
        if mass_limit is not None and candidate.layout.mass_kg is not None:
            value = float(candidate.layout.mass_kg)
            limit = float(mass_limit)
            constraints.append({"id": "geometry.mass", "value": value, "limit": limit, "residual": value - limit, "status": "pass" if value <= limit else "fail", "unit": "kg"})

        density_limits = limits.get("current_density_A_per_mm2", {})
        for block in candidate.layout.blocks:
            item = winding.get("windings", {}).get(block.name, {})
            spec = candidate.wire_specs.get(block.name) or candidate.wire_specs.get("Primary" if block.role.lower() in _PRIMARY_ROLES else "Secondary")
            area = spec.bare_copper_area_m2 if spec is not None else None
            current = item.get("current_rms_a")
            if area is None or not area or current is None:
                continue
            density = float(current) / (area * max(block.parallels, 1)) * 1e-6
            key = "primary_max" if block.role.lower() in _PRIMARY_ROLES else "secondary_max"
            limit = density_limits.get(key)
            if limit is None:
                continue
            constraints.append({"id": f"current_density.{block.name}", "value": density, "limit": float(limit), "residual": density - float(limit), "status": "pass" if density <= float(limit) else "fail", "unit": "A/mm2"})

        leakage_limit = limits.get("series_inductance_H")
        if leakage_limit and leakage.get("status") == "ok":
            target = leakage_limit.get("target") if isinstance(leakage_limit, Mapping) else None
            tolerance = leakage_limit.get("relative_tolerance") if isinstance(leakage_limit, Mapping) else None
            if target is not None and tolerance is not None:
                value = float(leakage["value"])
                lower, upper = float(target) * (1 - float(tolerance)), float(target) * (1 + float(tolerance))
                constraints.append({"id": "series_inductance", "value": value, "limit": [lower, upper], "residual": min(value - lower, upper - value), "status": "pass" if lower <= value <= upper else "fail", "unit": "H"})
        failed = [item for item in constraints if item["status"] == "fail"]
        return {"status": "fail" if failed else "pass", "constraints": constraints, "failed_count": len(failed), "note": "仅评估本次显式提供的结构/电流/漏感约束；热约束未在 Phase 5A 实现。"}

    def evaluate(
        self,
        candidate: EvaluationCandidate,
        operating_point: OperatingPointSnapshot,
        *,
        context: EvaluationContext | None = None,
        leakage_model: str = "native_sectional",
        winding_model: str = "native_dc",
        include_openmagnetics: bool = False,
        temperature_c: float | None = None,
    ) -> dict[str, Any]:
        """Evaluate one candidate without changing the optimizer or UI state."""

        context = context or EvaluationContext(data_snapshot=candidate.data_snapshot)
        candidate_hash = self._candidate_hash(candidate)
        excitation_hash = canonical_hash(operating_point.as_dict())
        evaluation_key = canonical_hash({
            "candidate_hash": candidate_hash,
            "excitation_hash": excitation_hash,
            "context": context.as_dict(),
            "leakage_model": leakage_model,
            "winding_model": winding_model,
            "include_openmagnetics": include_openmagnetics,
        })
        result: dict[str, Any] = {
            "status": "infeasible" if not candidate.layout.feasible else "partial",
            "candidate_id": candidate.candidate_id or f"unified-{candidate_hash[:12]}",
            "candidate_hash": candidate_hash,
            "excitation_hash": excitation_hash,
            "evaluation_key": evaluation_key,
            "service": "UnifiedEvaluationService",
            "service_version": self.service_version,
            "result_grade": self._result_grade(candidate, context),
            "engineering_approved": False,
            "units": "SI",
            "candidate_snapshot": candidate.as_dict(),
            "operating_point_snapshot": operating_point.as_dict(),
            "context": context.as_dict(),
            "capabilities": {
                "geometry": "calculated",
                "leakage": leakage_model,
                "winding_loss": winding_model,
                "core_loss": "not_requested",
                "thermal": "not_implemented",
                "hotspot": "not_available",
                "fringing_loss": "not_modelled",
            },
            "geometry": {
                "status": "ok" if candidate.layout.feasible else "infeasible",
                "model": "phase3_parameterized_geometry",
                "model_version": candidate.layout.geometry_version,
                "value": candidate.layout.feasible,
                "unit": None,
                "data": candidate.layout.as_dict(),
                "diagnostics": [item.as_dict() for item in candidate.layout.violations],
            },
            "electromagnetic": {},
            "losses": {},
            "thermal": {
                "status": "not_implemented",
                "core_C": None,
                "winding_C": None,
                "external_C": None,
                "hotspot_C": None,
                "hotspot_status": "not_available",
                "diagnostics": [_diagnostic("THERMAL_NOT_IN_PHASE5A", "Phase 5A 只编排结构、电磁和绕组损耗；未执行热模型。", severity="warning")],
            },
            "diagnostics": [],
        }
        if canonical_hash(candidate.data_snapshot) != canonical_hash(context.data_snapshot):
            result["status"] = "input_invalid"
            result["diagnostics"].append(_diagnostic(
                "DATA_SNAPSHOT_MISMATCH",
                "候选结构与评估上下文的数据快照不同；为避免混用旧数据，未执行子模型。",
                field="data_snapshot",
            ))
            return result
        if not candidate.layout.feasible:
            result["diagnostics"] = [_diagnostic(item.code, item.message, field=item.field) for item in candidate.layout.violations]
            return result

        temperature = operating_point.ambient_c if temperature_c is None else float(temperature_c)
        waveforms = operating_point.current_waveform_objects()
        winding = self.winding_loss_service.calculate(
            candidate.layout,
            wire_specs=candidate.wire_specs,
            waveforms=waveforms,
            model=winding_model,
            temperature_c=temperature,
        )
        current_diagnostics = self._validate_current_snapshot(candidate, operating_point, winding)
        leakage = self.leakage_service.calculate(
            candidate.layout,
            model=leakage_model,
            currents_rms=operating_point.currents_rms_a,
            reference_port=operating_point.reference_side,
            frequency_hz=operating_point.frequency_hz,
        )
        result["electromagnetic"]["leakage"] = leakage
        result["losses"]["winding"] = winding
        result["constraints"] = self._constraint_report(candidate, context, leakage, winding)
        result["diagnostics"].extend(current_diagnostics)

        if include_openmagnetics:
            if self.joint_service is None:
                result["openmagnetics"] = {
                    "status": "unavailable",
                    "model": "openmagnetics_joint_reference",
                    "value": None,
                    "diagnostics": [_diagnostic("OPENMAGNETICS_SERVICE_NOT_CONFIGURED", "未配置 OpenMagnetics JointCalculationService；没有回退为 synthetic 或零值。")],
                }
            else:
                electrical_names = []
                try:
                    magnetic = self.joint_service.adapter.to_magnetic(candidate.layout)
                    electrical_names = [item["name"] for item in magnetic["coil"]["functionalDescription"]]
                    provider_op, op_diagnostics = operating_point.provider_operating_point(electrical_names)
                    if op_diagnostics:
                        result["openmagnetics"] = {
                            "status": "input_invalid",
                            "model": "openmagnetics_joint_reference",
                            "value": None,
                            "diagnostics": op_diagnostics,
                        }
                    else:
                        result["openmagnetics"] = self.joint_service.calculate(
                            candidate.layout,
                            operating_point=provider_op,
                            inputs={"frequency_hz": operating_point.frequency_hz, "power_w": operating_point.power_w},
                            temperature_c=temperature,
                        )
                except Exception as exc:
                    result["openmagnetics"] = {
                        "status": "error",
                        "model": "openmagnetics_joint_reference",
                        "value": None,
                        "diagnostics": [_diagnostic("OPENMAGNETICS_JOINT_FAILED", f"{type(exc).__name__}: {exc}")],
                    }
        else:
            result["openmagnetics"] = {
                "status": "not_requested",
                "model": "openmagnetics_joint_reference",
                "value": None,
                "diagnostics": [],
            }

        child_statuses = [
            result["geometry"]["status"],
            leakage.get("status", "error"),
            winding.get("status", "error"),
            result["openmagnetics"].get("status", "not_requested"),
        ]
        result["status"] = _status_from_children(*child_statuses)
        if current_diagnostics:
            result["status"] = "input_invalid"
        return canonical_payload(result)
