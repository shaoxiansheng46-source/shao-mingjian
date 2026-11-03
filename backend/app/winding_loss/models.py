"""Application-owned Phase 4B data models.

The models deliberately do not expose PyOpenMagnetics objects.  A Litz record
keeps missing manufacturer fields explicit, while the waveform/spectrum models
make the RMS, DC and harmonic conventions auditable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import pi, sqrt
from typing import Any, Mapping, Sequence


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        for key in ("nominal", "maximum", "minimum"):
            if value.get(key) is not None:
                return float(value[key])
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class LitzWireSpecification:
    manufacturer: str | None
    model: str
    data_source: str
    strand_bare_diameter_m: float | None
    strand_insulated_diameter_m: float | None
    number_strands: int | None
    strand_layers: tuple[int, ...] = ()
    strand_group_counts: tuple[int, ...] = ()
    twist_pitch_m: float | None = None
    finished_outer_diameter_m: float | None = None
    finished_outer_diameter_min_m: float | None = None
    finished_outer_diameter_max_m: float | None = None
    finished_width_m: float | None = None
    finished_height_m: float | None = None
    conductor_material: str | None = None
    resistivity_ohm_m: float | None = None
    resistivity_reference_temperature_c: float = 20.0
    temperature_coefficient_per_c: float = 0.00393
    nominal_dc_resistance_ohm_per_m: float | None = None
    conductor_area_m2: float | None = None
    external_insulation_thickness_m: float | None = None
    coating_type: str | None = None
    coating_layers: int | None = None
    recommended_frequency_min_hz: float | None = None
    recommended_frequency_max_hz: float | None = None
    missing_parameters: tuple[str, ...] = ()
    data_status: str = "external_database"
    synthetic: bool = False
    demo_only: bool = False
    engineering_approved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_provider_record(
        cls,
        record: Mapping[str, Any],
        *,
        strand_record: Mapping[str, Any] | None = None,
        data_source: str = "OpenMagnetics database via Phase 4B adapter",
    ) -> "LitzWireSpecification":
        strand = strand_record or {}
        strand_d = _number(record.get("conducting_diameter_m")) or _number(strand.get("conducting_diameter_m"))
        conductor_area = _number(record.get("conducting_area_m2"))
        count = int(record["number_conductors"]) if record.get("number_conductors") is not None else None
        if conductor_area is None and strand_d is not None and count:
            conductor_area = count * pi * (strand_d / 2.0) ** 2
        outer_raw = record.get("outer_diameter_m")
        outer = outer_raw if isinstance(outer_raw, Mapping) else ({"nominal": outer_raw} if outer_raw is not None else {})
        outer_nominal = _number(outer.get("nominal"))
        outer_min = _number(outer.get("minimum"))
        outer_max = _number(outer.get("maximum"))
        missing: list[str] = []
        if strand_d is None:
            missing.append("strand_bare_diameter_m")
        if count is None:
            missing.append("number_strands")
        if outer_nominal is None:
            missing.append("finished_outer_diameter_nominal")
        if record.get("twist_pitch_m") is None:
            missing.append("twist_pitch_m")
        coating = record.get("coating") if isinstance(record.get("coating"), Mapping) else {}
        return cls(
            manufacturer=record.get("manufacturer"),
            model=str(record.get("name")),
            data_source=data_source,
            strand_bare_diameter_m=strand_d,
            strand_insulated_diameter_m=_number(strand.get("outer_diameter_m")),
            number_strands=count,
            twist_pitch_m=_number(record.get("twist_pitch_m")),
            finished_outer_diameter_m=outer_nominal,
            finished_outer_diameter_min_m=outer_min,
            finished_outer_diameter_max_m=outer_max,
            finished_width_m=_number(record.get("outer_width_m")),
            finished_height_m=_number(record.get("outer_height_m")),
            conductor_material=record.get("conductor_material") or strand.get("material"),
            conductor_area_m2=conductor_area,
            coating_type=coating.get("type"),
            coating_layers=int(coating["number_layers"]) if coating.get("number_layers") is not None else None,
            missing_parameters=tuple(missing),
            data_status=str(record.get("data_status", "external_database")),
            metadata={"strand_record": dict(strand), "provider_record": dict(record)},
        )

    @property
    def bare_copper_area_m2(self) -> float | None:
        if self.conductor_area_m2 is not None:
            return self.conductor_area_m2
        if self.strand_bare_diameter_m is None or self.number_strands is None:
            return None
        return self.number_strands * pi * (self.strand_bare_diameter_m / 2.0) ** 2

    @property
    def occupied_area_m2(self) -> float | None:
        if self.finished_width_m and self.finished_height_m:
            return self.finished_width_m * self.finished_height_m
        if self.finished_outer_diameter_m is not None:
            return pi * (self.finished_outer_diameter_m / 2.0) ** 2
        return None

    @property
    def equivalent_copper_diameter_m(self) -> float | None:
        area = self.bare_copper_area_m2
        return sqrt(4.0 * area / pi) if area and area > 0 else None

    def resistivity_at(self, temperature_c: float) -> float:
        if self.resistivity_ohm_m is None:
            raise ValueError("MISSING_RESISTIVITY: 导线记录没有可追溯的导体电阻率。")
        return self.resistivity_ohm_m * (1.0 + self.temperature_coefficient_per_c * (temperature_c - self.resistivity_reference_temperature_c))

    def geometry_diameter_m(self, *, policy: str | None = None) -> float:
        if self.finished_outer_diameter_m is not None:
            return self.finished_outer_diameter_m
        if policy == "database_maximum" and self.finished_outer_diameter_max_m is not None:
            return self.finished_outer_diameter_max_m
        raise ValueError("MISSING_LITZ_PARAMETER: 成品利兹线外径没有标称值，必须显式选择数据库范围或提供制造数据。")

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.update({
            "bare_copper_area_m2": self.bare_copper_area_m2,
            "occupied_area_m2": self.occupied_area_m2,
            "equivalent_copper_diameter_m": self.equivalent_copper_diameter_m,
        })
        return result


@dataclass(frozen=True)
class CurrentWaveform:
    name: str
    frequency_hz: float
    time_s: tuple[float, ...]
    current_a: tuple[float, ...]

    @classmethod
    def from_mapping(cls, name: str, value: Mapping[str, Any]) -> "CurrentWaveform":
        outer_frequency = value.get("frequency_hz", value.get("frequency"))
        nested = value.get("waveform")
        if isinstance(nested, Mapping):
            value = {**nested, **({"frequency": outer_frequency} if outer_frequency is not None else {})}
        data = value.get("data", value.get("current_a"))
        times = value.get("time_s", value.get("time"))
        frequency = value.get("frequency_hz", value.get("frequency"))
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes)) or not isinstance(times, Sequence) or isinstance(times, (str, bytes)):
            raise ValueError(f"INVALID_WAVEFORM: {name} 必须提供 time_s 和 current_a/data 数组。")
        if frequency is None or float(frequency) <= 0:
            raise ValueError(f"INVALID_FREQUENCY: {name} 需要正 frequency_hz。")
        if len(data) != len(times) or len(data) < 4:
            raise ValueError(f"INVALID_WAVEFORM: {name} 的采样点至少为 4 且长度相等。")
        return cls(name, float(frequency), tuple(float(item) for item in times), tuple(float(item) for item in data))

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "frequency_hz": self.frequency_hz, "time_s": list(self.time_s), "current_a": list(self.current_a)}


@dataclass(frozen=True)
class HarmonicComponent:
    order: int
    frequency_hz: float
    amplitude_a: float
    rms_a: float
    phase_rad: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HarmonicSpectrum:
    waveform_name: str
    fundamental_frequency_hz: float
    dc_a: float
    rms_a: float
    ac_rms_a: float
    components: tuple[HarmonicComponent, ...]
    sample_count: int
    harmonic_limit: int
    resampled: bool
    truncation_rms_a: float
    diagnostics: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "waveform_name": self.waveform_name,
            "fundamental_frequency_hz": self.fundamental_frequency_hz,
            "dc_a": self.dc_a,
            "rms_a": self.rms_a,
            "ac_rms_a": self.ac_rms_a,
            "components": [item.as_dict() for item in self.components],
            "sample_count": self.sample_count,
            "harmonic_limit": self.harmonic_limit,
            "resampled": self.resampled,
            "truncation_rms_a": self.truncation_rms_a,
            "diagnostics": list(self.diagnostics),
        }
