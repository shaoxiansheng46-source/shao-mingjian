"""Phase 6B HTTP task adapter for the Phase 6A real optimizer.

This module owns request decoding, task lifecycle and export views only. It
does not duplicate candidate generation or physical formulas. The provider is
required to be external; no synthetic data is accepted in this task domain.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .phase6a import DesignVariableSpace, Phase6AConfig, build_external_case, optimize_phase6a
from ..evaluation.models import OperatingPointSnapshot
from ..providers.openmagnetics import OpenMagneticsProvider
from ..winding_loss import CurrentWaveform


PHASE6B_API_VERSION = "sst-phase6b-optimization-workbench-0.1.0"


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def _diagnostic(code: str, message: str, severity: str = "error") -> dict[str, Any]:
    return {"code": code, "message": message, "severity": severity}


def _range(raw: Any, default: tuple[float, float], *, integer: bool = False) -> tuple[int, int] | tuple[float, float]:
    if not isinstance(raw, Mapping):
        raw = {"value": raw} if raw is not None else {}
    optimize = bool(raw.get("optimize", True))
    if not optimize:
        value = raw.get("value", default[0])
        return (int(value), int(value)) if integer else (float(value), float(value))
    low = raw.get("min", default[0])
    high = raw.get("max", default[1])
    return (int(low), int(high)) if integer else (float(low), float(high))


def _choice(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(raw, Mapping):
        raw = {"value": raw} if raw is not None else {}
    if not bool(raw.get("optimize", True)):
        return (str(raw.get("value", default[0])),)
    values = raw.get("choices", default)
    return tuple(str(item) for item in values)


def _step(raw: Any, default: float) -> float:
    if isinstance(raw, Mapping):
        return float(raw.get("step", default))
    return float(default)


def _waveform(name: str, raw: Any, frequency_hz: float) -> CurrentWaveform:
    if not isinstance(raw, Mapping):
        raise ValueError(f"MISSING_WAVEFORM:{name}")
    data = raw.get("data", raw.get("current_a"))
    times = raw.get("time", raw.get("time_s"))
    frequency = raw.get("frequency_hz", raw.get("frequency", frequency_hz))
    if not isinstance(data, list) or not isinstance(times, list) or len(data) != len(times) or len(data) < 4:
        raise ValueError(f"INVALID_WAVEFORM:{name}")
    return CurrentWaveform.from_mapping(name, {"data": data, "time": times, "frequency_hz": frequency})


def _operating_point(payload: Mapping[str, Any]) -> OperatingPointSnapshot:
    raw = payload.get("operating_point") if isinstance(payload.get("operating_point"), Mapping) else {}
    frequency = float(raw.get("frequency_hz", 100_000.0))
    current_raw = raw.get("current_waveforms") if isinstance(raw.get("current_waveforms"), Mapping) else {}
    voltage_raw = raw.get("voltage_waveforms") if isinstance(raw.get("voltage_waveforms"), Mapping) else {}
    currents = raw.get("currents_rms_a") if isinstance(raw.get("currents_rms_a"), Mapping) else {}
    current_waveforms = {
        "Primary": _waveform("Primary", current_raw.get("Primary"), frequency),
        "Secondary": _waveform("Secondary", current_raw.get("Secondary"), frequency),
    }
    for name in ("Primary", "Secondary"):
        value = voltage_raw.get(name)
        if not isinstance(value, Mapping):
            raise ValueError(f"MISSING_VOLTAGE_WAVEFORM:{name}")
        if isinstance(value.get("waveform"), Mapping):
            value = value["waveform"]
        if not isinstance(value.get("data"), list) or not isinstance(value.get("time"), list) or len(value["data"]) != len(value["time"]):
            raise ValueError(f"INVALID_VOLTAGE_WAVEFORM:{name}")
    return OperatingPointSnapshot(
        point_id=str(raw.get("point_id", "phase6b-web")),
        voltage_primary_v=float(raw.get("voltage_primary_v", 100.0)),
        voltage_secondary_v=float(raw.get("voltage_secondary_v", 25.0)),
        power_w=float(raw.get("power_w", 1_000.0)),
        frequency_hz=frequency,
        ambient_c=float(raw.get("ambient_c", 25.0)),
        currents_rms_a={str(key): float(value) for key, value in currents.items()},
        current_waveforms=current_waveforms,
        voltage_waveforms={"Primary": dict(voltage_raw["Primary"]), "Secondary": dict(voltage_raw["Secondary"])},
        topology=str(raw.get("topology", "DAB_SPS")),
        bridge_duty=float(raw.get("bridge_duty", 0.5)),
        reference_side=str(raw.get("reference_side", "primary")),
    )


def build_request_context(payload: Mapping[str, Any], provider: OpenMagneticsProvider) -> tuple[Any, DesignVariableSpace, Phase6AConfig]:
    if str(payload.get("data_source", "external_database")) != "external_database":
        raise ValueError("SYNTHETIC_DATA_BLOCKED_IN_PHASE6B")
    op = _operating_point(payload)
    fixed = payload.get("fixed") if isinstance(payload.get("fixed"), Mapping) else {}
    core = fixed.get("core") if isinstance(fixed.get("core"), Mapping) else {}
    wire = fixed.get("wire") if isinstance(fixed.get("wire"), Mapping) else {}
    primary_wire = str(wire.get("primary_name", "Litz 1000x0.02 - Grade 1 - Double Served"))
    secondary_wire = str(wire.get("secondary_name", primary_wire))
    if primary_wire != secondary_wire:
        raise ValueError("PHASE6B_WIRE_OPTIONS_MUST_SHARE_LOADED_CASE:当前首版请先选择同一真实导线；导线类别优化已由 Phase 6A 保留接口但未扩展多记录加载。")
    case = build_external_case(
        provider,
        shape_name=str(core.get("shape_name", "ETD 54/28/19")),
        material_name=str(core.get("material_name", "3C95")),
        bobbin_name=str(core.get("bobbin_name", "Bobbin ETD 54")),
        wire_name=primary_wire,
        operating_point=op,
    )
    variables = payload.get("variables") if isinstance(payload.get("variables"), Mapping) else {}
    np_bounds = _range(variables.get("Np"), (16, 24), integer=True)
    ns_bounds = _range(variables.get("Ns"), (4, 8), integer=True)
    p1_bounds = _range(variables.get("P1"), (1, max(1, int(np_bounds[1]) - 1)), integer=True)
    gap_bounds = _range(variables.get("interwinding_gap_m"), (0.0004, 0.0015))
    clearance_bounds = _range(variables.get("core_clearance_m"), (0.0003, 0.0012))
    space = DesignVariableSpace(
        np_bounds=np_bounds, ns_bounds=ns_bounds, p1_bounds=p1_bounds,
        interwinding_gap_bounds_m=gap_bounds, core_clearance_bounds_m=clearance_bounds,
        interwinding_gap_step_m=_step(variables.get("interwinding_gap_m"), 0.00005),
        core_clearance_step_m=_step(variables.get("core_clearance_m"), 0.00005),
        layout_choices=_choice(variables.get("layout"), ("PS", "PSP")),
        primary_wire_choices=(primary_wire,), secondary_wire_choices=(secondary_wire,),
    )
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), Mapping) else {}
    optimizer = payload.get("optimizer") if isinstance(payload.get("optimizer"), Mapping) else {}
    population = int(optimizer.get("population_size", 4))
    generations = int(optimizer.get("generations", 2))
    max_evaluations = int(optimizer.get("max_evaluations", population * generations * 2))
    if population < 2 or population > 32 or generations < 1 or generations > 20 or max_evaluations < 1 or max_evaluations > 256:
        raise ValueError("PHASE6B_BUDGET_OUT_OF_RANGE:种群≤32、代数≤20、最大评估≤256。")
    config = Phase6AConfig(
        seed=int(optimizer.get("seed", 20261103)), population_size=population,
        generations=generations, max_evaluations=max_evaluations,
        timeout_s=float(optimizer.get("timeout_s", 900.0)),
        turns_ratio_target=float(constraints.get("turns_ratio_target", op.voltage_primary_v / op.voltage_secondary_v)),
        turns_ratio_tolerance=float(constraints.get("turns_ratio_tolerance", 0.05)),
        bmax_max_t=_number(constraints.get("bmax_max_t"), 0.25),
        lm_min_h=_number(constraints.get("lm_min_h"), 100e-6),
        lm_max_h=_number(constraints.get("lm_max_h"), 2e-3),
        leakage_target_h=_number(constraints.get("leakage_target_h")),
        leakage_relative_tolerance=float(constraints.get("leakage_relative_tolerance", 0.2)),
    )
    return case, space, config


class Phase6BTaskManager:
    def __init__(self, provider: OpenMagneticsProvider, runtime: Path, executor: Any):
        self.provider = provider
        self.runtime = runtime
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.executor = executor
        self.tasks: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.cancel_events: dict[str, threading.Event] = {}
        self._rehydrate()

    def _rehydrate(self) -> None:
        for file in self.runtime.glob("phase6b-*.json"):
            try:
                document = json.loads(file.read_text(encoding="utf-8"))
                task_id = file.stem.removeprefix("phase6b-")
                result = document["result"]
                self.tasks[task_id] = self._base(task_id, document.get("input", {})) | {
                    "status": result.get("status", "completed"), "progress": 1.0, "result": result,
                    "summary": result.get("summary", {}), "completed_at": file.stat().st_mtime,
                }
            except (OSError, ValueError, KeyError, TypeError):
                continue

    @staticmethod
    def _base(task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": task_id, "mode": "real_structure_optimization", "status": "pending", "progress": 0.0,
            "generation": 0, "evaluated_count": 0, "unique_count": 0, "physical_success_count": 0,
            "cache_hit_count": 0, "geometry_rejected_count": 0, "research_feasible_count": 0,
            "pareto_count": 0, "cancel_requested": False,
            "input_hash": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16],
            "created_at": None,
        }

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:12]
        task = self._base(task_id, payload)
        task["created_at"] = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.tasks[task_id] = task
            event = threading.Event()
            self.cancel_events[task_id] = event
        self.executor.submit(self._run, task_id, copy.deepcopy(payload), event)
        return self.snapshot(task_id)

    def _update(self, task_id: str, **values: Any) -> None:
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(values)

    def _run(self, task_id: str, payload: dict[str, Any], cancel_event: threading.Event) -> None:
        try:
            self._update(task_id, status="running", progress=0.01)
            case, space, config = build_request_context(payload, self.provider)

            def progress(evaluator: Any) -> None:
                summary = evaluator.summary()
                generation = int(getattr(evaluator, "current_generation", 0) or 0)
                evaluated = summary["total_evaluations"]
                self._update(task_id, progress=min(0.98, evaluated / max(config.max_evaluations, 1)), generation=generation, evaluated_count=evaluated, unique_count=summary["unique_candidates"], physical_success_count=summary["successful_physical"], cache_hit_count=summary["cache_hits"], geometry_rejected_count=summary["geometry_rejected"], research_feasible_count=summary["research_feasible"])

            result = optimize_phase6a(case, space, config, cancel_event=cancel_event, progress_callback=progress)
            status = "cancelled" if result.get("status") == "cancelled" else ("failed" if result.get("status") in {"optimizer_error", "timeout"} else "completed")
            summary = result.get("summary", {})
            self._update(task_id, status=status, phase6a_status=result.get("status"), progress=1.0, generation=config.generations, evaluated_count=summary.get("total_evaluations", 0), unique_count=summary.get("unique_candidates", 0), physical_success_count=summary.get("successful_physical", 0), cache_hit_count=summary.get("cache_hits", 0), geometry_rejected_count=summary.get("geometry_rejected", 0), research_feasible_count=summary.get("research_feasible", 0), pareto_count=len(result.get("pareto", [])), summary=summary, result=result, completed_at=datetime.now(timezone.utc).isoformat())
            (self.runtime / f"phase6b-{task_id}.json").write_text(json.dumps({"input": payload, "result": result}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            self._update(task_id, status="failed", progress=1.0, error=str(exc), diagnostics=[_diagnostic("PHASE6B_TASK_FAILED", str(exc))])

    def snapshot(self, task_id: str, *, include_result: bool = False) -> dict[str, Any]:
        with self.lock:
            if task_id not in self.tasks:
                raise KeyError(task_id)
            result = copy.deepcopy(self.tasks[task_id])
        if not include_result:
            result.pop("result", None)
        return result

    def result(self, task_id: str) -> dict[str, Any]:
        with self.lock:
            task = self.tasks.get(task_id)
            if not task or "result" not in task:
                raise KeyError(task_id)
            return copy.deepcopy(task["result"])

    def cancel(self, task_id: str) -> dict[str, Any]:
        with self.lock:
            if task_id not in self.tasks:
                raise KeyError(task_id)
            self.tasks[task_id]["cancel_requested"] = True
            if self.tasks[task_id]["status"] in {"pending", "running"}:
                self.tasks[task_id]["status"] = "cancelling"
            event = self.cancel_events.get(task_id)
            if event:
                event.set()
        return self.snapshot(task_id)


def _records(manager: Phase6BTaskManager, task_id: str, view: str) -> list[dict[str, Any]]:
    result = manager.result(task_id)
    if view == "all":
        return result.get("all_unique_candidates", [])
    if view == "feasible":
        return [item for item in result.get("all_unique_candidates", []) if item.get("research_feasible")]
    if view == "pareto":
        return result.get("pareto", [])
    raise ValueError("UNKNOWN_RESULT_VIEW")


def _csv(records: list[Mapping[str, Any]]) -> str:
    output = io.StringIO()
    columns = ["candidate_hash", "status", "research_feasible", "pareto_rank", "layout", "Np", "Ns", "P1", "P2", "primary_wire", "secondary_wire", "interwinding_gap_m", "core_clearance_m", "total_loss_W", "volume_m3", "pcore_w", "pcu_complete_w", "bmax_t", "lm_h", "leakage_h", "engineering_status"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for item in records:
        variables = item.get("variables", {})
        metrics = item.get("metrics", {})
        objectives = item.get("objectives", [None, None])
        writer.writerow({
            "candidate_hash": item.get("candidate_hash"), "status": item.get("status"), "research_feasible": item.get("research_feasible"), "pareto_rank": item.get("pareto_rank"),
            "layout": variables.get("layout"), "Np": variables.get("Np"), "Ns": variables.get("Ns"), "P1": variables.get("P1"), "P2": variables.get("P2"), "primary_wire": variables.get("primary_wire"), "secondary_wire": variables.get("secondary_wire"),
            "interwinding_gap_m": variables.get("interwinding_gap_m"), "core_clearance_m": variables.get("core_clearance_m"), "total_loss_W": objectives[0] if len(objectives) > 0 else None, "volume_m3": objectives[1] if len(objectives) > 1 else None,
            "pcore_w": metrics.get("pcore_w"), "pcu_complete_w": metrics.get("pcu_complete_w"), "bmax_t": metrics.get("bmax_t"), "lm_h": metrics.get("lm_h"), "leakage_h": metrics.get("leakage_h"), "engineering_status": item.get("engineering_status"),
        })
    return output.getvalue()


def register_phase6b_routes(app: Any, provider: OpenMagneticsProvider, runtime: Path, executor: Any) -> Phase6BTaskManager:
    manager = Phase6BTaskManager(provider, runtime, executor)
    router = APIRouter(prefix="/api/v1.6", tags=["phase6b"])

    @router.get("/status")
    def status() -> dict[str, Any]:
        return {"api_version": PHASE6B_API_VERSION, "mode": "real_structure_optimization", "provider": provider.status(), "synthetic_fallback": False, "limits": {"population_max": 32, "generations_max": 20, "evaluations_max": 256}}

    @router.post("/optimizations")
    def create(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return manager.create(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "PHASE6B_INPUT_INVALID", "message": str(exc)}) from exc

    @router.get("/optimizations/{task_id}")
    def get(task_id: str, include_result: bool = Query(False)) -> dict[str, Any]:
        try:
            return manager.snapshot(task_id, include_result=include_result)
        except KeyError as exc:
            raise HTTPException(404, "phase6b_optimization_not_found") from exc

    @router.get("/optimizations/{task_id}/progress")
    def progress(task_id: str) -> dict[str, Any]:
        try:
            return manager.snapshot(task_id)
        except KeyError as exc:
            raise HTTPException(404, "phase6b_optimization_not_found") from exc

    @router.post("/optimizations/{task_id}/cancel")
    def cancel(task_id: str) -> dict[str, Any]:
        try:
            return manager.cancel(task_id)
        except KeyError as exc:
            raise HTTPException(404, "phase6b_optimization_not_found") from exc

    @router.get("/optimizations/{task_id}/candidates")
    def candidates(task_id: str, view: str = Query("all", pattern="^(all|feasible|pareto)$")) -> dict[str, Any]:
        try:
            values = _records(manager, task_id, view)
            return {"task_id": task_id, "view": view, "count": len(values), "items": values}
        except KeyError as exc:
            raise HTTPException(409, "phase6b_result_not_ready") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/optimizations/{task_id}/candidates/{candidate_hash}")
    def candidate(task_id: str, candidate_hash: str) -> dict[str, Any]:
        try:
            for item in _records(manager, task_id, "all"):
                if item.get("candidate_hash") == candidate_hash:
                    return item
            raise HTTPException(404, "phase6b_candidate_not_found")
        except KeyError as exc:
            raise HTTPException(409, "phase6b_result_not_ready") from exc

    @router.get("/optimizations/{task_id}/report")
    def report(task_id: str, format: str = Query("json", pattern="^(json|csv)$")) -> Response:
        try:
            result = manager.result(task_id)
        except KeyError as exc:
            raise HTTPException(409, "phase6b_result_not_ready") from exc
        if format == "csv":
            return Response(_csv(result.get("all_unique_candidates", [])), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=phase6b-{task_id}.csv"})
        return Response(json.dumps(result, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": f"attachment; filename=phase6b-{task_id}.json"})

    app.include_router(router)
    return manager
