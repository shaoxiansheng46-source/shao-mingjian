"""Application-owned inputs for Phase 5A unified evaluation.

The objects in this module are deliberately independent from MAS and from the
legacy ``engine.py`` input dictionaries.  They make the candidate geometry,
wire records and operating-point excitation one serializable, hashable input
boundary without pretending that an unverified result is engineering-rated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping

from ..geometry.models import LayoutGeometry
from ..winding_loss.models import CurrentWaveform, LitzWireSpecification


def _jsonable(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return _jsonable(value.as_dict())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("NON_FINITE_SNAPSHOT_VALUE")
        return value
    return value


def canonical_payload(value: Any) -> dict[str, Any] | list[Any] | Any:
    """Return a deterministic JSON-compatible representation."""

    return _jsonable(value)


def canonical_hash(value: Any, *, length: int = 16) -> str:
    payload = json.dumps(canonical_payload(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _waveform_as_dict(value: CurrentWaveform | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, CurrentWaveform):
        return value.as_dict()
    if isinstance(value, Mapping):
        return dict(canonical_payload(value))
    raise TypeError("WAVEFORM_MUST_BE_CURRENT_WAVEFORM_OR_MAPPING")


@dataclass(frozen=True)
class OperatingPointSnapshot:
    """One complete, immutable excitation snapshot in SI units.

    ``currents_rms_a`` carries signed port directions for the leakage energy
    model.  The current waveforms are required for winding-loss analysis.  A
    voltage waveform is optional for native calculations, but it is never
    synthesized when an OpenMagnetics joint calculation is requested.
    """

    point_id: str
    voltage_primary_v: float
    voltage_secondary_v: float
    power_w: float
    frequency_hz: float
    ambient_c: float
    currents_rms_a: Mapping[str, float]
    current_waveforms: Mapping[str, CurrentWaveform | Mapping[str, Any]]
    voltage_waveforms: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    topology: str = "DAB_SPS"
    bridge_duty: float = 0.5
    reference_side: str = "primary"

    def __post_init__(self) -> None:
        if not self.point_id:
            raise ValueError("INVALID_OPERATING_POINT_ID")
        for name, value in {
            "voltage_primary_v": self.voltage_primary_v,
            "voltage_secondary_v": self.voltage_secondary_v,
            "power_w": self.power_w,
            "frequency_hz": self.frequency_hz,
            "ambient_c": self.ambient_c,
        }.items():
            if not isfinite(float(value)):
                raise ValueError(f"NON_FINITE_OPERATING_POINT:{name}")
        if self.frequency_hz <= 0:
            raise ValueError("INVALID_FREQUENCY")
        if self.voltage_primary_v <= 0 or self.voltage_secondary_v <= 0:
            raise ValueError("INVALID_PORT_VOLTAGE")
        if self.power_w < 0:
            raise ValueError("INVALID_POWER")
        if not 0 < self.bridge_duty <= 1:
            raise ValueError("INVALID_BRIDGE_DUTY")
        if self.reference_side not in {"primary", "secondary"}:
            raise ValueError("INVALID_REFERENCE_SIDE")
        for name, value in self.currents_rms_a.items():
            if not isfinite(float(value)):
                raise ValueError(f"NON_FINITE_CURRENT:{name}")

    def current_waveform_objects(self) -> dict[str, CurrentWaveform]:
        return {
            str(name): value if isinstance(value, CurrentWaveform) else CurrentWaveform.from_mapping(str(name), value)
            for name, value in self.current_waveforms.items()
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "voltage_primary_v": float(self.voltage_primary_v),
            "voltage_secondary_v": float(self.voltage_secondary_v),
            "power_w": float(self.power_w),
            "frequency_hz": float(self.frequency_hz),
            "ambient_c": float(self.ambient_c),
            "currents_rms_a": {str(key): float(value) for key, value in sorted(self.currents_rms_a.items())},
            "current_waveforms": {str(key): _waveform_as_dict(value) for key, value in sorted(self.current_waveforms.items())},
            "voltage_waveforms": canonical_payload(self.voltage_waveforms),
            "topology": self.topology,
            "bridge_duty": float(self.bridge_duty),
            "reference_side": self.reference_side,
        }

    def provider_operating_point(self, electrical_names: list[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Build a MAS operating point only from explicitly supplied waveforms."""

        currents = self.current_waveform_objects()
        missing: list[dict[str, Any]] = []
        excitations: list[dict[str, Any]] = []
        for name in electrical_names:
            current = currents.get(name)
            voltage = self.voltage_waveforms.get(name)
            if current is None:
                missing.append({"code": "MISSING_CURRENT_WAVEFORM", "message": f"缺少 {name} 的电流波形。", "field": f"current_waveforms.{name}"})
            if voltage is None:
                missing.append({"code": "MISSING_VOLTAGE_WAVEFORM", "message": f"缺少 {name} 的电压波形；不会由直流端电压自动生成。", "field": f"voltage_waveforms.{name}"})
            if current is None or voltage is None:
                continue
            current_dict = {
                "waveform": {"data": list(current.current_a), "time": list(current.time_s)},
                "frequency": current.frequency_hz,
            }
            voltage_dict = canonical_payload(voltage)
            if isinstance(voltage_dict, Mapping) and "waveform" not in voltage_dict:
                voltage_dict = {"waveform": voltage_dict}
            excitations.append({
                "name": name,
                "voltage": voltage_dict,
                "current": current_dict,
            })
        if missing:
            return None, missing
        return {
            "excitationsPerWinding": excitations,
            "topology": self.topology,
            "frequency_hz": self.frequency_hz,
            "power_w": self.power_w,
            "voltage_primary_v": self.voltage_primary_v,
            "voltage_secondary_v": self.voltage_secondary_v,
            "bridge_duty": self.bridge_duty,
            "ambient_c": self.ambient_c,
        }, []


@dataclass(frozen=True)
class EvaluationCandidate:
    """One explicit candidate structure and its data records."""

    layout: LayoutGeometry
    wire_specs: Mapping[str, LitzWireSpecification]
    data_snapshot: Mapping[str, Any]
    record_ids: Mapping[str, str] = field(default_factory=dict)
    candidate_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "layout": self.layout.as_dict(),
            "wire_specs": {str(key): value.as_dict() for key, value in sorted(self.wire_specs.items())},
            "record_ids": canonical_payload(self.record_ids),
            "data_snapshot": canonical_payload(self.data_snapshot),
        }


@dataclass(frozen=True)
class EvaluationContext:
    """Version and constraint context supplied by the caller."""

    data_snapshot: Mapping[str, Any]
    model_registry_version: str = "sst-phase5a-model-registry-0.1.0"
    provider: str = "native"
    provider_provenance: Mapping[str, Any] = field(default_factory=dict)
    seed: int | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)
    model_selection: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_snapshot": canonical_payload(self.data_snapshot),
            "model_registry_version": self.model_registry_version,
            "provider": self.provider,
            "provider_provenance": canonical_payload(self.provider_provenance),
            "seed": self.seed,
            "constraints": canonical_payload(self.constraints),
            "model_selection": canonical_payload(self.model_selection),
        }
