"""Physical design-case factories for Phase 6A.

The external factory uses the Phase 5D data adapter only to load records.  All
candidate construction and calculation remain in the Phase 6A builder and
Phase 5A UnifiedEvaluationService.  Synthetic construction is intentionally
available only for unit tests of geometry/orchestration and is marked as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any, Mapping

from ...evaluation.models import EvaluationContext, OperatingPointSnapshot, canonical_hash
from ...geometry import CoreGeometry, WireGeometry
from ...providers.openmagnetics import OpenMagneticsProvider
from ...winding_loss import CurrentWaveform, LitzWireSpecification
from ...evaluation.physical import _external_core, _external_wire


@dataclass(frozen=True)
class PhysicalDesignCase:
    """Fixed database/work-point context shared by every candidate."""

    core: CoreGeometry
    wire_options: Mapping[str, Mapping[str, Any]]
    operating_point: OperatingPointSnapshot
    data_snapshot: Mapping[str, Any]
    context: EvaluationContext
    provider: OpenMagneticsProvider | None
    provider_inputs: Mapping[str, Any]
    requirements: Mapping[str, Any]
    requires_external_provider: bool = True

    @property
    def primary_wire_choices(self) -> tuple[str, ...]:
        return tuple(sorted(self.wire_options))

    @property
    def secondary_wire_choices(self) -> tuple[str, ...]:
        return tuple(sorted(self.wire_options))

    def as_dict(self) -> dict[str, Any]:
        return {
            "core": self.core.as_dict(),
            "wire_options": {name: {"wire": value["wire"].as_dict(), "spec": value["spec"].as_dict(), "record": value.get("record")} for name, value in sorted(self.wire_options.items())},
            "operating_point": self.operating_point.as_dict(),
            "data_snapshot": dict(self.data_snapshot),
            "context": self.context.as_dict(),
            "provider_inputs": dict(self.provider_inputs),
            "requirements": dict(self.requirements),
            "requires_external_provider": self.requires_external_provider,
        }


def _waveform(name: str, frequency_hz: float, amplitude: float) -> CurrentWaveform:
    period = 1.0 / frequency_hz
    # Four samples represent a deliberately explicit, periodic square-wave
    # work point. No waveform is inferred from the DC bus voltage.
    return CurrentWaveform(name, frequency_hz, (0.0, period * 0.25, period * 0.5, period * 0.75, period), (amplitude, amplitude, -amplitude, -amplitude, amplitude))


def build_external_case(
    provider: OpenMagneticsProvider,
    *,
    shape_name: str = "ETD 54/28/19",
    material_name: str = "3C95",
    bobbin_name: str = "Bobbin ETD 54",
    wire_name: str = "Litz 1000x0.02 - Grade 1 - Double Served",
    frequency_hz: float = 100_000.0,
    voltage_primary_v: float = 100.0,
    voltage_secondary_v: float = 25.0,
    power_w: float = 1_000.0,
    ambient_c: float = 25.0,
    operating_point: OperatingPointSnapshot | None = None,
) -> PhysicalDesignCase:
    """Load a real OpenMagnetics core and wire, or raise a clear error."""

    if not provider.available:
        raise RuntimeError("OPENMAGNETICS_UNAVAILABLE: Phase 6A 外部物理算例需要可用的真实 Provider。")
    core, core_record = _external_core({"core": {"shape_name": shape_name, "material_name": material_name, "bobbin_name": bobbin_name, "gap_mm": 0.1}}, provider)
    wire, spec, wire_record = _external_wire(wire_name, provider)
    op = operating_point or OperatingPointSnapshot(
        point_id="phase6a-nominal",
        voltage_primary_v=voltage_primary_v,
        voltage_secondary_v=voltage_secondary_v,
        power_w=power_w,
        frequency_hz=frequency_hz,
        ambient_c=ambient_c,
        currents_rms_a={"Primary": 0.3, "Secondary": -1.2},
        current_waveforms={"Primary": _waveform("Primary", frequency_hz, 0.3), "Secondary": _waveform("Secondary", frequency_hz, -1.2)},
        voltage_waveforms={
            "Primary": {"waveform": {"data": [voltage_primary_v, voltage_primary_v, -voltage_primary_v, -voltage_primary_v, voltage_primary_v], "time": [0.0, 1 / frequency_hz * 0.25, 1 / frequency_hz * 0.5, 1 / frequency_hz * 0.75, 1 / frequency_hz]}},
            "Secondary": {"waveform": {"data": [voltage_secondary_v, voltage_secondary_v, -voltage_secondary_v, -voltage_secondary_v, voltage_secondary_v], "time": [0.0, 1 / frequency_hz * 0.25, 1 / frequency_hz * 0.5, 1 / frequency_hz * 0.75, 1 / frequency_hz]}},
        },
    )
    snapshot = {
        "source": "OpenMagnetics database",
        "data_status": "external_database",
        "synthetic": False,
        "demo_only": False,
        "engineering_approved": False,
        "provider": provider.status(),
        "record_ids": {"core": core.core_id, "material": core.material_name, "wire": wire_name},
    }
    snapshot["snapshot_hash"] = canonical_hash(snapshot)
    context = EvaluationContext(
        data_snapshot=snapshot,
        provider="openmagnetics",
        provider_provenance=provider.status().get("provenance", {}),
        seed=None,
        model_selection={"phase5a": "sst-phase5a-unified-evaluation-0.1.0", "phase6a": "sst-phase6a-mixed-optimization-0.1.0"},
    )
    return PhysicalDesignCase(
        core=core,
        wire_options={wire_name: {"wire": wire, "spec": spec, "record": wire_record}},
        operating_point=op,
        data_snapshot=snapshot,
        context=context,
        provider=provider,
        provider_inputs={"designRequirements": {"magnetizingInductance": {"nominal": 100e-6}}},
        requirements={"turns_ratio_target": voltage_primary_v / voltage_secondary_v},
        requires_external_provider=True,
    )


def build_synthetic_case() -> PhysicalDesignCase:
    """Small explicitly synthetic case for builder/unit tests only."""

    core = CoreGeometry(
        core_id="PHASE6A_TEST_CORE", shape_name="TEST", material_name="TEST_MATERIAL",
        physical_dimensions_m={"outer_width_m": 0.04}, effective_area_m2=80e-6,
        effective_length_m=0.08, effective_volume_m3=6.4e-6, window_width_m=0.012,
        window_height_m=0.02, winding_column_width_m=0.01, winding_column_depth_m=0.01,
        bobbin_wall_m=0.0005, bobbin_id="TEST_BOBBIN", data_status="synthetic",
        synthetic=True, demo_only=True, engineering_approved=False,
    )
    area = 100 * pi * (0.0001 / 2) ** 2
    spec = LitzWireSpecification(
        manufacturer="synthetic-test", model="TEST_LITZ", data_source="unit-test synthetic fixture",
        strand_bare_diameter_m=0.0001, strand_insulated_diameter_m=0.00012,
        number_strands=100, finished_outer_diameter_m=0.0015, conductor_material="copper",
        resistivity_ohm_m=1.72e-8, conductor_area_m2=area, data_status="synthetic",
        synthetic=True, demo_only=True, engineering_approved=False,
    )
    wire = WireGeometry("TEST_LITZ", 0.0015, 0.0001, number_conductors=100, data_status="synthetic", synthetic=True, demo_only=True, engineering_approved=False)
    frequency_hz = 30_000.0
    op = OperatingPointSnapshot(
        point_id="phase6a-test", voltage_primary_v=100.0, voltage_secondary_v=25.0,
        power_w=1000.0, frequency_hz=frequency_hz, ambient_c=25.0,
        currents_rms_a={"Primary": 0.3, "Secondary": -1.2},
        current_waveforms={"Primary": _waveform("Primary", frequency_hz, 0.3), "Secondary": _waveform("Secondary", frequency_hz, -1.2)},
        voltage_waveforms={"Primary": {"waveform": {"data": [100.0, 100.0, -100.0, -100.0, 100.0], "time": [0.0, 1 / frequency_hz * 0.25, 1 / frequency_hz * 0.5, 1 / frequency_hz * 0.75, 1 / frequency_hz]}}, "Secondary": {"waveform": {"data": [25.0, 25.0, -25.0, -25.0, 25.0], "time": [0.0, 1 / frequency_hz * 0.25, 1 / frequency_hz * 0.5, 1 / frequency_hz * 0.75, 1 / frequency_hz]}}},
    )
    snapshot = {"source": "synthetic unit-test fixture", "data_status": "synthetic", "synthetic": True, "demo_only": True, "engineering_approved": False, "record_ids": {"core": core.core_id, "wire": wire.wire_id}}
    snapshot["snapshot_hash"] = canonical_hash(snapshot)
    context = EvaluationContext(data_snapshot=snapshot, provider="native", provider_provenance={}, model_selection={"phase6a": "test-fixture"})
    return PhysicalDesignCase(
        core=core, wire_options={wire.wire_id: {"wire": wire, "spec": spec, "record": {"data_status": "synthetic"}}},
        operating_point=op, data_snapshot=snapshot, context=context, provider=None,
        provider_inputs={}, requirements={"turns_ratio_target": 4.0}, requires_external_provider=False,
    )
