"""Strict MAS boundary for the OpenMagnetics provider.

The application side uses explicit SI field names.  This module is the only
place where the lightweight request representation is converted to MAS-shaped
objects.  It intentionally refuses incomplete waveforms rather than inventing
a DAB waveform from a DC bus voltage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class MasAdapterError(ValueError):
    """Validation error with user-facing, field-level diagnostics."""

    def __init__(self, diagnostics: list[dict[str, Any]]):
        self.diagnostics = diagnostics
        message = "; ".join(item["message"] for item in diagnostics)
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": "MAS_INPUT_INVALID", "diagnostics": self.diagnostics}


def _diagnostic(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "field": field, "severity": "error"}


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MasAdapterError([_diagnostic("INVALID_NUMBER", f"{field} 必须是数值。", field)])
    return float(value)


def _positive(value: Any, field: str) -> float:
    result = _number(value, field)
    if result <= 0:
        raise MasAdapterError([_diagnostic("NON_POSITIVE", f"{field} 必须大于 0。", field)])
    return result


class MasAdapter:
    """Convert explicit SST request data to/from the MAS structure."""

    @staticmethod
    def mm_to_m(value_mm: float) -> float:
        return _positive(value_mm, "length_mm") * 1e-3

    @staticmethod
    def mm2_to_m2(value_mm2: float) -> float:
        return _positive(value_mm2, "area_mm2") * 1e-6

    @staticmethod
    def khz_to_hz(value_khz: float) -> float:
        return _positive(value_khz, "frequency_khz") * 1e3

    @staticmethod
    def uh_to_h(value_uh: float) -> float:
        return _positive(value_uh, "inductance_uH") * 1e-6

    @staticmethod
    def _length(value: Any, field: str) -> float:
        if isinstance(value, Mapping):
            if "m" in value:
                return _positive(value["m"], f"{field}.m")
            if "mm" in value:
                return MasAdapter.mm_to_m(value["mm"])
        if field.endswith("_mm"):
            return MasAdapter.mm_to_m(value)
        return _positive(value, field)

    @staticmethod
    def _frequency(entry: Mapping[str, Any], field_prefix: str = "frequency") -> float:
        if "frequency_hz" in entry:
            return _positive(entry["frequency_hz"], f"{field_prefix}_hz")
        if "frequency_khz" in entry:
            return MasAdapter.khz_to_hz(entry["frequency_khz"])
        raise MasAdapterError([_diagnostic("MISSING_FREQUENCY", "缺少绕组工作频率（Hz 或 kHz）。", field_prefix)])

    @staticmethod
    def _waveform(value: Any, field: str) -> dict[str, list[float]]:
        if not isinstance(value, Mapping):
            raise MasAdapterError([_diagnostic("MISSING_WAVEFORM", f"{field} 必须提供 data 和 time 波形。", field)])
        data = value.get("data")
        time = value.get("time_s", value.get("time"))
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
            raise MasAdapterError([_diagnostic("INVALID_WAVEFORM", f"{field}.data 必须是数值数组。", field)])
        if not isinstance(time, Sequence) or isinstance(time, (str, bytes)):
            raise MasAdapterError([_diagnostic("INVALID_WAVEFORM", f"{field}.time 必须是秒单位数组。", field)])
        if len(data) < 2 or len(data) != len(time):
            raise MasAdapterError([_diagnostic("INVALID_WAVEFORM", f"{field} 的 data/time 长度必须相等且至少为 2。", field)])
        try:
            converted_data = [float(item) for item in data]
            converted_time = [float(item) for item in time]
        except (TypeError, ValueError):
            raise MasAdapterError([_diagnostic("INVALID_WAVEFORM", f"{field} 只能包含数值。", field)]) from None
        if any(item < 0 for item in converted_time):
            raise MasAdapterError([_diagnostic("INVALID_TIME", f"{field}.time 不能为负数。", field)])
        if any(right < left for left, right in zip(converted_time, converted_time[1:])):
            raise MasAdapterError([_diagnostic("INVALID_TIME", f"{field}.time 必须单调不减。", field)])
        return {"data": converted_data, "time": converted_time}

    @staticmethod
    def _gap_list(core: Mapping[str, Any]) -> list[dict[str, Any]]:
        if isinstance(core.get("gapping"), Sequence) and not isinstance(core.get("gapping"), (str, bytes)):
            gaps = []
            for index, item in enumerate(core["gapping"]):
                if not isinstance(item, Mapping):
                    raise MasAdapterError([_diagnostic("INVALID_GAP", "gapping 项必须是对象。", f"core.gapping[{index}]")])
                raw = item.get("length_m", item.get("length"))
                if raw is None and "length_mm" in item:
                    raw = MasAdapter.mm_to_m(item["length_mm"])
                if raw is None:
                    raise MasAdapterError([_diagnostic("MISSING_GAP_LENGTH", "气隙缺少长度。", f"core.gapping[{index}]")])
                length = _positive(raw, f"core.gapping[{index}].length_m")
                gaps.append({"type": item.get("type", "subtractive"), "length": length})
            return gaps
        if "gap_m" in core:
            return [{"type": core.get("gap_type", "subtractive"), "length": _positive(core["gap_m"], "core.gap_m")}]
        if "gap_mm" in core:
            return [{"type": core.get("gap_type", "subtractive"), "length": MasAdapter.mm_to_m(core["gap_mm"])}]
        return []

    def to_magnetic(self, request: Mapping[str, Any]) -> dict[str, Any]:
        core = request.get("core")
        windings = request.get("windings")
        diagnostics: list[dict[str, Any]] = []
        if not isinstance(core, Mapping):
            diagnostics.append(_diagnostic("MISSING_CORE", "缺少 core 磁芯结构。", "core"))
        if not isinstance(windings, Sequence) or isinstance(windings, (str, bytes)) or not windings:
            diagnostics.append(_diagnostic("MISSING_WINDINGS", "至少需要一个 winding。", "windings"))
        if diagnostics:
            raise MasAdapterError(diagnostics)
        shape = core.get("shape")
        material = core.get("material")
        if not shape or not material:
            raise MasAdapterError([_diagnostic("MISSING_CORE_ID", "core.shape 与 core.material 必须提供。", "core")])
        core_fd = {
            "type": core.get("type", "two-piece set"),
            "shape": str(shape),
            "material": str(material),
            "gapping": self._gap_list(core),
            "numberStacks": int(core.get("number_stacks", core.get("numberStacks", 1))),
        }
        mas_windings = []
        for index, winding in enumerate(windings):
            if not isinstance(winding, Mapping):
                raise MasAdapterError([_diagnostic("INVALID_WINDING", "winding 必须是对象。", f"windings[{index}]")])
            turns = winding.get("number_turns", winding.get("numberTurns"))
            if turns is None:
                raise MasAdapterError([_diagnostic("MISSING_TURNS", "绕组匝数必须提供。", f"windings[{index}]")])
            mas_windings.append(
                {
                    "name": str(winding.get("name", f"Winding {index + 1}")),
                    "numberTurns": int(_positive(turns, f"windings[{index}].number_turns")),
                    "numberParallels": int(winding.get("number_parallels", winding.get("numberParallels", 1))),
                    "wire": str(winding["wire"]),
                    "isolationSide": winding.get("isolation_side", winding.get("isolationSide")),
                }
            )
        coil = {"functionalDescription": mas_windings}
        if request.get("bobbin"):
            coil["bobbin"] = str(request["bobbin"])
        return {"core": {"functionalDescription": core_fd}, "coil": coil}

    def _operating_points(self, request: Mapping[str, Any]) -> list[dict[str, Any]]:
        operating_points = request.get("operating_points", request.get("operatingPoints"))
        if operating_points is None and request.get("operating_point") is not None:
            operating_points = [request["operating_point"]]
        if not isinstance(operating_points, Sequence) or isinstance(operating_points, (str, bytes)) or not operating_points:
            raise MasAdapterError([_diagnostic("MISSING_OPERATING_POINTS", "缺少 operating_points。", "operating_points")])
        result = []
        topology = str(request.get("topology", "")).lower().replace("-", "_")
        if topology in {"dab", "dual_active_bridge"} and not any(
            key in request for key in ("phase_shift_rad", "phase_shift_deg", "phaseShift")
        ):
            raise MasAdapterError([_diagnostic("MISSING_DAB_PHASE_SHIFT", "DAB 缺少移相角，不能从直流母线电压推造波形。", "phase_shift")])
        for op_index, op in enumerate(operating_points):
            if not isinstance(op, Mapping):
                raise MasAdapterError([_diagnostic("INVALID_OPERATING_POINT", "operating point 必须是对象。", f"operating_points[{op_index}]")])
            ambient = op.get("ambient_temperature_c", op.get("ambientTemperature", request.get("ambient_temperature_c", 25.0)))
            excitations = op.get("excitations_per_winding", op.get("excitationsPerWinding"))
            if not isinstance(excitations, Sequence) or isinstance(excitations, (str, bytes)) or not excitations:
                raise MasAdapterError([_diagnostic("MISSING_WAVEFORMS", "必须提供每个绕组的端电压和电流波形；不能只提供直流母线电压。", f"operating_points[{op_index}]")])
            mas_excitations = []
            for winding_index, excitation in enumerate(excitations):
                if not isinstance(excitation, Mapping):
                    raise MasAdapterError([_diagnostic("INVALID_EXCITATION", "激励必须是对象。", f"operating_points[{op_index}].excitations[{winding_index}]")])
                voltage = excitation.get("voltage_waveform", excitation.get("voltage"))
                current = excitation.get("current_waveform", excitation.get("current"))
                if isinstance(voltage, Mapping) and "waveform" in voltage:
                    voltage = voltage["waveform"]
                if isinstance(current, Mapping) and "waveform" in current:
                    current = current["waveform"]
                # The conversion intentionally does not accept dc_bus_voltage here.
                voltage_waveform = self._waveform(voltage, f"operating_points[{op_index}].voltage")
                current_waveform = self._waveform(current, f"operating_points[{op_index}].current")
                mas_excitations.append(
                    {
                        "name": str(excitation.get("name", f"Winding {winding_index + 1}")),
                        "frequency": self._frequency(excitation, f"operating_points[{op_index}].frequency"),
                        "voltage": {"waveform": voltage_waveform},
                        "current": {"waveform": current_waveform},
                    }
                )
            result.append({"name": str(op.get("name", f"Operating Point {op_index + 1}")), "conditions": {"ambientTemperature": _number(ambient, "ambient_temperature_c")}, "excitationsPerWinding": mas_excitations})
        return result

    def to_inputs(self, request: Mapping[str, Any]) -> dict[str, Any]:
        requirements = request.get("design_requirements", request.get("designRequirements", {}))
        if not isinstance(requirements, Mapping):
            raise MasAdapterError([_diagnostic("INVALID_DESIGN_REQUIREMENTS", "design_requirements 必须是对象。", "design_requirements")])
        inductance = requirements.get("magnetizing_inductance_h", requirements.get("magnetizingInductance"))
        if inductance is None and "magnetizing_inductance_uh" in requirements:
            nominal = self.uh_to_h(requirements["magnetizing_inductance_uh"])
            inductance = {"nominal": nominal}
        if isinstance(inductance, Mapping):
            inductance = {
                key: (_number(value, f"magnetizing_inductance_h.{key}") if key in {"nominal", "minimum", "maximum"} else value)
                for key, value in inductance.items()
            }
        if not isinstance(inductance, Mapping) or "nominal" not in inductance:
            raise MasAdapterError([_diagnostic("MISSING_MAGNETIZING_INDUCTANCE", "需要磁化电感 nominal（H）。", "design_requirements")])
        turns_ratios = requirements.get("turns_ratios", requirements.get("turnsRatios", []))
        if not isinstance(turns_ratios, Sequence) or isinstance(turns_ratios, (str, bytes)):
            raise MasAdapterError([_diagnostic("INVALID_TURNS_RATIOS", "turns_ratios 必须是数组。", "design_requirements.turns_ratios")])
        design = {"magnetizingInductance": inductance, "turnsRatios": list(turns_ratios)}
        if "leakage_inductance_h" in requirements:
            design["leakageInductance"] = requirements["leakage_inductance_h"]
        return {"designRequirements": design, "operatingPoints": self._operating_points(request)}

    def to_mas(self, request: Mapping[str, Any]) -> dict[str, Any]:
        magnetic = self.to_magnetic(request)
        inputs = self.to_inputs(request)
        return {"inputs": inputs, "magnetic": magnetic}

    @staticmethod
    def from_mas(mas: Mapping[str, Any]) -> dict[str, Any]:
        """Return a small canonical summary; never return the external object."""
        magnetic = mas.get("magnetic", {}) if isinstance(mas, Mapping) else {}
        core = magnetic.get("core", {}) if isinstance(magnetic, Mapping) else {}
        core_fd = core.get("functionalDescription", {}) if isinstance(core, Mapping) else {}
        coil = magnetic.get("coil", {}) if isinstance(magnetic, Mapping) else {}
        coil_fd = coil.get("functionalDescription", []) if isinstance(coil, Mapping) else []
        return {
            "core": {
                "shape": (core_fd.get("shape") or {}).get("name") if isinstance(core_fd.get("shape"), Mapping) else core_fd.get("shape"),
                "material": (core_fd.get("material") or {}).get("name") if isinstance(core_fd.get("material"), Mapping) else core_fd.get("material"),
                "gapping_m": [item.get("length") for item in core_fd.get("gapping", []) if isinstance(item, Mapping) and item.get("length") is not None],
            },
            "windings": [
                {"name": item.get("name"), "number_turns": item.get("numberTurns"), "wire": (item.get("wire") or {}).get("name") if isinstance(item.get("wire"), Mapping) else item.get("wire")}
                for item in coil_fd if isinstance(item, Mapping)
            ],
            "operating_point_count": len((mas.get("inputs", {}) or {}).get("operatingPoints", [])) if isinstance(mas, Mapping) else 0,
        }
