"""Run the Phase 5A unified candidate evaluation without the optimizer.

The fixture is deliberately marked ``demo_only``/``synthetic``.  It exercises
the actual Phase 3 geometry, Phase 4A leakage and Phase 4B winding-loss
services through one candidate and one operating-point snapshot.  OpenMagnetics
is optional and is reported as unavailable when the isolated package is not
installed; no value is substituted in that case.
"""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation import EvaluationCandidate, EvaluationContext, OperatingPointSnapshot, UnifiedEvaluationService
from backend.app.geometry import CoreGeometry, WireGeometry, WindingSpec, build_layout
from backend.app.providers.openmagnetics import OpenMagneticsProvider
from backend.app.geometry import JointCalculationService
from backend.app.winding_loss import CurrentWaveform, LitzWireSpecification

DATA_ROOT = ROOT / "SST_V1_4_Demo_Data"


def _load_demo_records() -> tuple[dict, dict]:
    cores = json.loads((DATA_ROOT / "core_geometry_library.json").read_text(encoding="utf-8"))
    wires = json.loads((DATA_ROOT / "litz_library.json").read_text(encoding="utf-8"))
    return ({item["id"]: item for item in cores}, {item["id"]: item for item in wires})


def _demo_snapshot(cores: dict, wires: dict) -> dict:
    names = ["core_geometry_library.json", "litz_library.json"]
    return {
        "data_version": "demo-package-1.4+phase5a-local-adapter",
        "data_hashes": {name: hashlib.sha256((DATA_ROOT / name).read_bytes()).hexdigest() for name in names},
        "record_counts": {"cores": len(cores), "wires": len(wires)},
    }


def _candidate(cores: dict, wires: dict, snapshot: dict) -> EvaluationCandidate:
    core_record = cores["DEMO_CORE_L"]
    wire_record = wires["DEMO_LITZ_2000x0p1"]
    core = CoreGeometry(
        core_id=core_record["id"],
        shape_name=core_record["core_family"],
        material_name=core_record["material_id"],
        physical_dimensions_m={"outer_width_m": core_record["core_outer_mm"][0] * 1e-3, "outer_height_m": core_record["core_outer_mm"][1] * 1e-3, "outer_depth_m": core_record["core_outer_mm"][2] * 1e-3},
        effective_area_m2=core_record["Ae_mm2"] * 1e-6,
        effective_length_m=core_record["le_mm"] * 1e-3,
        effective_volume_m3=core_record["Ve_mm3"] * 1e-9,
        window_width_m=core_record["window_width_mm"] * 1e-3,
        window_height_m=core_record["window_height_mm"] * 1e-3,
        winding_column_width_m=core_record["leg_width_mm"] * 1e-3,
        winding_column_depth_m=core_record["leg_depth_mm"] * 1e-3,
        bobbin_wall_m=core_record["bobbin_wall_mm"] * 1e-3,
        gap_m=0.0,
        mass_kg=core_record["mass_kg"],
        data_status=core_record["data_status"],
        synthetic=True,
        demo_only=True,
        engineering_approved=False,
    )
    wire = WireGeometry(
        wire_id=wire_record["id"],
        outer_diameter_m=wire_record["outer_diameter_mm"] * 1e-3,
        conducting_diameter_m=wire_record["strand_bare_diameter_mm"] * 1e-3,
        resistance_ohm_per_m=wire_record["Rdc_ohm_per_m_20C"],
        diameter_tolerance_m=wire_record["outer_dimension_tolerance_mm"] * 1e-3,
        number_conductors=wire_record["strand_count"],
        data_status=wire_record["data_status"],
        synthetic=True,
        demo_only=True,
        engineering_approved=False,
    )
    layout = build_layout(
        core,
        [WindingSpec("Primary", "primary", 20, wire), WindingSpec("Secondary", "secondary", 5, wire)],
        "PS",
        provenance={
            "data_status": "synthetic",
            "synthetic": True,
            "demo_only": True,
            "engineering_approved": False,
            "source": core_record["source"],
        },
    )
    litz = LitzWireSpecification(
        manufacturer="synthetic demo record",
        model=wire_record["id"],
        data_source=wire_record["source"],
        strand_bare_diameter_m=wire_record["strand_bare_diameter_mm"] * 1e-3,
        strand_insulated_diameter_m=wire_record["strand_insulated_diameter_mm"] * 1e-3,
        number_strands=wire_record["strand_count"],
        finished_outer_diameter_m=wire_record["outer_diameter_mm"] * 1e-3,
        finished_outer_diameter_min_m=(wire_record["outer_diameter_mm"] - wire_record["outer_dimension_tolerance_mm"]) * 1e-3,
        finished_outer_diameter_max_m=(wire_record["outer_diameter_mm"] + wire_record["outer_dimension_tolerance_mm"]) * 1e-3,
        conductor_material="synthetic_copper",
        conductor_area_m2=wire_record["copper_area_mm2"] * 1e-6,
        nominal_dc_resistance_ohm_per_m=wire_record["Rdc_ohm_per_m_20C"],
        data_status="synthetic",
        synthetic=True,
        demo_only=True,
        engineering_approved=False,
        metadata={"source_record_id": wire_record["id"]},
    )
    return EvaluationCandidate(
        layout=layout,
        wire_specs={"Primary": litz, "Secondary": litz},
        data_snapshot=snapshot,
        record_ids={"core": core_record["id"], "material": core_record["material_id"], "wire": wire_record["id"]},
    )


def _operating_point() -> OperatingPointSnapshot:
    frequency = 20_000.0
    period = 1.0 / frequency
    times = tuple(period * index / 32.0 for index in range(33))
    primary_voltage = tuple(800.0 if index < 16 else -800.0 for index in range(33))
    secondary_voltage = tuple(400.0 if index < 16 else -400.0 for index in range(33))
    return OperatingPointSnapshot(
        point_id="rated",
        voltage_primary_v=800.0,
        voltage_secondary_v=400.0,
        power_w=1000.0,
        frequency_hz=frequency,
        ambient_c=40.0,
        currents_rms_a={"Primary": 1.0, "Secondary": -4.0},
        current_waveforms={
            "Primary": CurrentWaveform("Primary", frequency, times, tuple(1.0 for _ in times)),
            "Secondary": CurrentWaveform("Secondary", frequency, times, tuple(-4.0 for _ in times)),
        },
        voltage_waveforms={
            "Primary": {"data": list(primary_voltage), "time": list(times), "frequency": frequency},
            "Secondary": {"data": list(secondary_voltage), "time": list(times), "frequency": frequency},
        },
    )


def main() -> dict:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cores, wires = _load_demo_records()
    snapshot = _demo_snapshot(cores, wires)
    candidate = _candidate(cores, wires, snapshot)
    provider = OpenMagneticsProvider()
    service = UnifiedEvaluationService(joint_service=JointCalculationService(provider))
    result = service.evaluate(
        candidate,
        _operating_point(),
        context=EvaluationContext(
            data_snapshot=snapshot,
            provider="hybrid",
            provider_provenance=provider.status()["provenance"],
            constraints={
                "current_density_A_per_mm2": {"primary_max": 3.0, "secondary_max": 3.0},
                "series_inductance_H": {"target": 2e-5, "relative_tolerance": 0.5},
            },
        ),
        include_openmagnetics=True,
    )
    result["benchmark"] = "phase5a_unified_evaluation"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
