"""Run the Phase 4A leakage models and a real OpenMagnetics comparison."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.geometry import WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.leakage import LeakageInductanceService
from backend.app.providers.openmagnetics import OpenMagneticsProvider
from examples.phase3_geometry_joint import _core_from_database, _ok, _request


def _layout(provider: OpenMagneticsProvider, request: dict[str, Any], template: str, *, main_insulation_m: float = 0.00025, primary_segments: tuple[int, int] | None = None):
    core = _core_from_database(provider, request)
    wire_result = _ok(provider.find_wire_by_name(request["windings"][0]["wire"]), "wire lookup")
    record = wire_result["value"]
    wire = WireGeometry(record["name"], float(record["outer_diameter_m"]), float(record["conducting_diameter_m"]), number_conductors=int(record.get("number_conductors") or 1))
    specs = [
        WindingSpec("Primary", "primary", 20, wire),
        WindingSpec("Secondary", "secondary", 5, wire),
    ]
    layout = build_layout(
        core,
        specs,
        WindingLayout(template, ["P", "S"] if template == "PS" else ["P1", "S", "P2"], main_insulation_m=main_insulation_m),
        primary_segments=primary_segments,
        provenance={"data_status": "external_database", "synthetic": False, "demo_only": False, "engineering_approved": False},
    )
    return layout


def run() -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    report: dict[str, Any] = {"benchmark": "phase4a_leakage", "status": "running", "runtime": provider.status(), "cases": {}, "checks": []}
    if not provider.available:
        report["status"] = "unavailable"
        return report
    request = _request()
    service = LeakageInductanceService(provider)
    currents = {"Primary": 1.0, "Secondary": -4.0}
    for template in ("PS", "PSP"):
        layout = _layout(provider, request, template)
        native_model = "native_basic" if template == "PS" else "native_sectional"
        native = service.calculate(layout, model=native_model, currents_rms=currents, reference_port="primary")
        sectional = service.calculate(layout, model="native_sectional", currents_rms=currents, reference_port="primary")
        comparison = service.calculate(layout, model="openmagnetics_comparison", currents_rms=currents, reference_port="primary", frequency_hz=100000.0)
        report["cases"][template] = {
            "layout": layout.as_dict(),
            "currents_rms_signed_a": currents,
            "native": native,
            "sectional": sectional,
            "openmagnetics_comparison": comparison,
        }
    ps = report["cases"]["PS"]
    psp = report["cases"]["PSP"]
    report["checks"] = [
        {"name": "ps_basic_provider_independent", "passed": ps["native"]["status"] == "ok" and ps["sectional"]["status"] == "ok" and abs(ps["native"]["value"] - ps["sectional"]["value"]) <= max(abs(ps["native"]["value"]), 1e-30) * 1e-12},
        {"name": "psp_sectional_geometry_model", "passed": psp["native"]["status"] == "ok" and psp["native"]["value"] >= 0 and len(psp["native"]["zones"]) >= 3},
        {"name": "openmagnetics_ps_call", "passed": ps["openmagnetics_comparison"]["openmagnetics"].get("status") == "ok", "details": ps["openmagnetics_comparison"]["openmagnetics"]},
        {"name": "openmagnetics_psp_call", "passed": psp["openmagnetics_comparison"]["openmagnetics"].get("status") == "ok", "details": psp["openmagnetics_comparison"]["openmagnetics"]},
    ]
    report["model_boundary"] = {
        "reference_port": "primary",
        "short_circuit_assumption": "signed RMS currents satisfy sum(N_i I_i)=0",
        "energy_convention": "period-average W_sigma from RMS field; L=2W_sigma/I_ref_rms^2",
        "not_claimed": ["3-D end leakage", "different-height winding end fields", "FEM or measured engineering accuracy"],
    }
    report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".runtime/phase4a-leakage-benchmark.json"))
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks", []), "values": {key: {"native_h": value["native"].get("value"), "openmagnetics_h": value["openmagnetics_comparison"].get("openmagnetics", {}).get("value")} for key, value in report.get("cases", {}).items()}}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
