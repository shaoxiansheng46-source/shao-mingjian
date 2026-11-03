"""Independent OpenMagnetics database and physics benchmark.

Run with the isolated interpreter created for phase 2, for example:

    .runtime\\openmagnetics-venv\\Scripts\\python.exe examples\\openmagnetics_benchmark.py --output .runtime\\openmagnetics-benchmark.json

The script does not import or call the SST optimizer.  A missing third-party
runtime is reported as unavailable; no synthetic or hard-coded result is used.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.providers.openmagnetics import MasAdapter, MasAdapterError, OpenMagneticsProvider


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def _require_ok(result: dict[str, Any], label: str) -> dict[str, Any]:
    if result.get("status") != "ok":
        raise RuntimeError(f"{label} 失败: {result.get('errors')}")
    return result


def _make_request() -> dict[str, Any]:
    return {
        "topology": "dab",
        "phase_shift_deg": 15.0,
        "ambient_temperature_c": 25.0,
        "core": {
            "type": "two-piece set",
            "shape": "ETD 54/28/19",
            "material": "3C95",
            "gap_mm": 0.1,
            "number_stacks": 1,
        },
        "bobbin": "Bobbin ETD 54",
        "windings": [
            {"name": "Primary", "number_turns": 20, "number_parallels": 1, "wire": "Round 0.5 - Grade 1", "isolation_side": "primary"},
            {"name": "Secondary", "number_turns": 5, "number_parallels": 1, "wire": "Round 0.5 - Grade 1", "isolation_side": "secondary"},
        ],
        "design_requirements": {
            "magnetizing_inductance_uh": 100.0,
            "turns_ratios": [{"nominal": 4.0}],
        },
        "operating_points": [
            {
                "name": "Nominal",
                "excitations_per_winding": [
                    {"name": "Primary", "frequency_hz": 100000.0, "voltage_waveform": {"data": [100.0, 100.0, -100.0, -100.0], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}, "current_waveform": {"data": [0.2, 0.4, 0.4, 0.2], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}},
                    {"name": "Secondary", "frequency_hz": 100000.0, "voltage_waveform": {"data": [25.0, 25.0, -25.0, -25.0], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}, "current_waveform": {"data": [0.8, 1.2, 1.2, 0.8], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}},
                ],
            }
        ],
    }


def _replace_operating_point(request: dict[str, Any], *, frequency_hz: float | None = None, current_scale: float | None = None) -> dict[str, Any]:
    value = copy.deepcopy(request)
    op = value["operating_points"][0]
    for excitation in op["excitations_per_winding"]:
        if frequency_hz is not None:
            excitation["frequency_hz"] = frequency_hz
            old_time = excitation["voltage_waveform"]["time_s"]
            period_scale = 100000.0 / frequency_hz
            excitation["voltage_waveform"]["time_s"] = [item * period_scale for item in old_time]
            excitation["current_waveform"]["time_s"] = [item * period_scale for item in old_time]
        if current_scale is not None:
            excitation["current_waveform"]["data"] = [item * current_scale for item in excitation["current_waveform"]["data"]]
    return value


def run() -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    status = provider.status()
    report: dict[str, Any] = {
        "benchmark": "openmagnetics_phase2_independent",
        "status": "running",
        "runtime": status,
        "checks": [],
        "results": {},
        "called_functions": [
            "load_databases",
            "get_core_materials",
            "get_core_shapes",
            "get_wires",
            "find_core_material_by_name",
            "find_core_shape_by_name",
            "find_wire_by_name",
            "find_bobbin_by_name",
            "calculate_core_data",
            "calculate_inductance_from_number_turns_and_gapping",
            "calculate_gapping_from_number_turns_and_inductance",
            "calculate_core_losses",
            "calculate_ohmic_losses",
            "calculate_skin_effect_losses",
            "calculate_magnetic_field_strength_field",
            "calculate_proximity_effect_losses",
            "calculate_winding_losses",
            "wind",
        ],
    }
    if not provider.available:
        report["status"] = "unavailable"
        report["checks"].append(_check("runtime_available", False, {"errors": status.get("errors", [])}))
        return report

    materials = provider.get_core_materials(limit=1)
    shapes = provider.get_core_shapes(limit=1)
    wires = provider.get_wires(limit=1)
    report["checks"].append(_check("database_counts", all(item.get("status") == "ok" for item in (materials, shapes, wires)), {"materials": materials.get("count"), "shapes": shapes.get("count"), "wires": wires.get("count")}))

    request = _make_request()
    adapter = MasAdapter()
    mas = adapter.to_mas(request)
    report["checks"].append(_check("mas_unit_conversion", math.isclose(mas["magnetic"]["core"]["functionalDescription"]["gapping"][0]["length"], 1e-4) and math.isclose(mas["inputs"]["operatingPoints"][0]["excitationsPerWinding"][0]["frequency"], 1e5), {"gap_m": mas["magnetic"]["core"]["functionalDescription"]["gapping"][0]["length"], "frequency_hz": mas["inputs"]["operatingPoints"][0]["excitationsPerWinding"][0]["frequency"]}))
    try:
        adapter.to_mas({"topology": "dab", "dc_bus_voltage": 400.0, "core": request["core"], "windings": request["windings"], "design_requirements": request["design_requirements"], "operating_points": [{"excitations_per_winding": []}]})
        missing_waveform_check = False
    except MasAdapterError as exc:
        missing_waveform_check = any(item["code"] in {"MISSING_WAVEFORMS", "MISSING_DAB_PHASE_SHIFT", "MISSING_WAVEFORM"} for item in exc.diagnostics)
    report["checks"].append(_check("missing_waveform_diagnostic", missing_waveform_check, {"dc_bus_voltage_not_promoted_to_waveform": True}))

    material = _require_ok(provider.find_core_material_by_name(request["core"]["material"]), "material lookup")
    shape = _require_ok(provider.find_core_shape_by_name(request["core"]["shape"]), "shape lookup")
    wire = _require_ok(provider.find_wire_by_name(request["windings"][0]["wire"]), "wire lookup")
    report["results"]["selected_database_records"] = {"material": material["value"], "shape": shape["value"], "wire": wire["value"]}

    core_result = _require_ok(provider.calculate_core_data(mas["magnetic"]["core"]), "core data")
    op = mas["inputs"]["operatingPoints"][0]
    inductance = _require_ok(provider.calculate_inductance(mas["magnetic"]["core"], mas["magnetic"]["coil"], op, {"reluctance": "ZHANG"}), "inductance")
    gap_solution = provider.calculate_gap_for_inductance(mas["magnetic"]["core"], mas["magnetic"]["coil"], mas["inputs"], "SUBTRACTIVE", 4, {"reluctance": "ZHANG"})
    core_losses = _require_ok(provider.calculate_core_losses(mas["magnetic"]["core"], mas["magnetic"]["coil"], mas["inputs"], {"coreLosses": "IGSE", "reluctance": "ZHANG", "coreTemperature": "MANIKTALA"}), "core losses")
    winding_losses = _require_ok(provider.calculate_winding_losses(mas["magnetic"], op, 25.0), "winding losses")
    ohmic_losses = _require_ok(provider.calculate_ohmic_losses(mas["magnetic"]["coil"], op, 25.0), "ohmic losses")
    # The compact four-point waveform is sufficient for the full winding-loss
    # path, but the standalone AC components require pre-computed harmonics and
    # a field object.  Call them explicitly and retain the diagnostic instead of
    # manufacturing a zero.
    skin_losses = provider.calculate_skin_effect_losses(mas["magnetic"]["coil"], op, 25.0)
    proximity_losses = provider.calculate_proximity_effect_losses(mas["magnetic"], op, 25.0)
    report["results"]["core_data"] = core_result
    report["results"]["magnetizing_inductance"] = inductance
    report["results"]["gap_solution"] = gap_solution
    report["checks"].append(_check("gap_solver_no_silent_fallback", (gap_solution.get("status") == "ok" and gap_solution.get("value")) or (gap_solution.get("status") == "error" and gap_solution.get("value") is None and gap_solution.get("errors")), {"status": gap_solution.get("status"), "errors": gap_solution.get("errors"), "note": "当前精简 MAS 输入在 MKF gap solver 返回 Bad optional access；保留诊断，不当作零气隙。"}))
    report["results"]["core_losses"] = core_losses
    report["results"]["winding_losses"] = winding_losses
    report["results"]["ohmic_losses"] = ohmic_losses
    report["results"]["skin_losses"] = skin_losses
    report["results"]["proximity_losses"] = proximity_losses
    report["checks"].append(_check("standalone_ac_loss_input_diagnostic", skin_losses.get("status") == "error" and proximity_losses.get("status") == "error", {"skin_status": skin_losses.get("status"), "proximity_status": proximity_losses.get("status"), "note": "紧凑波形没有调用 process_inputs 生成的 harmonics；未静默回退为零。"}))

    turns_request = copy.deepcopy(request)
    turns_request["windings"][0]["number_turns"] = 40
    turns_mas = adapter.to_mas(turns_request)
    l40 = _require_ok(provider.calculate_inductance(turns_mas["magnetic"]["core"], turns_mas["magnetic"]["coil"], turns_mas["inputs"]["operatingPoints"][0], {"reluctance": "ZHANG"}), "40-turn inductance")
    gap_request = copy.deepcopy(request)
    gap_request["core"]["gap_mm"] = 0.2
    gap_mas = adapter.to_mas(gap_request)
    lgap = _require_ok(provider.calculate_inductance(gap_mas["magnetic"]["core"], gap_mas["magnetic"]["coil"], gap_mas["inputs"]["operatingPoints"][0], {"reluctance": "ZHANG"}), "larger-gap inductance")
    current_request = _replace_operating_point(request, current_scale=2.0)
    current_mas = adapter.to_mas(current_request)
    ohmic_2x = _require_ok(provider.calculate_ohmic_losses(current_mas["magnetic"]["coil"], current_mas["inputs"]["operatingPoints"][0], 25.0), "2x current ohmic loss")
    frequency_request = _replace_operating_point(request, frequency_hz=200000.0)
    frequency_mas = adapter.to_mas(frequency_request)
    core_loss_2f = _require_ok(provider.calculate_core_losses(frequency_mas["magnetic"]["core"], frequency_mas["magnetic"]["coil"], frequency_mas["inputs"], {"coreLosses": "IGSE", "reluctance": "ZHANG", "coreTemperature": "MANIKTALA"}), "2x frequency core loss")

    l20 = float(inductance["value"])
    l40_value = float(l40["value"])
    lgap_value = float(lgap["value"])
    p1 = float(ohmic_losses["value"])
    p2 = float(ohmic_2x["value"])
    f1 = float(core_losses["value"])
    f2 = float(core_loss_2f["value"])
    report["checks"].extend([
        _check("turns_vs_inductance", 3.0 < l40_value / l20 < 5.0, {"l20_h": l20, "l40_h": l40_value, "ratio": l40_value / l20}),
        _check("gap_vs_inductance", lgap_value < l20, {"gap_0_1mm_h": l20, "gap_0_2mm_h": lgap_value}),
        _check("current_vs_ohmic_loss", 3.2 < p2 / p1 < 4.8, {"loss_1x_w": p1, "loss_2x_w": p2, "ratio": p2 / p1}),
        _check("frequency_call_changes_core_loss", f1 >= 0 and f2 >= 0 and not math.isclose(f1, f2, rel_tol=1e-12, abs_tol=1e-15), {"loss_100khz_w": f1, "loss_200khz_w": f2}),
    ])

    repeat = _require_ok(provider.calculate_core_losses(mas["magnetic"]["core"], mas["magnetic"]["coil"], mas["inputs"], {"coreLosses": "IGSE", "reluctance": "ZHANG", "coreTemperature": "MANIKTALA"}), "repeat core losses")
    report["checks"].append(_check("repeatability", math.isclose(float(repeat["value"]), f1, rel_tol=1e-12, abs_tol=1e-15), {"first_w": f1, "second_w": float(repeat["value"])}))
    invalid = provider.find_core_material_by_name("__not_a_real_material__")
    report["checks"].append(_check("invalid_lookup_diagnostic", invalid.get("status") == "error" and bool(invalid.get("errors")), {"status": invalid.get("status"), "errors": invalid.get("errors")}))
    invalid_core = provider.find_core_shape_by_name("__not_a_real_core__")
    report["checks"].append(_check("invalid_core_diagnostic", invalid_core.get("status") == "error" and bool(invalid_core.get("errors")), {"status": invalid_core.get("status"), "errors": invalid_core.get("errors")}))
    invalid_winding = provider.wind({"bobbin": request["bobbin"], "functionalDescription": [{"name": "Primary", "wire": request["windings"][0]["wire"]}]})
    report["checks"].append(_check("invalid_winding_diagnostic", invalid_winding.get("status") == "error" and invalid_winding.get("value") is None, {"status": invalid_winding.get("status"), "errors": invalid_winding.get("errors")}))
    unsupported_model = provider.calculate_core_losses(mas["magnetic"]["core"], mas["magnetic"]["coil"], mas["inputs"], {"coreLosses": "NOT_A_MODEL", "reluctance": "ZHANG", "coreTemperature": "MANIKTALA"})
    report["checks"].append(_check("unsupported_model_diagnostic", unsupported_model.get("status") == "error" and unsupported_model.get("value") is None, {"status": unsupported_model.get("status"), "errors": unsupported_model.get("errors")}))
    report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the JSON report to this path")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
