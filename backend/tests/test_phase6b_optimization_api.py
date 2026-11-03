"""Phase 6B request-boundary and API contract tests.

These tests deliberately do not replace the real OpenMagnetics run with a
synthetic fixture.  They cover the web adapter's validation boundary and keep
the real-provider execution as an explicit integration smoke test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.optimization.phase6b_web import _choice, _operating_point, _range, build_request_context
from backend.app.providers.openmagnetics import OpenMagneticsProvider


def _wave(data: list[float], times: list[float], frequency_hz: float = 30_000.0) -> dict:
    return {"data": data, "time": times, "frequency_hz": frequency_hz}


def _explicit_operating_point() -> dict:
    times = [0.0, 8.333333e-6, 16.666667e-6, 25.0e-6]
    return {
        "frequency_hz": 30_000.0,
        "voltage_primary_v": 800.0,
        "voltage_secondary_v": 400.0,
        "current_waveforms": {
            "Primary": _wave([1.0, 1.0, -1.0, -1.0], times),
            "Secondary": _wave([-2.0, -2.0, 2.0, 2.0], times),
        },
        "voltage_waveforms": {
            "Primary": {"data": [800.0, 800.0, -800.0, -800.0], "time": times},
            "Secondary": {"data": [400.0, 400.0, -400.0, -400.0], "time": times},
        },
    }


def test_phase6b_range_and_choice_decoding_is_explicit():
    assert _range({"optimize": True, "min": 18, "max": 22}, (16, 24), integer=True) == (18, 22)
    assert _range({"optimize": False, "value": 20}, (16, 24), integer=True) == (20, 20)
    assert _choice({"optimize": True, "choices": ["PS", "PSP"]}, ("PS",)) == ("PS", "PSP")
    assert _choice({"optimize": False, "value": "PSP"}, ("PS",)) == ("PSP",)


def test_phase6b_requires_explicit_current_and_voltage_waveforms():
    provider = OpenMagneticsProvider(initialize=False)
    with pytest.raises(ValueError, match="MISSING_WAVEFORM:Primary"):
        _operating_point({"operating_point": {"frequency_hz": 30_000.0}})

    with pytest.raises(ValueError, match="SYNTHETIC_DATA_BLOCKED_IN_PHASE6B"):
        build_request_context({"data_source": "demo_fixture", "operating_point": _explicit_operating_point()}, provider)


def test_phase6b_external_request_does_not_silently_use_synthetic_provider():
    provider = OpenMagneticsProvider(initialize=False)
    payload = {"data_source": "external_database", "operating_point": _explicit_operating_point()}
    with pytest.raises(RuntimeError, match="OPENMAGNETICS_UNAVAILABLE"):
        build_request_context(payload, provider)


def test_phase6b_status_route_exposes_no_synthetic_fallback():
    client = TestClient(app)
    response = client.get("/api/v1.6/status")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "real_structure_optimization"
    assert body["synthetic_fallback"] is False
    assert body["limits"]["evaluations_max"] == 256
