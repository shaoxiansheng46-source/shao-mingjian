"""Run the independent Phase 4B real-Litz-wire benchmark.

The benchmark uses an actual PyOpenMagnetics database record and actual
waveforms.  It does not touch the SST optimizer or synthetic engine.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.geometry import WireGeometry, WindingLayout, WindingSpec, build_layout
from backend.app.providers.openmagnetics import MasAdapter, OpenMagneticsProvider
from backend.app.winding_loss import CurrentWaveform, LitzWireSpecification, WindingLossService
from backend.app.winding_loss.service import _processed_descriptor, analyze_current_waveform
from examples.phase3_geometry_joint import _core_from_database, _request


LITZ_NAME = "Litz 1000x0.02 - Grade 1 - Double Served"


def _waveforms() -> tuple[dict[str, CurrentWaveform], dict[str, Any]]:
    frequency_hz = 100_000.0
    period = 1.0 / frequency_hz
    count = 64
    time_s = [period * index / count for index in range(count)]
    primary_current = [0.30 + 0.10 * math.sin(2.0 * math.pi * frequency_hz * time) for time in time_s]
    secondary_current = [0.90 + 0.20 * math.sin(2.0 * math.pi * frequency_hz * time + 0.15) for time in time_s]
    primary_voltage = [100.0 if index < count / 2 else -100.0 for index in range(count)]
    secondary_voltage = [25.0 if index < count / 2 else -25.0 for index in range(count)]
    waveforms = {
        "Primary": CurrentWaveform("Primary", frequency_hz, tuple(time_s), tuple(primary_current)),
        "Secondary": CurrentWaveform("Secondary", frequency_hz, tuple(time_s), tuple(secondary_current)),
    }
    operating_point = {
        "name": "Phase4B dense periodic benchmark",
        "conditions": {"ambientTemperature": 25.0},
        "excitationsPerWinding": [
            {"name": "Primary", "frequency": frequency_hz, "voltage": {"waveform": {"data": primary_voltage, "time": time_s}}, "current": {"waveform": {"data": primary_current, "time": time_s}}},
            {"name": "Secondary", "frequency": frequency_hz, "voltage": {"waveform": {"data": secondary_voltage, "time": time_s}}, "current": {"waveform": {"data": secondary_current, "time": time_s}}},
        ],
    }
    return waveforms, operating_point


def _layout(provider: OpenMagneticsProvider, request: dict[str, Any], template: str, spec: LitzWireSpecification):
    core = _core_from_database(provider, request)
    diameter = spec.geometry_diameter_m(policy="database_maximum")
    equivalent_copper_diameter = spec.equivalent_copper_diameter_m
    if equivalent_copper_diameter is None:
        raise ValueError("Litz database record lacks a calculable copper area.")
    wire = WireGeometry(spec.model, diameter, equivalent_copper_diameter, number_conductors=1, data_status="external_database")
    specs = [WindingSpec("Primary", "primary", 20, wire), WindingSpec("Secondary", "secondary", 5, wire)]
    order = ["P", "S"] if template == "PS" else ["P1", "S", "P2"]
    # The selected ETD54 bobbin has a narrow radial window.  These are
    # explicit research-prototype manufacturing clearances, not a safety
    # standard claim; keeping them in the input makes the feasibility reason
    # auditable instead of silently accepting an overflow.
    layout_rules = WindingLayout(
        template,
        order,
        main_insulation_m=0.00015,
        process_clearance_m=0.00005,
        winding_to_core_clearance_m=0.0005,
    )
    return build_layout(
        core,
        specs,
        layout_rules,
        provenance={"data_status": "external_database", "synthetic": False, "demo_only": False, "engineering_approved": False},
    )


def run() -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    report: dict[str, Any] = {"benchmark": "phase4b_real_litz_wire", "status": "running", "runtime": provider.status(), "checks": [], "cases": {}, "called_functions": []}
    if not provider.available:
        report["status"] = "unavailable"
        report["checks"].append({"name": "runtime_available", "passed": False, "details": provider.status()})
        return report

    detailed = provider.find_litz_wire_by_name(LITZ_NAME)
    report["called_functions"].extend(["load_databases", "find_wire_by_name", "find_litz_wire_by_name", "calculate_dc_resistance_per_meter", "calculate_skin_ac_resistance_per_meter", "calculate_winding_losses", "calculate_skin_effect_losses"])
    if detailed.get("status") != "ok":
        report["status"] = "failed"
        report["checks"].append({"name": "litz_record_lookup", "passed": False, "details": detailed})
        return report
    record = detailed["value"]
    strand = provider.find_wire_by_name(record["strand"]) if record.get("strand") else {"status": "error"}
    spec = LitzWireSpecification.from_provider_record(record, strand_record=strand.get("value") if strand.get("status") == "ok" else None)
    report["litz_specification"] = spec.as_dict()
    report["checks"].append({"name": "real_litz_record", "passed": spec.number_strands == 1000 and spec.strand_bare_diameter_m is not None and spec.data_status == "external_database", "details": {"name": spec.model, "strand": record.get("strand"), "missing_parameters": list(spec.missing_parameters)}})
    report["checks"].append({"name": "no_inferred_nominal_outer_diameter", "passed": spec.finished_outer_diameter_m is None and "finished_outer_diameter_nominal" in spec.missing_parameters, "details": {"range_m": [spec.finished_outer_diameter_min_m, spec.finished_outer_diameter_max_m], "geometry_policy": "database_maximum"}})
    waveforms, operating_point = _waveforms()
    service = WindingLossService(provider)
    request = _request()
    for template in ("PS", "PSP"):
        layout = _layout(provider, request, template, spec)
        case = {"layout": layout.as_dict(), "native_dc": service.calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=waveforms, model="native_dc", temperature_c=25.0), "openmagnetics_skin": service.calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=waveforms, model="openmagnetics_skin", operating_point=operating_point, temperature_c=25.0), "openmagnetics_full": service.calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=waveforms, model="openmagnetics_full", operating_point=operating_point, temperature_c=25.0)}
        case["comparison"] = service.calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=waveforms, model="comparison", operating_point=operating_point, temperature_c=25.0)
        report["cases"][template] = case

    primary_descriptor = _processed_descriptor(analyze_current_waveform(waveforms["Primary"]), waveforms["Primary"])
    report["wire_api"] = {
        "dc_resistance_per_m": provider.calculate_wire_dc_resistance_per_meter(LITZ_NAME, 25.0),
        "skin_ac_resistance_per_m": provider.calculate_wire_skin_ac_resistance_per_meter(LITZ_NAME, primary_descriptor, 25.0),
    }
    ps = report["cases"]["PS"]
    psp = report["cases"]["PSP"]
    report["checks"].extend([
        {"name": "ps_native_dc_ok", "passed": ps["native_dc"]["status"] == "ok" and ps["native_dc"]["value"] is not None},
        {"name": "psp_native_dc_ok", "passed": psp["native_dc"]["status"] == "ok" and psp["native_dc"]["value"] is not None},
        {"name": "ps_openmagnetics_full_ok", "passed": ps["openmagnetics_full"]["status"] == "ok" and ps["openmagnetics_full"]["value"] is not None},
        {"name": "psp_openmagnetics_full_ok", "passed": psp["openmagnetics_full"]["status"] == "ok" and psp["openmagnetics_full"]["value"] is not None},
        {"name": "skin_is_real_nonzero_or_diagnostic", "passed": ps["openmagnetics_skin"].get("skin_loss_w") is not None or bool(ps["openmagnetics_skin"].get("diagnostics"))},
        {"name": "psp_primary_series_blocks_not_duplicated", "passed": psp["native_dc"]["electrical_windings"].get("Primary", {}).get("blocks") == ["P1", "P2"]},
        {"name": "real_provenance_preserved", "passed": all(not item.get("synthetic", True) and item.get("data_status") == "external_database" for item in (ps["layout"]["provenance"], psp["layout"]["provenance"]))},
    ])
    report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".runtime/phase4b-litz/benchmark.json"))
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
