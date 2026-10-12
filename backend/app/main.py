from __future__ import annotations

import copy
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .core.engine import (
    ENGINE_VERSION,
    MODEL_VERSION,
    InputValidationError,
    export_csv,
    export_report,
    load_database,
    nsga2_optimization,
    reference_enumeration,
    validate_input,
    evaluate_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
RUNTIME = ROOT / ".runtime"
RUNTIME.mkdir(exist_ok=True)

app = FastAPI(title="SST 中高频隔离变压器初步设计 Demo", version=ENGINE_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

DB = load_database()
TASKS: dict[str, dict[str, Any]] = {}
TASK_LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sst-demo")

# Rehydrate completed task snapshots so a restarted demo can still expose the
# same reproducible input/result pair for report export.
for _snapshot_file in RUNTIME.glob("*.json"):
    try:
        _snapshot = json.loads(_snapshot_file.read_text(encoding="utf-8"))
        _result = _snapshot["result"]
        TASKS[_snapshot_file.stem] = {
            "id": _snapshot_file.stem, "status": _result.get("status", "completed"), "mode": _result.get("optimizer"), "progress": 1.0,
            "generation": _result.get("generations"), "evaluated_count": _result.get("evaluated_count", _result.get("candidate_count", 0)),
            "feasible_count": _result.get("feasible_count", 0), "pareto_count": _result.get("pareto_count", 0),
            "input_hash": __import__("hashlib").sha256(json.dumps(_snapshot["input"], sort_keys=True).encode()).hexdigest()[:16],
            "created_at": _snapshot_file.stat().st_mtime, "completed_at": _snapshot_file.stat().st_mtime, "result": _result,
        }
    except (OSError, ValueError, KeyError, TypeError):
        continue


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_snapshot(task_id: str) -> dict[str, Any]:
    with TASK_LOCK:
        # The finished result is deliberately returned in full: the workspace
        # renders the actual selected candidate geometry and Pareto points from
        # this same payload, not a placeholder summary.
        return copy.deepcopy(TASKS[task_id])


def run_task(task_id: str, inp: dict[str, Any], mode: str) -> None:
    def update(payload: dict[str, Any]) -> None:
        with TASK_LOCK:
            if task_id in TASKS:
                TASKS[task_id].update(payload)
                TASKS[task_id]["updated_at"] = now()

    def cancelled() -> bool:
        with TASK_LOCK:
            return bool(TASKS.get(task_id, {}).get("cancel_requested"))

    try:
        update({"status": "running", "started_at": now()})
        result = reference_enumeration(inp, update, cancelled) if mode == "reference" else nsga2_optimization(inp, update, cancelled)
        status = result.get("status", "completed")
        with TASK_LOCK:
            TASKS[task_id].update({"status": status, "progress": 1.0 if status != "cancelled" else TASKS[task_id].get("progress", 0), "result": result, "completed_at": now(), "updated_at": now()})
        (RUNTIME / f"{task_id}.json").write_text(json.dumps({"input": inp, "result": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # API must distinguish calculation errors from no-feasible results.
        with TASK_LOCK:
            TASKS[task_id].update({"status": "failed", "error": str(exc), "completed_at": now(), "updated_at": now()})


@app.get("/")
def index_page():
    return FileResponse(FRONTEND / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "engine_version": ENGINE_VERSION, "model_version": MODEL_VERSION, "data_mode": "demo"}


@app.get("/api/v1.4/data/summary")
def data_summary():
    return {
        "data_mode": "demo", "label": "虚构数据演示", "schema_version": "1.4", "normalized_schema_version": "1.5",
        "record_counts": {key: len(value) for key, value in DB.items()},
        "libraries": {key: [{"id": item["id"], "revision": item.get("revision"), "data_status": item.get("data_status"), "engineering_approved": item.get("engineering_approved"), "enabled": item.get("enabled", True), "disabled_reason": item.get("disabled_reason")} for item in value.values()] for key, value in DB.items()},
        "models": [{"id": item["id"], "kind": item.get("kind"), "enabled": item.get("enabled"), "limitation": item.get("limitation")} for item in DB["models"].values()],
    }


@app.get("/api/v1.4/examples/default")
def default_example():
    return json.loads((ROOT / "SST_V1_4_Demo_Data" / "sample_input_feasible.json").read_text(encoding="utf-8"))


@app.get("/api/v1.4/data/{kind}")
def data_records(kind: str):
    if kind not in DB:
        raise HTTPException(404, "unknown_data_kind")
    return list(DB[kind].values())


@app.post("/api/v1.4/projects/validate")
def validate_project(inp: dict[str, Any]):
    try:
        out = validate_input(inp, DB)
        return {"valid": True, **out}
    except InputValidationError as exc:
        return {"valid": False, "error": str(exc), "message": validation_message(str(exc))}


def validation_message(error: str) -> str:
    messages = {
        "SYNTHETIC_DATA_BLOCKED_IN_ENGINEERING": "工程模式不能使用当前虚构 synthetic 数据库；请切换回演示模式或导入经审核工程库。",
        "UNSUPPORTED_WAVEFORM": "当前 Demo 只支持 DAB SPS、50% 对称桥方波；非 50% 占空比已阻断。",
        "DEMO_SUPPORTS_PS_ONLY": "当前仅启用同心 P-S 排布，其他模板保持禁用。",
        "PSP_LAYOUT_NOT_SELECTED": "V1.1 已选择 P-S-P，但搜索排布未选择启用的 P-S-P 模板。",
        "PS_LAYOUT_NOT_SELECTED": "当前选择 P-S，但搜索排布未选择 P-S 模板。",
        "UNKNOWN_LEAKAGE_MODE": "漏感模式只支持集成漏感或允许外置电感。",
        "UNKNOWN_EXTERNAL_MODE": "外置电感模式只支持集成漏感或允许外置电感。",
        "EXTERNAL_MODE_MISMATCH": "外置电感配置与漏感参考模式不一致，请同时选择集成漏感或允许外置电感。",
        "REFERENCE_MODE_V1_0_ONLY": "参考枚举仅用于 V1.0 默认回归；启用 V1.1 后请运行 NSGA-II。",
        "UNKNOWN_CORE_ASSEMBLY": "所选磁芯组合不在当前虚构数据库中。",
        "UNKNOWN_EXTERNAL_INDUCTOR": "所选外置电感不在当前虚构离散库中。",
        "INVALID_LM_TARGET": "励磁电感目标必须为正数。",
        "INVALID_IM_MAX": "励磁电流上限必须为正数。",
        "NO_ENABLED_LAYOUT": "没有可用排布模板。",
        "frequency_out_of_demo_range": "频率超出当前演示材料模型的 10–100 kHz 范围。",
    }
    return messages.get(error.split(":")[0], error)


@app.post("/api/v1.4/designs/evaluate")
def evaluate_design(payload: dict[str, Any]):
    inp = payload.get("input", payload)
    genes = tuple(payload.get("genes", ("DEMO_CORE_XL", 12, 6, "DEMO_LITZ_8000x0p1", "DEMO_LITZ_8000x0p1", 1, 2, 2)))
    try:
        validate_input(inp, DB)
        return evaluate_candidate(inp, DB, genes, reference_mode=False, fast=False)
    except (InputValidationError, ValueError, KeyError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@app.post("/api/v1.4/optimizations")
def create_optimization(payload: dict[str, Any]):
    inp = payload.get("input", payload)
    mode = payload.get("mode", "nsga2")
    try:
        validate_input(inp, DB)
    except InputValidationError as exc:
        raise HTTPException(422, detail={"error": str(exc), "message": validation_message(str(exc))}) from exc
    if mode not in {"reference", "nsga2"}:
        raise HTTPException(422, "mode_must_be_reference_or_nsga2")
    task_id = uuid.uuid4().hex[:12]
    with TASK_LOCK:
        TASKS[task_id] = {
            "id": task_id, "status": "queued", "mode": mode, "progress": 0.0, "generation": None,
            "evaluated_count": 0, "feasible_count": 0, "pareto_count": 0, "cancel_requested": False,
            "input_hash": __import__("hashlib").sha256(json.dumps(inp, sort_keys=True).encode()).hexdigest()[:16], "created_at": now(),
        }
    EXECUTOR.submit(run_task, task_id, copy.deepcopy(inp), mode)
    return {"id": task_id, **task_snapshot(task_id)}


@app.get("/api/v1.4/optimizations/{task_id}")
def get_optimization(task_id: str):
    with TASK_LOCK:
        if task_id not in TASKS:
            raise HTTPException(404, "optimization_not_found")
    return task_snapshot(task_id)


@app.post("/api/v1.4/optimizations/{task_id}/cancel")
def cancel_optimization(task_id: str):
    with TASK_LOCK:
        if task_id not in TASKS:
            raise HTTPException(404, "optimization_not_found")
        TASKS[task_id]["cancel_requested"] = True
        TASKS[task_id]["status"] = "cancelling"
    return task_snapshot(task_id)


@app.get("/api/v1.4/designs/{task_id}/report")
def report(task_id: str, format: str = Query("md", pattern="^(md|csv|json)$")):
    with TASK_LOCK:
        task = TASKS.get(task_id)
    if not task or "result" not in task:
        raise HTTPException(404, "completed_result_not_found")
    result = task["result"]
    inp = json.loads((RUNTIME / f"{task_id}.json").read_text(encoding="utf-8"))["input"]
    if format == "csv":
        return Response(export_csv(result), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={task_id}.csv"})
    if format == "json":
        return Response(json.dumps({"input": inp, "result": result}, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={task_id}.json"})
    return PlainTextResponse(export_report(result, inp), media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename={task_id}.md"})
