"""Phase 5D API tests; the synthetic fixture is explicit and stays demo-only."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.app.main import app


CLIENT = TestClient(app)


def _payload(*, layout: str = "PS", waveforms: bool = True) -> dict:
    times = [0.0, 8.333333e-6, 16.666667e-6, 25e-6]
    op = {
        "voltage_primary_v": 100.0,
        "voltage_secondary_v": 25.0,
        "power_w": 1000.0,
        "frequency_hz": 30000.0,
        "ambient_c": 25.0,
        "currents_rms_a": {"Primary": 2.0, "Secondary": -8.0} if waveforms else {},
        "current_waveforms": {
            "Primary": {"frequency_hz": 30000.0, "time_s": times, "data": [2.0, 2.0, -2.0, -2.0]},
            "Secondary": {"frequency_hz": 30000.0, "time_s": times, "data": [-8.0, -8.0, 8.0, 8.0]},
        } if waveforms else {},
        "voltage_waveforms": {
            "Primary": {"frequency_hz": 30000.0, "time_s": times, "data": [100.0, 100.0, -100.0, -100.0]},
            "Secondary": {"frequency_hz": 30000.0, "time_s": times, "data": [25.0, 25.0, -25.0, -25.0]},
        } if waveforms else {},
    }
    result = {
        "data_source": "demo_fixture",
        "layout": layout,
        "primary_turns": 20 if layout == "PS" else 21,
        "secondary_turns": 5,
        "primary_segments": None if layout == "PS" else [10, 11],
        "core": {"core_id": "DEMO_CORE_XL", "gap_mm": 0.2},
        "wire": {"primary_name": "DEMO_LITZ_8000x0p1", "secondary_name": "DEMO_LITZ_8000x0p1"},
        "geometry": {"main_insulation_mm": 0.25, "winding_to_core_clearance_mm": 0.5, "end_margin_mm": 3.0},
        "operating_point": op,
        "include_openmagnetics": False,
    }
    if layout == "PSP":
        result["wire"] = {"primary_name": "DEMO_LITZ_2000x0p1", "secondary_name": "DEMO_LITZ_2000x0p1"}
    return result


def _wait(task_id: str) -> dict:
    for _ in range(40):
        value = CLIENT.get(f"/api/v1.5/physical/evaluations/{task_id}").json()
        if value.get("status") in {"completed", "input_invalid", "failed"}:
            return value
        time.sleep(0.025)
    raise AssertionError("physical evaluation did not finish")


def test_physical_status_exposes_provider_and_thermal_boundary():
    response = CLIENT.get("/api/v1.5/physical/status")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "physical_workbench"
    assert body["provider"]["provenance"]["third_party_package"] == "PyOpenMagnetics"
    assert body["thermal"]["status"] == "not_implemented"


def test_geometry_only_preserves_missing_waveform_diagnostics():
    response = CLIENT.post("/api/v1.5/physical/evaluations", json=_payload(waveforms=False))
    result = _wait(response.json()["id"])["result"]
    assert result["geometry"]["status"] == "ok"
    assert result["waveform_requirements"]["status"] == "missing"
    assert any(item["code"] == "MISSING_VOLTAGE_WAVEFORM" for item in result["diagnostics"])
    assert result["thermal"]["hotspot_C"] is None


def test_ps_full_waveform_calculation_uses_unified_snapshot_and_exports_json():
    created = CLIENT.post("/api/v1.5/physical/evaluations", json=_payload())
    task_id = created.json()["id"]
    task = _wait(task_id)
    result = task["result"]
    assert task["status"] == "completed"
    assert result["geometry"]["status"] == "ok"
    assert result["electromagnetic"]["leakage"]["status"] == "ok"
    assert result["summary"]["Pcu_native_W"] is not None
    assert result["source_selection"]["synthetic"] is True
    report = CLIENT.get(f"/api/v1.5/physical/evaluations/{task_id}/report?format=json")
    assert report.status_code == 200
    assert report.json()["result"]["evaluation_key"] == result["evaluation_key"]


def test_psp_keeps_two_physical_primary_blocks_and_series_connection():
    task = _wait(CLIENT.post("/api/v1.5/physical/evaluations", json=_payload(layout="PSP")).json()["id"])
    result = task["result"]
    assert result["geometry"]["status"] == "ok"
    layout = result["geometry"]["data"]
    assert [item["name"] for item in layout["blocks"]] == ["P1", "S", "P2"]
    assert sum(item["turns"] for item in layout["blocks"] if item["role"] == "primary") == 21
    assert layout["connection"]["type"] == "series"
    assert layout["connection"]["direction"] == "same"
