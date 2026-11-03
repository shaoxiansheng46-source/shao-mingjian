from __future__ import annotations

import pytest

from backend.app.providers.openmagnetics import MasAdapter, MasAdapterError, OpenMagneticsProvider


def _request() -> dict:
    return {
        "core": {"shape": "ETD 54/28/19", "material": "3C95", "gap_mm": 0.1},
        "bobbin": "Bobbin ETD 54",
        "windings": [
            {"name": "Primary", "number_turns": 20, "wire": "Round 0.5 - Grade 1"},
            {"name": "Secondary", "number_turns": 5, "wire": "Round 0.5 - Grade 1"},
        ],
        "design_requirements": {"magnetizing_inductance_uh": 100.0, "turns_ratios": [{"nominal": 4.0}]},
        "operating_points": [
            {
                "excitations_per_winding": [
                    {"name": "Primary", "frequency_khz": 100, "voltage_waveform": {"data": [1, -1], "time_s": [0, 5e-6]}, "current_waveform": {"data": [0.1, 0.1], "time_s": [0, 5e-6]}},
                    {"name": "Secondary", "frequency_khz": 100, "voltage_waveform": {"data": [0.25, -0.25], "time_s": [0, 5e-6]}, "current_waveform": {"data": [0.4, 0.4], "time_s": [0, 5e-6]}},
                ]
            }
        ],
    }


def test_mas_adapter_uses_si_units_and_preserves_explicit_waveforms():
    mas = MasAdapter().to_mas(_request())
    assert mas["magnetic"]["core"]["functionalDescription"]["gapping"][0]["length"] == pytest.approx(1e-4)
    assert mas["inputs"]["designRequirements"]["magnetizingInductance"]["nominal"] == pytest.approx(100e-6)
    excitation = mas["inputs"]["operatingPoints"][0]["excitationsPerWinding"][0]
    assert excitation["frequency"] == pytest.approx(100_000.0)
    assert excitation["voltage"]["waveform"]["data"] == [1.0, -1.0]


def test_mas_adapter_rejects_dc_bus_without_terminal_waveforms():
    request = _request()
    request["topology"] = "dab"
    request["phase_shift_deg"] = 15
    request["operating_points"] = [{"excitations_per_winding": []}]
    with pytest.raises(MasAdapterError) as error:
        MasAdapter().to_mas(request)
    assert any(item["code"] == "MISSING_WAVEFORMS" for item in error.value.diagnostics)


def test_mas_adapter_requires_dab_phase_shift():
    request = _request()
    request["topology"] = "dab"
    with pytest.raises(MasAdapterError) as error:
        MasAdapter().to_mas(request)
    assert any(item["code"] == "MISSING_DAB_PHASE_SHIFT" for item in error.value.diagnostics)


def test_provider_does_not_turn_unavailable_engine_into_zero():
    provider = OpenMagneticsProvider(initialize=False)
    result = provider.calculate_core_data({"functionalDescription": {"shape": "ETD 54/28/19", "material": "3C95"}})
    assert result["status"] == "unavailable"
    assert result["value"] is None
    assert result["errors"]
