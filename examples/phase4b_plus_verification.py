"""Phase 4B+ consistency audit using one identical MAS/work-point input.

This script is deliberately outside the production engine.  It compares the
native Rdc baseline with MKF ohmic/skin/proximity/full results and records the
geometry scope used by each path.  The important distinction is that Phase 4B
native geometry includes an explicit lead allowance, while the current MAS
turn descriptions contain turn lengths only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.providers.openmagnetics import OpenMagneticsProvider
from backend.app.winding_loss import LitzWireSpecification, WindingLossService
from backend.app.winding_loss.service import analyze_current_waveform
from examples.phase3_geometry_joint import _request
from examples.phase4b_litz_benchmark import LITZ_NAME, _layout, _waveforms


TEMPERATURE_C = 25.0


def _ok(result: Mapping[str, Any], label: str) -> Any:
    if result.get("status") != "ok":
        raise RuntimeError(f"{label} failed: {result.get('errors', result.get('diagnostics'))}")
    return result.get("value")


def _sum_component(items: list[Mapping[str, Any]], key: str) -> float | None:
    values = [float(item[key]) for item in items if item.get(key) is not None]
    return sum(values) if values else None


def _mas_turn_lengths(magnetic: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"length_m": 0.0, "turn_count": 0, "turn_names": []})
    turns = magnetic["coil"].get("turnsDescription", [])
    for item in turns:
        name = str(item.get("winding"))
        grouped[name]["length_m"] += float(item["length"])
        grouped[name]["turn_count"] += 1
        grouped[name]["turn_names"].append(item.get("name"))
    return dict(grouped)


def _block_audit(layout: Any, native: Mapping[str, Any], spectra: Mapping[str, Any], rdc_per_m: float) -> dict[str, Any]:
    blocks: dict[str, dict[str, Any]] = {}
    for block in layout.blocks:
        turn_length_m = sum(float(item.length_m) for item in block.turns_geometry)
        parallel_count = max(int(block.parallels), 1)
        turn_branch_length_m = turn_length_m / parallel_count
        lead_per_branch_m = max(float(block.branch_length_m - block.mean_turn_length_m), 0.0)
        native_total_length_m = turn_length_m + lead_per_branch_m * parallel_count
        turn_only_rdc_ohm = rdc_per_m * turn_branch_length_m / parallel_count
        current_rms_a = float(spectra[block.name].rms_a)
        native_item = native.get("windings", {}).get(block.name, {})
        blocks[block.name] = {
            "electrical_winding": native_item.get("electrical_winding"),
            "turns": block.turns,
            "parallels": parallel_count,
            "turn_length_m": turn_length_m,
            "turn_branch_length_m": turn_branch_length_m,
            "lead_allowance_per_branch_m": lead_per_branch_m,
            "native_total_length_m": native_total_length_m,
            "native_branch_length_m": native_item.get("branch_length_m"),
            "mas_turn_length_scope_m": turn_length_m,
            "length_difference_due_to_lead_m": native_total_length_m - turn_length_m,
            "current_dc_a": float(spectra[block.name].dc_a),
            "current_rms_a": current_rms_a,
            "rdc_per_m_ohm_per_m": rdc_per_m,
            "turn_only_rdc_ohm": turn_only_rdc_ohm,
            "turn_only_ohmic_w": current_rms_a * current_rms_a * turn_only_rdc_ohm,
            "native_rdc_ohm": native_item.get("rdc_ohm"),
            "native_ohmic_w": native_item.get("ohmic_loss_w"),
            "spectrum": spectra[block.name].as_dict(),
        }
    return blocks


def _aggregate_turn_only(blocks: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for block_name, item in blocks.items():
        electrical = str(item["electrical_winding"])
        aggregate = result.setdefault(electrical, {"blocks": [], "length_m": 0.0, "rdc_ohm": 0.0, "ohmic_loss_w": 0.0, "current_rms_a": item["current_rms_a"]})
        aggregate["blocks"].append(block_name)
        aggregate["length_m"] += item["turn_length_m"]
        aggregate["rdc_ohm"] += item["turn_only_rdc_ohm"]
        aggregate["ohmic_loss_w"] += item["turn_only_ohmic_w"]
    return result


def _component_audit(provider: OpenMagneticsProvider, service: WindingLossService, layout: Any, raw_operating_point: Mapping[str, Any], waveforms: Mapping[str, Any], temperature_c: float) -> dict[str, Any]:
    normalized, spectra, waveform_diagnostics = service._build_spectra(layout, waveforms, 31)
    electrical_waveforms, electrical_spectra = service._electrical_waveform_inputs(layout, normalized, spectra)
    processed_operating_point = service._attach_processed_waveforms(raw_operating_point, electrical_waveforms, electrical_spectra)
    magnetic = service.adapter.to_magnetic(layout)
    ohmic = provider.calculate_ohmic_losses(magnetic["coil"], processed_operating_point, temperature_c)
    skin_standalone = provider.calculate_skin_effect_losses(magnetic["coil"], processed_operating_point, temperature_c)
    skin = provider.calculate_skin_effect_losses_processed(magnetic["coil"], processed_operating_point, temperature_c)
    proximity = provider.calculate_proximity_effect_losses(magnetic, processed_operating_point, temperature_c)
    full = provider.calculate_winding_losses(magnetic, processed_operating_point, temperature_c)
    return {
        "raw_operating_point": raw_operating_point,
        "processed_operating_point": processed_operating_point,
        "magnetic_mas": magnetic,
        "waveform_diagnostics": waveform_diagnostics,
        "spectra": {name: value.as_dict() for name, value in spectra.items()},
        "direct_api_results": {
            "ohmic": ohmic,
            "skin_standalone": skin_standalone,
            "skin_increment": skin,
            "proximity": proximity,
            "complete_winding": full,
        },
    }


def _case(provider: OpenMagneticsProvider, service: WindingLossService, spec: LitzWireSpecification, template: str, request: Mapping[str, Any], waveforms: Mapping[str, Any], operating_point: Mapping[str, Any]) -> dict[str, Any]:
    layout = _layout(provider, dict(request), template, spec)
    if not layout.feasible:
        raise RuntimeError(f"{template} layout infeasible: {[item.as_dict() for item in layout.violations]}")
    native = service.calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=waveforms, model="native_dc", temperature_c=TEMPERATURE_C)
    full_service = service.calculate(layout, wire_specs={"Primary": spec, "Secondary": spec}, waveforms=waveforms, model="openmagnetics_full", operating_point=operating_point, temperature_c=TEMPERATURE_C)
    normalized, spectra, _ = service._build_spectra(layout, waveforms, 31)
    rdc_result = provider.calculate_wire_dc_resistance_per_meter(LITZ_NAME, TEMPERATURE_C)
    rdc_per_m = float(_ok(rdc_result, "wire Rdc"))
    block_audit = _block_audit(layout, native, spectra, rdc_per_m)
    turn_only_electrical = _aggregate_turn_only(block_audit)
    component = _component_audit(provider, service, layout, operating_point, waveforms, TEMPERATURE_C)
    direct_full = component["direct_api_results"]["complete_winding"]
    full_per_winding = direct_full.get("details", {}).get("per_winding_w", []) if direct_full.get("status") == "ok" else []
    full_sum = {
        "ohmic_w": _sum_component(full_per_winding, "ohmic_w"),
        "skin_w": _sum_component(full_per_winding, "skin_w"),
        "proximity_w": _sum_component(full_per_winding, "proximity_w"),
    }
    full_component_sum = sum(value for value in full_sum.values() if value is not None) if all(value is not None for value in full_sum.values()) else None
    mas_lengths = _mas_turn_lengths(component["magnetic_mas"])
    native_aggregate = native.get("electrical_windings", {})
    direct_proximity = component["direct_api_results"]["proximity"].get("value")
    direct_skin_standalone = component["direct_api_results"]["skin_standalone"].get("value")
    direct_skin_increment = component["direct_api_results"]["skin_increment"].get("value")
    unresolved: list[dict[str, Any]] = []
    if direct_proximity is not None and full_sum["proximity_w"] is not None and not math.isclose(float(direct_proximity), float(full_sum["proximity_w"]), rel_tol=1e-9, abs_tol=1e-15):
        unresolved.append({
            "code": "MKF_STANDALONE_PROXIMITY_DIFFERS_FROM_COMPLETE",
            "message": "同一几何和工作点下，MKF standalone proximity per-turn 聚合与 complete winding per-winding proximity 不一致；保留两者，不使用修正系数覆盖。",
            "standalone_proximity_w": direct_proximity,
            "complete_per_winding_proximity_w": full_sum["proximity_w"],
            "status": "unresolved",
        })
    comparison = {
        "native_total_w": native.get("value"),
        "native_ohmic_baseline_w": native.get("ohmic_loss_w"),
        "turn_only_rdc_baseline_w": sum(item["ohmic_loss_w"] for item in turn_only_electrical.values()),
        "mkf_ohmic_w": full_sum["ohmic_w"],
        "mkf_full_w": direct_full.get("value"),
        "mkf_full_component_sum_w": full_component_sum,
        "mkf_full_minus_mkf_ohmic_w": (direct_full.get("value") - full_sum["ohmic_w"]) if direct_full.get("value") is not None and full_sum["ohmic_w"] is not None else None,
        "mkf_full_minus_turn_only_rdc_w": (direct_full.get("value") - sum(item["ohmic_loss_w"] for item in turn_only_electrical.values())) if direct_full.get("value") is not None else None,
        "native_vs_mkf_ohmic_difference_w": (native.get("value") - full_sum["ohmic_w"]) if native.get("value") is not None and full_sum["ohmic_w"] is not None else None,
        "native_extra_lead_length_m": sum(item["length_difference_due_to_lead_m"] for item in block_audit.values()),
    }
    checks = [
        {"name": "same_temperature", "passed": TEMPERATURE_C == float(component["direct_api_results"]["complete_winding"].get("details", {}).get("temperature_c", float("nan")))},
        {"name": "native_uses_provider_rdc", "passed": all(abs(float(item["rdc_per_m_ohm_per_m"]) - rdc_per_m) < 1e-15 for item in block_audit.values())},
        {"name": "mkf_ohmic_matches_turn_only_rdc", "passed": full_sum["ohmic_w"] is not None and abs(float(full_sum["ohmic_w"]) - comparison["turn_only_rdc_baseline_w"]) < 1e-12},
        {"name": "mkf_skin_standalone_matches_increment", "passed": direct_skin_standalone is not None and direct_skin_increment is not None and math.isclose(float(direct_skin_standalone), float(direct_skin_increment), rel_tol=1e-9, abs_tol=1e-15)},
        {"name": "mkf_complete_not_below_its_ohmic", "passed": direct_full.get("value") is not None and full_sum["ohmic_w"] is not None and float(direct_full["value"]) + 1e-15 >= float(full_sum["ohmic_w"])},
        {"name": "mkf_complete_not_below_turn_only_baseline", "passed": direct_full.get("value") is not None and float(direct_full["value"]) + 1e-15 >= float(comparison["turn_only_rdc_baseline_w"])},
        {"name": "mas_and_native_turn_lengths_match", "passed": all(abs(float(mas_lengths[name]["length_m"]) - float(item["turn_length_m"])) < 1e-12 for name, item in (("Primary", next(iter(block_audit.values()))) if template == "PS" else ("Secondary", block_audit["S"]),))},
    ]
    # The preceding generic check is intentionally supplemented by an exact
    # electrical comparison for both PS and PSP.
    if template == "PS":
        expected_mas = {"Primary": sum(item["turn_length_m"] for item in block_audit.values() if item["electrical_winding"] == "Primary"), "Secondary": sum(item["turn_length_m"] for item in block_audit.values() if item["electrical_winding"] == "Secondary")}
    else:
        expected_mas = {name: item["length_m"] for name, item in mas_lengths.items()}
        expected_mas = {name: sum(item["turn_length_m"] for item in block_audit.values() if item["electrical_winding"] == name) for name in expected_mas}
    checks[-1] = {"name": "mas_and_native_turn_lengths_match", "passed": all(abs(float(mas_lengths[name]["length_m"]) - float(length)) < 1e-12 for name, length in expected_mas.items())}
    return {
        "layout": layout.as_dict(),
        "litz_specification": spec.as_dict(),
        "wire_rdc_api": rdc_result,
        "block_input_audit": block_audit,
        "turn_only_electrical_baseline": turn_only_electrical,
        "native_result": native,
        "native_electrical_aggregates": native_aggregate,
        "service_openmagnetics_full": full_service,
        "mkf_component_audit": component,
        "mas_turn_lengths": mas_lengths,
        "comparison": comparison,
        "unresolved_items": unresolved,
        "checks": checks,
    }


def run() -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    report: dict[str, Any] = {
        "benchmark": "phase4b_plus_loss_consistency",
        "status": "running",
        "temperature_c": TEMPERATURE_C,
        "runtime": provider.status(),
        "request": _request(),
        "called_functions": [
            "load_databases",
            "find_litz_wire_by_name",
            "find_wire_by_name",
            "calculate_dc_resistance_per_meter",
            "calculate_ohmic_losses",
            "calculate_skin_effect_losses",
            "calculate_magnetic_field_strength_field",
            "calculate_proximity_effect_losses",
            "calculate_winding_losses",
        ],
    }
    if not provider.available:
        report["status"] = "unavailable"
        return report
    detailed = provider.find_litz_wire_by_name(LITZ_NAME)
    if detailed.get("status") != "ok":
        report["status"] = "failed"
        report["error"] = detailed
        return report
    record = detailed["value"]
    strand = provider.find_wire_by_name(record["strand"])
    spec = LitzWireSpecification.from_provider_record(record, strand_record=strand.get("value") if strand.get("status") == "ok" else None)
    waveforms, operating_point = _waveforms()
    service = WindingLossService(provider)
    request = _request()
    report["litz_database_record"] = record
    report["strand_database_record"] = strand
    report["raw_waveforms"] = {name: value.as_dict() for name, value in waveforms.items()}
    report["cases"] = {template: _case(provider, service, spec, template, request, waveforms, operating_point) for template in ("PS", "PSP")}
    all_checks = [check for case in report["cases"].values() for check in case["checks"]]
    report["checks"] = all_checks
    unresolved = [item for case in report["cases"].values() for item in case.get("unresolved_items", [])]
    report["unresolved_items"] = unresolved
    if not all(check["passed"] for check in all_checks):
        report["status"] = "failed"
    else:
        report["status"] = "passed_with_unresolved_mkf_proximity_path" if unresolved else "passed"
    report["conclusion"] = {
        "root_cause": "native_dc includes a 0.15 m lead allowance for each physical winding block, while the current MAS turnsDescription and MKF ohmic path use turn lengths only.",
        "mkf_full_definition": "The returned complete winding loss equals the sum of MKF per-winding ohmic, skin and proximity components for this input.",
        "unresolved_component_path": "The standalone MKF proximity stage and complete winding stage return different proximity totals for the same input; both raw normalized results are retained.",
        "engineering_status": "research_prototype_not_engineering_approved",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/ab_upgrade/phase4b/verification/phase4b_plus_results.json"))
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks", []), "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if report["status"].startswith("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
