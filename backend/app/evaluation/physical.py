"""Phase 5D web-workbench adapter for one physical candidate.

This module is deliberately an orchestration boundary.  It converts the
small, JSON-safe request used by the web UI into the Phase 3 geometry model
and the Phase 5A snapshots, then delegates all calculations to the existing
services.  It never falls back from an external database to the synthetic
fixture without an explicit ``data_source=demo_fixture`` selection.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any

from ..geometry import (
    CoreGeometry,
    JointCalculationService,
    WireGeometry,
    WindingSpec,
    build_layout,
)
from ..providers.openmagnetics import OpenMagneticsProvider
from ..winding_loss import CurrentWaveform, LitzWireSpecification, WindingLossService
from .models import EvaluationCandidate, EvaluationContext, OperatingPointSnapshot, canonical_hash
from .service import UnifiedEvaluationService


PHYSICAL_API_VERSION = "sst-phase5d-physical-workbench-0.1.0"
PHYSICAL_MODEL_VERSION = "sst-phase5d-unified-web-evaluation-0.1.0"


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, Mapping):
        for key in ("nominal", "maximum", "minimum"):
            if value.get(key) is not None:
                return float(value[key])
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mm(value: Any, default: float | None = None) -> float | None:
    number = _number(value, default)
    return None if number is None else number * 1e-3


def _diagnostic(code: str, message: str, *, field: str | None = None, severity: str = "error") -> dict[str, Any]:
    return {"code": code, "message": message, "field": field, "severity": severity}


def provider_catalog(provider: OpenMagneticsProvider, kind: str, query: str = "", limit: int = 25) -> dict[str, Any]:
    """Return a filtered, normalized third-party catalog; never raw PyOM data."""

    if kind == "materials":
        result = provider.get_core_materials()
    elif kind == "cores":
        result = provider.get_core_shapes()
    elif kind == "wires":
        result = provider.get_wires()
    else:
        return {"status": "error", "items": [], "count": 0, "errors": [_diagnostic("UNKNOWN_CATALOG", f"未知数据库类型 {kind}。")], "provenance": {}}
    needle = query.strip().lower()
    items = result.get("items", []) if isinstance(result, Mapping) else []
    if needle:
        items = [item for item in items if needle in str(item.get("name", "")).lower() or needle in str(item.get("manufacturer", "")).lower()]
    result = dict(result)
    result["items"] = items[: max(1, min(int(limit), 100))]
    result["returned_count"] = len(result["items"])
    return result


def _synthetic_core(request: Mapping[str, Any], db: Mapping[str, Mapping[str, Any]]) -> tuple[CoreGeometry, dict[str, Any]]:
    selection = request.get("core") if isinstance(request.get("core"), Mapping) else {}
    core_id = str(selection.get("core_id", "DEMO_CORE_XL"))
    core = db["cores"].get(core_id)
    if not core:
        raise ValueError(f"UNKNOWN_SYNTHETIC_CORE:{core_id}")
    material = db["materials"].get(core["material_id"], {})
    gap_m = _mm(selection.get("gap_mm", 0.0), 0.0) or 0.0
    geometry = CoreGeometry(
        core_id=core_id,
        shape_name=str(core.get("core_family", "DEMO_RECT_FRAME")),
        material_name=str(material.get("id", core.get("material_id", "unknown"))),
        physical_dimensions_m={f"outer_{index}_m": float(value) * 1e-3 for index, value in enumerate(core.get("core_outer_mm", []))},
        effective_area_m2=float(core["Ae_mm2"]) * 1e-6,
        effective_length_m=float(core["le_mm"]) * 1e-3,
        effective_volume_m3=float(core["Ve_mm3"]) * 1e-9,
        window_width_m=float(core["window_width_mm"]) * 1e-3,
        window_height_m=float(core["window_height_mm"]) * 1e-3,
        winding_column_width_m=float(core.get("leg_width_mm", core["window_width_mm"])) * 1e-3,
        winding_column_depth_m=float(core.get("leg_depth_mm", core["window_width_mm"])) * 1e-3,
        bobbin_wall_m=float(core.get("bobbin_wall_mm", 0.0)) * 1e-3,
        bobbin_id=f"{core_id}-synthetic-bobbin",
        gap_m=gap_m,
        stack_count=int(selection.get("stack_count", core.get("quantity", 1))),
        mass_kg=float(core.get("mass_kg")) if core.get("mass_kg") is not None else None,
        data_status="synthetic",
        synthetic=True,
        demo_only=True,
        engineering_approved=False,
    )
    return geometry, core


def _external_core(request: Mapping[str, Any], provider: OpenMagneticsProvider) -> tuple[CoreGeometry, dict[str, Any]]:
    selection = request.get("core") if isinstance(request.get("core"), Mapping) else {}
    shape_name = str(selection.get("shape_name", "ETD 54/28/19"))
    material_name = str(selection.get("material_name", "3C95"))
    bobbin_name = str(selection.get("bobbin_name", "Bobbin ETD 54"))
    gap_m = _mm(selection.get("gap_mm", 0.1), 0.1e-3) or 0.0
    stacks = int(selection.get("stack_count", 1))
    core_request = {"functionalDescription": {"type": "two-piece set", "shape": shape_name, "material": material_name, "gapping": ([{"type": "subtractive", "length": gap_m}] if gap_m > 0 else []), "numberStacks": stacks}}
    core_data = provider.calculate_core_data(core_request)
    shape_result = provider.find_core_shape_by_name(shape_name)
    bobbin_result = provider.find_bobbin_by_name(bobbin_name)
    if core_data.get("status") != "ok" or shape_result.get("status") != "ok" or bobbin_result.get("status") != "ok":
        raise ValueError(json_diagnostics("EXTERNAL_CORE_LOOKUP_FAILED", "真实磁芯、材料或骨架数据不可用。", core_data, shape_result, bobbin_result))
    shape = shape_result["value"]
    value = core_data["value"]
    processed = bobbin_result["value"].get("processed_description", {})
    windows = processed.get("winding_windows", [])
    if not windows:
        raise ValueError("EXTERNAL_BOBBIN_WINDOW_MISSING:真实骨架没有可用窗口尺寸。")
    window = windows[0]
    width = _number(window.get("width"))
    height = _number(window.get("height"))
    if width is None or height is None:
        raise ValueError("EXTERNAL_BOBBIN_WINDOW_INVALID:真实骨架窗口缺少 width/height。")
    dimensions: dict[str, float] = {}
    for key, item in (shape.get("dimensions_m") or {}).items():
        value_m = _number(item)
        if value_m is not None:
            dimensions[f"{key}_m"] = value_m
    geometry = CoreGeometry(
        core_id=shape_name,
        shape_name=shape_name,
        material_name=material_name,
        physical_dimensions_m=dimensions,
        effective_area_m2=float(value["effective_area_m2"]),
        effective_length_m=float(value["effective_length_m"]),
        effective_volume_m3=float(value["effective_volume_m3"]),
        window_width_m=float(width),
        window_height_m=float(height),
        winding_column_width_m=float(processed.get("column_width_m") or width),
        winding_column_depth_m=float(processed.get("column_depth_m") or width),
        bobbin_wall_m=float(processed.get("wall_thickness_m") or 0.0),
        bobbin_id=bobbin_name,
        gap_m=gap_m,
        stack_count=stacks,
        data_status="external_database",
        synthetic=False,
        demo_only=False,
        engineering_approved=False,
    )
    return geometry, {"shape": shape_result["value"], "core_data": core_data, "bobbin": bobbin_result["value"]}


def json_diagnostics(code: str, message: str, *results: Mapping[str, Any]) -> str:
    details = []
    for result in results:
        details.extend(result.get("errors", []) if isinstance(result, Mapping) else [])
    return f"{code}: {message} details={details}"


def _synthetic_wire(record: Mapping[str, Any]) -> tuple[WireGeometry, LitzWireSpecification]:
    area = float(record["copper_area_mm2"]) * 1e-6
    outer = float(record["outer_diameter_mm"]) * 1e-3
    rdc = float(record["Rdc_ohm_per_m_20C"])
    spec = LitzWireSpecification(
        manufacturer=None,
        model=str(record["id"]),
        data_source=str(record.get("source", "synthetic demo package")),
        strand_bare_diameter_m=float(record["strand_bare_diameter_mm"]) * 1e-3,
        strand_insulated_diameter_m=float(record["strand_insulated_diameter_mm"]) * 1e-3,
        number_strands=int(record["strand_count"]),
        twist_pitch_m=None,
        finished_outer_diameter_m=outer,
        conductor_material="copper",
        resistivity_ohm_m=rdc * area,
        resistivity_reference_temperature_c=float(record.get("reference_temperature_C", 20.0)),
        temperature_coefficient_per_c=float(record.get("copper_alpha_per_K", 0.00393)),
        nominal_dc_resistance_ohm_per_m=rdc,
        conductor_area_m2=area,
        missing_parameters=("twist_pitch_m",),
        data_status="synthetic",
        synthetic=True,
        demo_only=True,
        engineering_approved=False,
        metadata={"source_record": dict(record)},
    )
    wire = WireGeometry(
        wire_id=str(record["id"]),
        outer_diameter_m=outer,
        conducting_diameter_m=float(record["strand_bare_diameter_mm"]) * 1e-3,
        resistance_ohm_per_m=rdc,
        diameter_tolerance_m=float(record.get("outer_dimension_tolerance_mm", 0.0)) * 1e-3,
        number_conductors=int(record.get("strand_count", 1)),
        data_status="synthetic",
        synthetic=True,
        demo_only=True,
        engineering_approved=False,
    )
    return wire, spec


def _external_wire(name: str, provider: OpenMagneticsProvider) -> tuple[WireGeometry, LitzWireSpecification, dict[str, Any]]:
    result = provider.find_litz_wire_by_name(name)
    if result.get("status") != "ok":
        raise ValueError(json_diagnostics("EXTERNAL_WIRE_LOOKUP_FAILED", f"真实利兹线 {name} 不可用。", result))
    record = result["value"]
    strand_result = provider.find_wire_by_name(str(record.get("strand"))) if record.get("strand") else {"status": "error"}
    strand_record = strand_result.get("value", {}) if strand_result.get("status") == "ok" else {}
    outer = _number(record.get("outer_diameter_m")) or _number((record.get("outer_diameter_m") or {}).get("maximum"))
    conducting = _number(record.get("conducting_diameter_m")) or _number(strand_record.get("conducting_diameter_m"))
    count = record.get("number_conductors")
    if outer is None or conducting is None or count is None:
        raise ValueError("EXTERNAL_WIRE_GEOMETRY_MISSING:真实利兹线缺少成品外径、股径或股数。")
    spec = LitzWireSpecification.from_provider_record(record, strand_record=strand_record)
    wire = WireGeometry(
        wire_id=name,
        outer_diameter_m=float(outer),
        conducting_diameter_m=float(conducting),
        number_conductors=int(count),
        data_status="external_database",
        synthetic=False,
        demo_only=False,
        engineering_approved=False,
    )
    return wire, spec, record


def _waveform(name: str, value: Any) -> CurrentWaveform:
    if isinstance(value, CurrentWaveform):
        return value
    if not isinstance(value, Mapping):
        raise ValueError(f"INVALID_WAVEFORM:{name} 必须是对象。")
    return CurrentWaveform.from_mapping(name, value)


def _operating_point(request: Mapping[str, Any]) -> OperatingPointSnapshot:
    raw = request.get("operating_point") if isinstance(request.get("operating_point"), Mapping) else {}
    current_values = raw.get("currents_rms_a", {})
    current_waveforms_raw = raw.get("current_waveforms", {})
    voltage_waveforms = raw.get("voltage_waveforms", {})
    waveforms: dict[str, CurrentWaveform] = {}
    if isinstance(current_waveforms_raw, Mapping):
        for name, value in current_waveforms_raw.items():
            waveforms[str(name)] = _waveform(str(name), value)
    return OperatingPointSnapshot(
        point_id=str(raw.get("point_id", "web-nominal")),
        voltage_primary_v=float(raw.get("voltage_primary_v", 800.0)),
        voltage_secondary_v=float(raw.get("voltage_secondary_v", 400.0)),
        power_w=float(raw.get("power_w", 1000.0)),
        frequency_hz=float(raw.get("frequency_hz", 30000.0)),
        ambient_c=float(raw.get("ambient_c", 25.0)),
        currents_rms_a={str(key): float(value) for key, value in current_values.items()} if isinstance(current_values, Mapping) else {},
        current_waveforms=waveforms,
        voltage_waveforms=dict(voltage_waveforms) if isinstance(voltage_waveforms, Mapping) else {},
        topology=str(raw.get("topology", "DAB_SPS")),
        bridge_duty=float(raw.get("bridge_duty", 0.5)),
        reference_side=str(raw.get("reference_side", "primary")),
    )


def _empty_waveform_diagnostics(op: OperatingPointSnapshot) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for name in ("Primary", "Secondary"):
        if name not in op.current_waveforms:
            missing.append(_diagnostic("MISSING_CURRENT_WAVEFORM", f"缺少 {name} 电流波形；仍可查看几何检查。", field=f"operating_point.current_waveforms.{name}"))
        if name not in op.voltage_waveforms:
            missing.append(_diagnostic("MISSING_VOLTAGE_WAVEFORM", f"缺少 {name} 绕组端电压波形；不会由直流母线电压自动生成。", field=f"operating_point.voltage_waveforms.{name}"))
    return missing


def build_physical_evaluation(request: Mapping[str, Any], *, db: Mapping[str, Mapping[str, Any]], provider: OpenMagneticsProvider) -> dict[str, Any]:
    """Build and evaluate one web request through the existing Phase 5A service."""

    source = str(request.get("data_source", "external_database"))
    if source not in {"external_database", "demo_fixture"}:
        raise ValueError("UNKNOWN_DATA_SOURCE:只能选择 external_database 或 demo_fixture。")
    try:
        if source == "external_database":
            core, core_records = _external_core(request, provider)
            primary_wire, primary_spec, primary_record = _external_wire(str(request.get("wire", {}).get("primary_name", "Litz 1000x0.02 - Grade 1 - Double Served")), provider)
            secondary_name = str(request.get("wire", {}).get("secondary_name", primary_wire.wire_id))
            if secondary_name == primary_wire.wire_id:
                secondary_wire, secondary_spec, secondary_record = primary_wire, primary_spec, primary_record
            else:
                secondary_wire, secondary_spec, secondary_record = _external_wire(secondary_name, provider)
            snapshot = {"source": "OpenMagnetics database", "provider": provider.status(), "record_ids": {"core": core.core_id, "material": core.material_name, "primary_wire": primary_wire.wire_id, "secondary_wire": secondary_wire.wire_id}, "request_hash": canonical_hash(request)}
            provenance = {"data_status": "external_database", "synthetic": False, "demo_only": False, "engineering_approved": False}
            provider_name = "openmagnetics"
        else:
            from ..core.engine import data_snapshot
            core, core_record = _synthetic_core(request, db)
            primary_record = db["wires"].get(str(request.get("wire", {}).get("primary_name", "DEMO_LITZ_8000x0p1")))
            secondary_record = db["wires"].get(str(request.get("wire", {}).get("secondary_name", "DEMO_LITZ_8000x0p1")))
            if not primary_record or not secondary_record:
                raise ValueError("UNKNOWN_SYNTHETIC_WIRE:本地演示导线不存在。")
            primary_wire, primary_spec = _synthetic_wire(primary_record)
            secondary_wire, secondary_spec = _synthetic_wire(secondary_record)
            snapshot = data_snapshot(db)
            snapshot["request_hash"] = canonical_hash(request)
            provenance = {"data_status": "synthetic", "synthetic": True, "demo_only": True, "engineering_approved": False}
            provider_name = "native"

        selection = request.get("geometry") if isinstance(request.get("geometry"), Mapping) else {}
        layout_id = str(request.get("layout", "PS")).upper()
        np_turns = int(request.get("primary_turns", 20))
        ns_turns = int(request.get("secondary_turns", 5))
        primary_segments = request.get("primary_segments")
        segment_tuple = tuple(int(item) for item in primary_segments) if isinstance(primary_segments, (list, tuple)) and len(primary_segments) == 2 else None
        specs = [WindingSpec("Primary", "primary", np_turns, primary_wire, parallels=int(request.get("primary_parallels", 1)))]
        specs.append(WindingSpec("Secondary", "secondary", ns_turns, secondary_wire, parallels=int(request.get("secondary_parallels", 1))))
        from ..geometry.models import WindingLayout
        template = WindingLayout(
            template_id=layout_id,
            block_order=["P", "S"] if layout_id == "PS" else ["P1", "S", "P2"],
            process_clearance_m=_mm(selection.get("process_clearance_mm", 0.15), 0.15e-3) or 0.15e-3,
            layer_insulation_m=_mm(selection.get("layer_insulation_mm", 0.2), 0.2e-3) or 0.2e-3,
            main_insulation_m=_mm(selection.get("main_insulation_mm", 0.5), 0.5e-3) or 0.5e-3,
            winding_to_core_clearance_m=_mm(selection.get("winding_to_core_clearance_mm", 0.5), 0.5e-3) or 0.5e-3,
            end_margin_m=_mm(selection.get("end_margin_mm", 3.0), 3e-3) or 3e-3,
        )
        layout = build_layout(core, specs, template, primary_segments=segment_tuple, provenance=provenance)
        op = _operating_point(request)
        missing_waveforms = _empty_waveform_diagnostics(op)
        data_constraints = request.get("constraints") if isinstance(request.get("constraints"), Mapping) else {}
        context = EvaluationContext(
            data_snapshot=snapshot,
            provider=provider_name,
            provider_provenance=provider.status().get("provenance", {}),
            seed=int(request.get("seed")) if request.get("seed") is not None else None,
            constraints=dict(data_constraints),
            model_selection={"phase5d": PHYSICAL_MODEL_VERSION, "source": source},
        )
        candidate = EvaluationCandidate(
            layout=layout,
            wire_specs={"Primary": primary_spec, "Secondary": secondary_spec, "P": primary_spec, "S": secondary_spec, "P1": primary_spec, "P2": primary_spec},
            data_snapshot=snapshot,
            record_ids={"core": core.core_id, "material": core.material_name, "primary_wire": primary_wire.wire_id, "secondary_wire": secondary_wire.wire_id},
            candidate_id=f"web-{canonical_hash({"request": request, "layout": layout.as_dict()})[:12]}",
        )
        joint = JointCalculationService(provider)
        winding_model = "comparison" if bool(request.get("include_openmagnetics", source == "external_database")) else "native_dc"
        service = UnifiedEvaluationService(winding_loss_service=WindingLossService(provider if provider.available else None), joint_service=joint)
        requirements = request.get("design_requirements") if isinstance(request.get("design_requirements"), Mapping) else {}
        lm_requirement = requirements.get("magnetizing_inductance_h") if isinstance(requirements, Mapping) else None
        provider_inputs = {}
        if lm_requirement is not None:
            provider_inputs["designRequirements"] = {"magnetizingInductance": {"nominal": float(lm_requirement)}, "turnsRatios": [{"nominal": np_turns / ns_turns}]}
        result = service.evaluate(candidate, op, context=context, leakage_model=str(request.get("leakage_model", "native_sectional")), winding_model=winding_model, include_openmagnetics=bool(request.get("include_openmagnetics", source == "external_database")), temperature_c=op.ambient_c, provider_inputs=provider_inputs)
        if missing_waveforms:
            result["diagnostics"] = missing_waveforms + result.get("diagnostics", [])
            result["waveform_requirements"] = {"status": "missing", "diagnostics": missing_waveforms, "geometry_allowed": True, "losses_blocked": True}
        else:
            result["waveform_requirements"] = {"status": "complete", "diagnostics": [], "geometry_allowed": True, "losses_blocked": False}
        result["physical_api_version"] = PHYSICAL_API_VERSION
        result["physical_model_version"] = PHYSICAL_MODEL_VERSION
        result["source_selection"] = {"data_source": source, "provider_available": provider.available, "engineering_approved": False, "synthetic": source == "demo_fixture", "demo_only": source == "demo_fixture"}
        result["summary"] = summarize_result(result)
        return result
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "status": "input_invalid",
            "physical_api_version": PHYSICAL_API_VERSION,
            "physical_model_version": PHYSICAL_MODEL_VERSION,
            "engineering_approved": False,
            "diagnostics": [_diagnostic("PHYSICAL_INPUT_INVALID", str(exc))],
            "waveform_requirements": {"status": "unknown", "geometry_allowed": False, "losses_blocked": True},
        }


def _metric_value(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def summarize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    leakage = result.get("electromagnetic", {}).get("leakage", {}) if isinstance(result.get("electromagnetic"), Mapping) else {}
    winding = result.get("losses", {}).get("winding", {}) if isinstance(result.get("losses"), Mapping) else {}
    joint = result.get("openmagnetics", {}) if isinstance(result.get("openmagnetics"), Mapping) else {}
    calculations = joint.get("calculations", {}).get("openmagnetics", {}) if isinstance(joint.get("calculations"), Mapping) else {}
    core_loss = calculations.get("core_losses", {}) if isinstance(calculations, Mapping) else {}
    lm = calculations.get("magnetizing_inductance", {}) if isinstance(calculations, Mapping) else {}
    winding_open = winding.get("openmagnetics_full", {}) if isinstance(winding, Mapping) else {}
    native_w = winding.get("native_dc", winding) if isinstance(winding, Mapping) else {}
    return {
        "status": result.get("status"),
        "geometry": result.get("geometry", {}).get("status") if isinstance(result.get("geometry"), Mapping) else None,
        "Lm_H": _metric_value(lm.get("value") if isinstance(lm, Mapping) else None),
        "Bmax_T": _metric_value(core_loss.get("details", {}).get("magnetic_flux_density_peak_t") if isinstance(core_loss, Mapping) else None),
        "Pcore_W": _metric_value(core_loss.get("value") if isinstance(core_loss, Mapping) else None),
        "Lleak_p_H": _metric_value(leakage.get("value") if isinstance(leakage, Mapping) else None),
        "Rdc_primary_ohm": _metric_value(native_w.get("electrical_windings", {}).get("Primary", {}).get("rdc_ohm") if isinstance(native_w, Mapping) else None),
        "Rdc_secondary_ohm": _metric_value(native_w.get("electrical_windings", {}).get("Secondary", {}).get("rdc_ohm") if isinstance(native_w, Mapping) else None),
        "Pcu_native_W": _metric_value(native_w.get("value") if isinstance(native_w, Mapping) else None),
        "Pcu_complete_W": _metric_value(winding_open.get("value") if isinstance(winding_open, Mapping) else None),
        "thermal_status": result.get("thermal", {}).get("status") if isinstance(result.get("thermal"), Mapping) else "not_implemented",
        "engineering_status": "UNKNOWN",
        "engineering_approved": False,
        "data_status": result.get("source_selection", {}).get("data_source") if isinstance(result.get("source_selection"), Mapping) else None,
    }
