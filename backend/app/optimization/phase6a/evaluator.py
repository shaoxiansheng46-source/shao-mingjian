"""Phase 6A candidate evaluation, cache and complete audit ledger."""

from __future__ import annotations

import copy
import time
from dataclasses import replace
from math import isfinite
from typing import Any, Mapping

from ...evaluation import EvaluationContext, UnifiedEvaluationService, canonical_hash
from ...geometry import JointCalculationService
from ...winding_loss import WindingLossService
from .builder import CandidateBuilder
from .case import PhysicalDesignCase
from .models import DesignVariableSpace, Phase6AConfig


class Phase6AEvaluator:
    """The only path from an optimizer individual to physical performance."""

    def __init__(
        self,
        case: PhysicalDesignCase,
        variable_space: DesignVariableSpace,
        config: Phase6AConfig | None = None,
        *,
        evaluation_service: UnifiedEvaluationService | None = None,
    ):
        self.case = case
        self.variable_space = variable_space
        self.config = config or Phase6AConfig()
        self.builder = CandidateBuilder(case, variable_space)
        self.service = evaluation_service or UnifiedEvaluationService(
            winding_loss_service=WindingLossService(case.provider if case.provider and case.provider.available else None),
            joint_service=JointCalculationService(case.provider) if case.provider is not None else None,
        )
        self.records: list[dict[str, Any]] = []
        self.unique_records: dict[str, dict[str, Any]] = {}
        self.cache: dict[str, dict[str, Any]] = {}
        self.started_at = time.monotonic()
        self.cancel_event: Any | None = None
        self.progress_callback: Any | None = None
        self.constraint_ids = self._constraint_ids()

    def _constraint_ids(self) -> list[str]:
        ids = ["turns_ratio"]
        if self.config.bmax_max_t is not None:
            ids.append("bmax")
        if self.config.lm_min_h is not None:
            ids.append("lm_min")
        if self.config.lm_max_h is not None:
            ids.append("lm_max")
        if self.config.leakage_target_h is not None:
            ids.extend(["leakage_lower", "leakage_upper"])
        return ids

    @property
    def constraint_count(self) -> int:
        return len(self.constraint_ids)

    def attach_controls(self, *, cancel_event: Any | None = None, progress_callback: Any | None = None) -> None:
        self.cancel_event = cancel_event
        self.progress_callback = progress_callback

    def should_stop(self) -> str | None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            return "cancelled"
        if self.config.timeout_s is not None and time.monotonic() - self.started_at > self.config.timeout_s:
            return "timeout"
        return None

    @staticmethod
    def _metric(mapping: Any, *path: str) -> float | None:
        value = mapping
        for key in path:
            if not isinstance(value, Mapping):
                return None
            value = value.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if isfinite(number) else None

    def _failure_record(self, build: Any, status: str, diagnostics: list[dict[str, Any]], *, cache_key: str) -> dict[str, Any]:
        invalid = float(self.config.invalid_objective_value)
        unknown = float(self.config.unknown_constraint_sentinel)
        return {
            "status": status,
            "cache_hit": False,
            "variables": dict(build.variables),
            "candidate_hash": build.candidate_hash,
            "evaluation_key": cache_key,
            "objectives": [invalid, invalid],
            "objective_names": ["total_electromagnetic_loss_W", "winding_envelope_volume_m3"],
            "constraints": [{"id": name, "value": None, "residual": unknown, "status": "unknown"} for name in self.constraint_ids],
            "constraint_vector": [unknown] * self.constraint_count,
            "geometry_feasible": False,
            "research_feasible": False,
            "engineering_status": "UNKNOWN",
            "engineering_approved": False,
            "diagnostics": diagnostics,
            "candidate_snapshot": build.candidate.as_dict() if build.candidate else None,
            "layout_snapshot": build.layout.as_dict() if build.layout is not None else None,
            "evaluation_result": None,
            "elapsed_s": 0.0,
            "model_version": self.config.model_version,
            "provenance": dict(self.case.data_snapshot),
        }

    def _research_constraints(self, variables: Mapping[str, Any], result: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[float], list[str]]:
        summary = result.get("_phase6a_metrics", {}) if isinstance(result, Mapping) else {}
        ratio = float(variables["Np"]) / float(variables["Ns"])
        rows: list[dict[str, Any]] = []
        vector: list[float] = []
        unknown: list[str] = []

        def add(name: str, value: float | None, residual: float | None, unit: str | None = None) -> None:
            if value is None or residual is None or not isfinite(float(residual)):
                rows.append({"id": name, "value": value, "residual": self.config.unknown_constraint_sentinel, "status": "unknown", "unit": unit})
                vector.append(float(self.config.unknown_constraint_sentinel))
                unknown.append(name)
            else:
                residual_f = float(residual)
                rows.append({"id": name, "value": float(value), "residual": residual_f, "status": "pass" if residual_f <= 0 else "fail", "unit": unit})
                vector.append(residual_f)

        target = self.config.turns_ratio_target
        if target is None:
            add("turns_ratio", ratio, -1.0, "ratio")
        else:
            add("turns_ratio", ratio, abs(ratio - target) - self.config.turns_ratio_tolerance, "ratio")
        bmax = summary.get("bmax_t")
        if self.config.bmax_max_t is not None:
            add("bmax", bmax, None if bmax is None else bmax - self.config.bmax_max_t, "T")
        lm = summary.get("lm_h")
        if self.config.lm_min_h is not None:
            add("lm_min", lm, None if lm is None else self.config.lm_min_h - lm, "H")
        if self.config.lm_max_h is not None:
            add("lm_max", lm, None if lm is None else lm - self.config.lm_max_h, "H")
        if self.config.leakage_target_h is not None:
            leakage = summary.get("leakage_h")
            lower = self.config.leakage_target_h * (1.0 - self.config.leakage_relative_tolerance)
            upper = self.config.leakage_target_h * (1.0 + self.config.leakage_relative_tolerance)
            add("leakage_lower", leakage, None if leakage is None else lower - leakage, "H")
            add("leakage_upper", leakage, None if leakage is None else leakage - upper, "H")
        return rows, vector, unknown

    def _make_record(self, build: Any, *, cache_key: str) -> dict[str, Any]:
        started = time.monotonic()
        if build.status in {"invalid_variables", "unsupported"}:
            return self._failure_record(build, build.status, build.violations, cache_key=cache_key)
        if not build.layout.feasible:
            return self._failure_record(build, "geometry_infeasible", build.violations, cache_key=cache_key) | {
                "geometry_feasible": False,
                "layout_snapshot": build.layout.as_dict(),
            }
        if self.case.requires_external_provider and (self.case.provider is None or not self.case.provider.available):
            return self._failure_record(build, "provider_unavailable", [{"code": "OPENMAGNETICS_UNAVAILABLE", "message": "本算例要求真实 OpenMagnetics Provider；没有使用 synthetic 回退。", "severity": "error"}], cache_key=cache_key) | {
                "geometry_feasible": True,
                "layout_snapshot": build.layout.as_dict(),
            }

        provider_inputs = copy.deepcopy(dict(self.case.provider_inputs))
        design_requirements = copy.deepcopy(dict(provider_inputs.get("designRequirements", {})))
        design_requirements["turnsRatios"] = [{"nominal": float(build.variables["Np"]) / float(build.variables["Ns"])}]
        provider_inputs["designRequirements"] = design_requirements
        context = replace(self.case.context, seed=self.config.seed)
        result = self.service.evaluate(
            build.candidate,
            self.case.operating_point,
            context=context,
            leakage_model="native_sectional",
            winding_model="comparison" if self.case.requires_external_provider else "native_dc",
            include_openmagnetics=self.case.requires_external_provider,
            temperature_c=self.case.operating_point.ambient_c,
            provider_inputs=provider_inputs,
        )
        joint = result.get("openmagnetics", {}).get("calculations", {}).get("openmagnetics", {}) if isinstance(result.get("openmagnetics"), Mapping) else {}
        pcore = self._metric(joint, "core_losses", "value")
        lm = self._metric(joint, "magnetizing_inductance", "value")
        bmax = self._metric(joint, "core_losses", "details", "magnetic_flux_density_peak_t")
        winding = result.get("losses", {}).get("winding", {}) if isinstance(result.get("losses"), Mapping) else {}
        complete = winding.get("openmagnetics_full", {}) if isinstance(winding, Mapping) else {}
        pcu = self._metric(complete, "value")
        leakage = self._metric(result, "electromagnetic", "leakage", "value")
        metrics = {"pcore_w": pcore, "pcu_complete_w": pcu, "lm_h": lm, "bmax_t": bmax, "leakage_h": leakage}
        physical_ok = all(value is not None for value in (pcore, pcu, lm, bmax))
        diagnostics = list(result.get("diagnostics", [])) if isinstance(result.get("diagnostics"), list) else []
        if not physical_ok:
            diagnostics.append({"code": "PHYSICAL_METRIC_INCOMPLETE", "message": "核心损耗、完整 MKF 绕组损耗、励磁电感或磁密缺少有效值；未生成可行 Pareto 解。", "severity": "error"})
        result["_phase6a_metrics"] = metrics
        constraints, vector, unknown = self._research_constraints(build.variables, result)
        research_feasible = physical_ok and not unknown and all(value <= 0 for value in vector)
        status = "research_feasible" if research_feasible else ("physical_success_research_infeasible" if physical_ok else "physical_failed")
        volume = build.layout.volume_m3
        objective = [pcore + pcu, float(volume)] if physical_ok and volume is not None else [self.config.invalid_objective_value, self.config.invalid_objective_value]
        return {
            "status": status,
            "cache_hit": False,
            "variables": dict(build.variables),
            "candidate_hash": build.candidate_hash,
            "excitation_hash": canonical_hash(self.case.operating_point.as_dict()),
            "evaluation_key": cache_key,
            "objectives": objective,
            "objective_names": ["total_electromagnetic_loss_W", "winding_envelope_volume_m3"],
            "constraints": constraints,
            "constraint_vector": vector,
            "unknown_constraints": unknown,
            "geometry_feasible": True,
            "research_feasible": research_feasible,
            "engineering_status": "UNKNOWN",
            "engineering_approved": False,
            "diagnostics": diagnostics,
            "candidate_snapshot": build.candidate.as_dict(),
            "layout_snapshot": build.layout.as_dict(),
            "evaluation_result": result,
            "metrics": metrics,
            "elapsed_s": time.monotonic() - started,
            "model_version": self.config.model_version,
            "provenance": dict(self.case.data_snapshot),
        }

    def evaluate(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Evaluate one individual; every call is recorded, including cache hits."""

        stop = self.should_stop()
        plain_values = {str(key): item.item() if hasattr(item, "item") else item for key, item in values.items()}
        raw_key = canonical_hash({"values": plain_values, "snapshot": self.case.data_snapshot, "config": self.config.as_dict()})
        if stop:
            record = self._failure_record(type("B", (), {"variables": dict(values), "candidate": None, "layout": None, "candidate_hash": raw_key, "violations": []})(), stop, [{"code": stop.upper(), "message": f"优化在评估前{stop}。", "severity": "warning"}], cache_key=raw_key)
        else:
            build = self.builder.build(values)
            cache_key = canonical_hash({"candidate_hash": build.candidate_hash, "excitation_hash": canonical_hash(self.case.operating_point.as_dict()), "model_version": self.config.model_version, "config": self.config.as_dict()})
            if cache_key in self.cache:
                record = copy.deepcopy(self.cache[cache_key])
                record["cache_hit"] = True
            elif len(self.records) >= self.config.max_evaluations:
                record = self._failure_record(build, "budget_exhausted", [{"code": "MAX_EVALUATIONS_REACHED", "message": "已达到本次优化的计算预算。", "severity": "warning"}], cache_key=cache_key)
            else:
                record = self._make_record(build, cache_key=cache_key)
                self.cache[cache_key] = copy.deepcopy(record)
                self.unique_records[cache_key] = copy.deepcopy(record)
        record["evaluation_index"] = len(self.records)
        self.records.append(record)
        if self.progress_callback is not None:
            self.progress_callback(self)
        return record

    def summary(self) -> dict[str, Any]:
        unique = list(self.unique_records.values())
        return {
            "total_evaluations": len(self.records),
            "unique_candidates": len(unique),
            "cache_hits": sum(1 for item in self.records if item.get("cache_hit")),
            "successful_physical": sum(1 for item in unique if item.get("status") in {"research_feasible", "physical_success_research_infeasible"}),
            "geometry_rejected": sum(1 for item in unique if item.get("status") == "geometry_infeasible"),
            "physical_failures": sum(1 for item in unique if item.get("status") in {"physical_failed", "provider_unavailable"}),
            "research_feasible": sum(1 for item in unique if item.get("research_feasible")),
            "engineering_unknown": sum(1 for item in unique if item.get("engineering_status") == "UNKNOWN"),
        }
