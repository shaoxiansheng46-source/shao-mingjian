"""Phase 3 parameterized geometry + real OpenMagnetics joint benchmark.

Run with the isolated Phase 2 interpreter::

    .runtime\\openmagnetics-venv\\Scripts\\python.exe examples\\phase3_geometry_joint.py --output .runtime\\phase3-geometry-joint.json

The selected core, bobbin and wire are looked up at runtime.  No physical
result is read from a fixture or substituted when a provider call fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.geometry import CoreGeometry, JointCalculationService, WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.providers.openmagnetics import MasAdapter, OpenMagneticsProvider


def _ok(result: dict[str, Any], label: str) -> dict[str, Any]:
    if result.get("status") != "ok":
        raise RuntimeError(f"{label} failed: {result.get('errors')}")
    return result


def _request() -> dict[str, Any]:
    return {
        "topology": "dab",
        "phase_shift_deg": 15.0,
        "ambient_temperature_c": 25.0,
        "core": {"type": "two-piece set", "shape": "ETD 54/28/19", "material": "3C95", "gap_mm": 0.1, "number_stacks": 1},
        "bobbin": "Bobbin ETD 54",
        "windings": [
            {"name": "Primary", "number_turns": 20, "number_parallels": 1, "wire": "Round 0.5 - Grade 1", "isolation_side": "primary"},
            {"name": "Secondary", "number_turns": 5, "number_parallels": 1, "wire": "Round 0.5 - Grade 1", "isolation_side": "secondary"},
        ],
        "design_requirements": {"magnetizing_inductance_uh": 100.0, "turns_ratios": [{"nominal": 4.0}]},
        "operating_points": [{
            "name": "Nominal",
            "excitations_per_winding": [
                {"name": "Primary", "frequency_hz": 100000.0, "voltage_waveform": {"data": [100.0, 100.0, -100.0, -100.0], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}, "current_waveform": {"data": [0.2, 0.4, 0.4, 0.2], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}},
                {"name": "Secondary", "frequency_hz": 100000.0, "voltage_waveform": {"data": [25.0, 25.0, -25.0, -25.0], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}, "current_waveform": {"data": [0.8, 1.2, 1.2, 0.8], "time_s": [0.0, 5e-6, 5e-6, 10e-6]}},
            ],
        }],
    }


def _core_from_database(provider: OpenMagneticsProvider, request: dict[str, Any]) -> CoreGeometry:
    core_result = _ok(provider.calculate_core_data({"functionalDescription": request["core"]}), "core data")
    shape_result = _ok(provider.find_core_shape_by_name(request["core"]["shape"]), "shape lookup")
    bobbin_result = _ok(provider.find_bobbin_by_name(request["bobbin"]), "bobbin lookup")
    shape = shape_result["value"]
    dimensions = {}
    for key, value in (shape.get("dimensions_m") or {}).items():
        if isinstance(value, dict) and value.get("maximum_m") is not None:
            dimensions[f"{key}_maximum_m"] = value["maximum_m"]
    processed = bobbin_result["value"]["processed_description"]
    window = processed["winding_windows"][0]
    return CoreGeometry(
        core_id=shape["name"],
        shape_name=shape["name"],
        material_name=request["core"]["material"],
        physical_dimensions_m=dimensions,
        effective_area_m2=core_result["value"]["effective_area_m2"],
        effective_length_m=core_result["value"]["effective_length_m"],
        effective_volume_m3=core_result["value"]["effective_volume_m3"],
        window_width_m=float(window["width"]),
        window_height_m=float(window["height"]),
        winding_column_width_m=float(processed["column_width_m"]),
        winding_column_depth_m=float(processed["column_depth_m"]),
        bobbin_wall_m=float(processed["wall_thickness_m"]),
        bobbin_id=request["bobbin"],
        gap_m=float(request["core"]["gap_mm"]) * 1e-3,
        stack_count=int(request["core"]["number_stacks"]),
    )


def run() -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    report: dict[str, Any] = {"benchmark": "openmagnetics_phase3_geometry_joint", "status": "running", "results": {}, "checks": []}
    if not provider.available:
        report["status"] = "unavailable"
        report["errors"] = provider.status().get("errors", [])
        return report
    request = _request()
    core = _core_from_database(provider, request)
    wire_result = _ok(provider.find_wire_by_name(request["windings"][0]["wire"]), "wire lookup")
    wire_record = wire_result["value"]
    wire = WireGeometry(
        wire_id=wire_record["name"],
        outer_diameter_m=float(wire_record["outer_diameter_m"]),
        conducting_diameter_m=float(wire_record["conducting_diameter_m"]),
        number_conductors=int(wire_record.get("number_conductors") or 1),
    )
    specs = [
        WindingSpec("Primary", "primary", 20, wire, isolation_side="primary"),
        WindingSpec("Secondary", "secondary", 5, wire, isolation_side="secondary"),
    ]
    mas_inputs = MasAdapter().to_inputs(request)
    op = mas_inputs["operatingPoints"][0]
    service = JointCalculationService(provider)
    for template in ("PS", "PSP"):
        # The real bobbin lookup does not provide an insulation-rule approval.
        # Use an explicit 0.25 mm research barrier so PSP can be evaluated in
        # this window; this is not a claim of compliance with a safety standard.
        layout_spec = WindingLayout(
            template_id=template,
            block_order=["P", "S"] if template == "PS" else ["P1", "S", "P2"],
            main_insulation_m=0.00025,
        )
        layout = build_layout(core, specs, layout_spec, provenance={"data_status": "external_database", "synthetic": False, "demo_only": False, "engineering_approved": False})
        # PSP is one electrical Primary winding made of two physical series
        # blocks.  Both layouts therefore receive the same terminal waveform;
        # P1/P2 remain visible only in the physical geometry metadata.
        result = service.calculate(layout, operating_point=op, inputs=mas_inputs, models={"reluctance": "ZHANG", "coreLosses": "IGSE", "coreTemperature": "MANIKTALA"})
        report["results"][template] = result
        report["checks"].append({"name": f"{template}_geometry_feasible", "passed": layout.feasible, "details": {"violations": [item.as_dict() for item in layout.violations]}})
        report["checks"].append({"name": f"{template}_mas_mapping_valid", "passed": result.get("mas_validation", {}).get("valid", False), "details": result.get("mas_validation")})
        calculations = result.get("calculations", {}).get("openmagnetics", {})
        required_calls = ["core_data", "magnetizing_inductance", "core_losses", "winding_losses", "ohmic_losses", "geometry_call"]
        report["checks"].append({
            "name": f"{template}_real_provider_calculations",
            "passed": all(calculations.get(name, {}).get("status") == "ok" for name in required_calls),
            "details": {name: calculations.get(name, {}).get("status") for name in required_calls},
        })
    ps = report["results"].get("PS", {})
    psp = report["results"].get("PSP", {})
    ps_magnetic = ps.get("mas", {})
    psp_magnetic = psp.get("mas", {})
    ps_fd = ps_magnetic.get("coil", {}).get("functionalDescription", [])
    psp_fd = psp_magnetic.get("coil", {}).get("functionalDescription", [])
    ps_open = ps.get("calculations", {}).get("openmagnetics", {})
    psp_open = psp.get("calculations", {}).get("openmagnetics", {})

    def _value(result: dict[str, Any]) -> Any:
        return result.get("value") if isinstance(result, dict) else None

    ps_l = _value(ps_open.get("magnetizing_inductance", {}))
    psp_l = _value(psp_open.get("magnetizing_inductance", {}))
    ps_core_loss = _value(ps_open.get("core_losses", {}))
    psp_core_loss = _value(psp_open.get("core_losses", {}))
    ps_b = ps_open.get("core_losses", {}).get("details", {}).get("magnetic_flux_density_peak_t")
    psp_b = psp_open.get("core_losses", {}).get("details", {}).get("magnetic_flux_density_peak_t")

    def _relative(a: Any, b: Any) -> float | None:
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return None
        denominator = max(abs(float(a)), abs(float(b)), 1e-30)
        return abs(float(a) - float(b)) / denominator

    electrical_consistent = (
        [(item.get("name"), item.get("numberTurns"), item.get("wire")) for item in ps_fd]
        == [(item.get("name"), item.get("numberTurns"), item.get("wire")) for item in psp_fd]
        == [("Primary", 20, request["windings"][0]["wire"]), ("Secondary", 5, request["windings"][1]["wire"])]
    )
    report["checks"].extend([
        {
            "name": "PS_PSP_same_electrical_input",
            "passed": electrical_consistent and ps.get("geometry", {}).get("template", {}).get("template_id") != psp.get("geometry", {}).get("template", {}).get("template_id"),
            "details": {"ps_functional_description": ps_fd, "psp_functional_description": psp_fd, "operating_point_shared": True},
        },
        {
            "name": "PS_PSP_magnetizing_inductance_consistent",
            "passed": _relative(ps_l, psp_l) is not None and _relative(ps_l, psp_l) <= 0.01,
            "details": {"ps_h": ps_l, "psp_h": psp_l, "relative_difference": _relative(ps_l, psp_l), "tolerance": 0.01},
        },
        {
            "name": "PS_PSP_core_flux_and_loss_consistent",
            "passed": _relative(ps_b, psp_b) is not None and _relative(ps_b, psp_b) <= 0.01 and _relative(ps_core_loss, psp_core_loss) is not None and _relative(ps_core_loss, psp_core_loss) <= 0.01,
            "details": {"ps_peak_b_t": ps_b, "psp_peak_b_t": psp_b, "ps_core_loss_w": ps_core_loss, "psp_core_loss_w": psp_core_loss, "relative_b_difference": _relative(ps_b, psp_b), "relative_loss_difference": _relative(ps_core_loss, psp_core_loss), "tolerance": 0.01},
        },
    ])
    report["database_selection"] = {"material": request["core"]["material"], "shape": request["core"]["shape"], "bobbin": request["bobbin"], "wire": wire.wire_id}
    report["runtime"] = provider.status()
    report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
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
