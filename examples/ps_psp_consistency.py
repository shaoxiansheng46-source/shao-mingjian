"""Independent PS/PSP electromagnetic consistency benchmark.

The script builds both layouts from the installed OpenMagnetics database,
captures the complete MAS/work-point inputs, compares them, and executes the
real provider calls.  It deliberately keeps the independent reluctance
calculation outside the application geometry/inductance implementation.

Run::

    .runtime\\openmagnetics-venv\\Scripts\\python.exe examples\\ps_psp_consistency.py --output ps_psp_input_diff.json
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

from backend.app.geometry import CoreGeometry, JointCalculationService, WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.providers.openmagnetics import MasAdapter, OpenMagneticsProvider
from examples.phase3_geometry_joint import _core_from_database, _ok, _request

MU0 = 4.0 * math.pi * 1e-7
MODELS = {"reluctance": "ZHANG", "coreLosses": "IGSE", "coreTemperature": "MANIKTALA"}


def _deep_diff(left: Any, right: Any, path: str = "$") -> list[dict[str, Any]]:
    if isinstance(left, dict) and isinstance(right, dict):
        result: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}"
            if key not in left:
                result.append({"path": child, "kind": "added", "right": right[key]})
            elif key not in right:
                result.append({"path": child, "kind": "removed", "left": left[key]})
            else:
                result.extend(_deep_diff(left[key], right[key], child))
        return result
    if isinstance(left, list) and isinstance(right, list):
        result = []
        for index in range(max(len(left), len(right))):
            child = f"{path}[{index}]"
            if index >= len(left):
                result.append({"path": child, "kind": "added", "right": right[index]})
            elif index >= len(right):
                result.append({"path": child, "kind": "removed", "left": left[index]})
            else:
                result.extend(_deep_diff(left[index], right[index], child))
        return result
    if left != right:
        return [{"path": path, "kind": "changed", "left": left, "right": right}]
    return []


def _relative(left: Any, right: Any) -> float | None:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return abs(float(left) - float(right)) / max(abs(float(left)), abs(float(right)), 1e-30)


def _trapezoid(data: list[float], time: list[float]) -> float:
    return sum(0.5 * (left + right) * (t_right - t_left) for left, right, t_left, t_right in zip(data, data[1:], time, time[1:]))


def _waveform_summary(operating_point: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for excitation in operating_point.get("excitationsPerWinding", []):
        voltage = excitation["voltage"]["waveform"]
        data = [float(item) for item in voltage["data"]]
        time = [float(item) for item in voltage["time"]]
        summary[excitation["name"]] = {
            "frequency_hz": excitation.get("frequency"),
            "point_count": len(data),
            "voltage_time_integral_v_s": _trapezoid(data, time),
            "absolute_voltage_time_integral_v_s": _trapezoid([abs(item) for item in data], time),
            "voltage_min_v": min(data),
            "voltage_max_v": max(data),
        }
    return summary


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    openmagnetics = result.get("calculations", {}).get("openmagnetics", {})
    values: dict[str, Any] = {}
    for name in ("core_data", "magnetizing_inductance", "core_losses", "winding_losses", "ohmic_losses", "geometry_call"):
        item = openmagnetics.get(name, {})
        values[name] = {
            "status": item.get("status"),
            "value": item.get("value"),
            "unit": item.get("unit"),
            "model": item.get("model"),
            "details": item.get("details", {}),
            "errors": item.get("errors", []),
        }
    return {"status": result.get("status"), "calculations": values, "mas_validation": result.get("mas_validation")}


def _build_case(provider: OpenMagneticsProvider, core: CoreGeometry, wire: WireGeometry, template: str, request: dict[str, Any], op: dict[str, Any], mas_inputs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    specs = [
        WindingSpec("Primary", "primary", 20, wire, isolation_side="primary"),
        WindingSpec("Secondary", "secondary", 5, wire, isolation_side="secondary"),
    ]
    layout_spec = WindingLayout(
        template_id=template,
        block_order=["P", "S"] if template == "PS" else ["P1", "S", "P2"],
        main_insulation_m=0.00025,
    )
    layout = build_layout(core, specs, layout_spec, provenance={"data_status": "external_database", "synthetic": False, "demo_only": False, "engineering_approved": False})
    result = JointCalculationService(provider).calculate(layout, operating_point=op, inputs=mas_inputs, models=MODELS)
    snapshot = {
        "magnetic": result.get("mas"),
        "operating_point": copy.deepcopy(op),
        "inputs": copy.deepcopy(mas_inputs),
        "temperature_c": 25.0,
        "models": MODELS,
        "geometry": layout.as_dict(),
    }
    return result, snapshot


def _independent_reluctance(provider: OpenMagneticsProvider, request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    core_value = result["calculations"]["openmagnetics"]["core_data"]["value"]
    material_result = _ok(provider.find_core_material_by_name(request["core"]["material"]), "material lookup")
    material = material_result["value"]
    mu_r = material.get("permeability_real_at_100khz")
    gap_m = float(request["core"]["gap_mm"]) * 1e-3
    turns = int(request["windings"][0]["number_turns"])
    if mu_r is None:
        return {"status": "unavailable", "reason": "数据库未提供 100 kHz 实部磁导率。", "material": material}
    ae = float(core_value["effective_area_m2"])
    le = float(core_value["effective_length_m"])
    r_core = le / (MU0 * float(mu_r) * ae)
    r_gap = gap_m / (MU0 * ae)
    r_total = r_core + r_gap
    inductance = turns * turns / r_total
    return {
        "status": "ok",
        "assumption": "linear reluctance: Rm=le/(mu0*mur*Ae)+gap/(mu0*Ae)",
        "ae_m2": ae,
        "le_m": le,
        "gap_m": gap_m,
        "mu_r_real_at_100khz": float(mu_r),
        "turns": turns,
        "reluctance_core_a_per_wb": r_core,
        "reluctance_gap_a_per_wb": r_gap,
        "reluctance_total_a_per_wb": r_total,
        "inductance_h": inductance,
        "material": material,
    }


def run() -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    report: dict[str, Any] = {
        "benchmark": "phase3_ps_psp_electromagnetic_consistency",
        "status": "running",
        "third_party": provider.status(),
        "results": {},
        "input_snapshots": {},
        "checks": [],
    }
    if not provider.available:
        report["status"] = "unavailable"
        return report
    request = _request()
    core = _core_from_database(provider, request)
    wire_result = _ok(provider.find_wire_by_name(request["windings"][0]["wire"]), "wire lookup")
    wire_record = wire_result["value"]
    wire = WireGeometry(
        wire_record["name"],
        float(wire_record["outer_diameter_m"]),
        float(wire_record["conducting_diameter_m"]),
        number_conductors=int(wire_record.get("number_conductors") or 1),
    )
    mas_inputs = MasAdapter().to_inputs(request)
    op = mas_inputs["operatingPoints"][0]
    full_results: dict[str, dict[str, Any]] = {}
    for template in ("PS", "PSP"):
        result, snapshot = _build_case(provider, core, wire, template, request, op, mas_inputs)
        full_results[template] = result
        report["results"][template] = _result_summary(result)
        report["input_snapshots"][template] = snapshot

    ps = report["input_snapshots"]["PS"]
    psp = report["input_snapshots"]["PSP"]
    ps_result = report["results"]["PS"]
    psp_result = report["results"]["PSP"]
    ps_fd = ps["magnetic"]["coil"]["functionalDescription"]
    psp_fd = psp["magnetic"]["coil"]["functionalDescription"]
    ps_l = ps_result["calculations"]["magnetizing_inductance"]["value"]
    psp_l = psp_result["calculations"]["magnetizing_inductance"]["value"]
    ps_b = ps_result["calculations"]["core_losses"]["details"].get("magnetic_flux_density_peak_t")
    psp_b = psp_result["calculations"]["core_losses"]["details"].get("magnetic_flux_density_peak_t")
    ps_core_loss = ps_result["calculations"]["core_losses"]["value"]
    psp_core_loss = psp_result["calculations"]["core_losses"]["value"]
    independent = _independent_reluctance(provider, request, full_results["PS"])
    report["independent_reluctance"] = independent
    report["waveform_summary"] = {"PS": _waveform_summary(ps["operating_point"]), "PSP": _waveform_summary(psp["operating_point"])}
    report["raw_input_diff"] = _deep_diff(ps, psp)
    report["electrical_input_diff"] = _deep_diff(
        {"core": ps["magnetic"]["core"], "functionalDescription": ps_fd, "inputs": ps["inputs"], "operating_point": ps["operating_point"], "temperature_c": ps["temperature_c"], "models": ps["models"]},
        {"core": psp["magnetic"]["core"], "functionalDescription": psp_fd, "inputs": psp["inputs"], "operating_point": psp["operating_point"], "temperature_c": psp["temperature_c"], "models": psp["models"]},
    )
    report["physical_geometry_diff"] = [item for item in report["raw_input_diff"] if any(token in item["path"] for token in ("geometry", "sectionsDescription", "layersDescription", "turnsDescription", "sstElectrical"))]
    report["checks"] = [
        {"name": "provider_calls_ok", "passed": all(item["calculations"][name]["status"] == "ok" for item in (ps_result, psp_result) for name in ("core_data", "magnetizing_inductance", "core_losses", "winding_losses", "ohmic_losses", "geometry_call"))},
        {"name": "same_core_gap_and_workpoint", "passed": ps["magnetic"]["core"] == psp["magnetic"]["core"] and ps["inputs"] == psp["inputs"] and ps["operating_point"] == psp["operating_point"], "details": {"electrical_input_diff_count": len(report["electrical_input_diff"])}},
        {"name": "primary_total_turns_and_psp_series", "passed": ps_fd[0]["numberTurns"] == 20 and psp_fd[0]["name"] == "Primary" and psp_fd[0]["numberTurns"] == 20 and psp["magnetic"]["coil"]["sstElectricalConnections"] == {"type": "series", "direction": "same", "primary_segments": ["P1", "P2"], "constraint": "P1+P2=Np"}},
        {"name": "openmagnetics_ps_psp_inductance", "passed": _relative(ps_l, psp_l) is not None and _relative(ps_l, psp_l) <= 0.01, "details": {"ps_h": ps_l, "psp_h": psp_l, "relative_difference": _relative(ps_l, psp_l), "tolerance": 0.01}},
        {"name": "independent_reluctance_vs_openmagnetics", "passed": independent.get("status") == "ok" and _relative(independent.get("inductance_h"), ps_l) is not None and _relative(independent.get("inductance_h"), ps_l) <= 0.01, "details": {"independent_h": independent.get("inductance_h"), "openmagnetics_h": ps_l, "relative_difference": _relative(independent.get("inductance_h"), ps_l), "tolerance": 0.01}},
        {"name": "same_flux_and_core_loss", "passed": _relative(ps_b, psp_b) is not None and _relative(ps_b, psp_b) <= 0.01 and _relative(ps_core_loss, psp_core_loss) is not None and _relative(ps_core_loss, psp_core_loss) <= 0.01, "details": {"ps_peak_b_t": ps_b, "psp_peak_b_t": psp_b, "ps_core_loss_w": ps_core_loss, "psp_core_loss_w": psp_core_loss, "relative_b_difference": _relative(ps_b, psp_b), "relative_loss_difference": _relative(ps_core_loss, psp_core_loss), "tolerance": 0.01}},
    ]
    report["interpretation"] = {
        "electrical_inputs_match": len(report["electrical_input_diff"]) == 0,
        "raw_input_difference_count": len(report["raw_input_diff"]),
        "physical_geometry_is_expected_to_differ": True,
        "winding_loss_comparison": {"ps_w": ps_result["calculations"]["winding_losses"]["value"], "psp_w": psp_result["calculations"]["winding_losses"]["value"], "note": "P1/S/P2 实体位置不同，绕组损耗允许不同；本专项不把它强行判定为电磁不一致。"},
    }
    report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("ps_psp_input_diff.json"))
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "checks": report.get("checks", []), "independent_reluctance": report.get("independent_reluctance")}, ensure_ascii=False, indent=2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
