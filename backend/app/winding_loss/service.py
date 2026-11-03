"""Independent Phase 4B winding-loss calculations.

The service owns waveform validation, harmonic extraction, actual conductor
length accounting and the result boundary.  OpenMagnetics remains behind the
existing provider adapter; no raw PyOpenMagnetics object is returned here.
"""

from __future__ import annotations

import copy
import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from typing import Any

from ..geometry.mas_geometry import MasGeometryAdapter
from ..geometry.models import LayoutGeometry, WindingSegmentGeometry
from ..providers.openmagnetics import OpenMagneticsProvider
from .models import CurrentWaveform, HarmonicComponent, HarmonicSpectrum, LitzWireSpecification

MODEL_VERSION = "sst-phase4b-winding-loss-0.1.0"
_PRIMARY_ROLES = {"primary", "p", "原边"}
_SECONDARY_ROLES = {"secondary", "s", "副边"}


def _diagnostic(code: str, message: str, *, field: str | None = None, severity: str = "error") -> dict[str, Any]:
    return {"code": code, "message": message, "field": field, "severity": severity}


def _failure(model: str, diagnostics: list[dict[str, Any]], *, layout: LayoutGeometry | None = None) -> dict[str, Any]:
    provenance = dict(layout.provenance) if layout is not None else {}
    return {
        "status": "input_invalid",
        "model": model,
        "model_version": MODEL_VERSION,
        "value": None,
        "unit": "W",
        "windings": {},
        "electrical_windings": {},
        "diagnostics": diagnostics,
        "unmodeled_mechanisms": [],
        "provenance": provenance,
    }


def _as_waveform(name: str, value: CurrentWaveform | Mapping[str, Any]) -> CurrentWaveform:
    if isinstance(value, CurrentWaveform):
        return value
    if not isinstance(value, Mapping):
        raise ValueError(f"INVALID_WAVEFORM: {name} 必须是 CurrentWaveform 或对象。")
    return CurrentWaveform.from_mapping(name, value)


def _collapse_duplicate_times(time_s: Sequence[float], values: Sequence[float]) -> tuple[list[float], list[float], bool]:
    result_t: list[float] = []
    result_v: list[float] = []
    collapsed = False
    for time, value in zip(time_s, values):
        if result_t and math.isclose(time, result_t[-1], rel_tol=0.0, abs_tol=1e-15):
            result_v[-1] = float(value)
            collapsed = True
        else:
            result_t.append(float(time))
            result_v.append(float(value))
    return result_t, result_v, collapsed


def _periodic_resample(waveform: CurrentWaveform) -> tuple[list[float], list[float], bool, list[dict[str, Any]]]:
    times, values, collapsed = _collapse_duplicate_times(waveform.time_s, waveform.current_a)
    diagnostics: list[dict[str, Any]] = []
    if len(times) < 4 or any(not math.isfinite(item) for item in times + values):
        raise ValueError(f"INVALID_WAVEFORM: {waveform.name} 采样必须为至少 4 个有限数值点。")
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError(f"INVALID_TIME: {waveform.name} 时间必须严格递增；重复时间只能表示同一平台点。")
    period = 1.0 / waveform.frequency_hz
    span = times[-1] - times[0]
    tolerance = max(period * 2e-3, 1e-15)
    endpoint_included = abs(span - period) <= tolerance
    if span > period + tolerance or span < period * 0.5:
        raise ValueError(f"INVALID_PERIOD: {waveform.name} 时间范围 {span:.6g}s 与 frequency_hz={waveform.frequency_hz:.6g} 不对应一个周期。")
    if endpoint_included:
        base_t = times[:-1]
        base_v = values[:-1]
    else:
        base_t = times
        base_v = values
    if len(base_t) < 4:
        raise ValueError(f"INVALID_WAVEFORM: {waveform.name} 去除周期端点后有效采样少于 4 点。")
    n = len(base_t)
    uniform_t = [times[0] + period * index / n for index in range(n)]
    source_t = list(base_t) + [base_t[0] + period]
    source_v = list(base_v) + [base_v[0]]
    uniform_v: list[float] = []
    for target in uniform_t:
        position = bisect_right(source_t, target) - 1
        position = max(0, min(position, len(source_t) - 2))
        left_t, right_t = source_t[position], source_t[position + 1]
        left_v, right_v = source_v[position], source_v[position + 1]
        fraction = (target - left_t) / max(right_t - left_t, 1e-30)
        uniform_v.append(left_v + fraction * (right_v - left_v))
    if collapsed:
        diagnostics.append(_diagnostic("DUPLICATE_TIME_COLLAPSED", "重复时间点被合并为周期插值的单个采样点。", severity="warning"))
    if not endpoint_included:
        diagnostics.append(_diagnostic("WAVEFORM_RESAMPLED", "输入不是等距采样；已用周期线性插值重采样，结果保留该近似标识。", severity="warning"))
    return uniform_t, uniform_v, collapsed or not endpoint_included, diagnostics


def analyze_current_waveform(waveform: CurrentWaveform, harmonic_limit: int = 31) -> HarmonicSpectrum:
    """Compute a single-sided DFT spectrum from one validated period."""
    time_s, values, resampled, diagnostics = _periodic_resample(waveform)
    n = len(values)
    dc = sum(values) / n
    rms = math.sqrt(sum(value * value for value in values) / n)
    components: list[HarmonicComponent] = []
    maximum_order = min(max(1, int(harmonic_limit)), n // 2)
    selected_square = 0.0
    for order in range(1, maximum_order + 1):
        real = 0.0
        imag = 0.0
        for index, value in enumerate(values):
            angle = 2.0 * math.pi * order * index / n
            real += value * math.cos(angle)
            imag -= value * math.sin(angle)
        amplitude = 2.0 * math.hypot(real, imag) / n
        rms_component = amplitude / math.sqrt(2.0)
        phase = math.atan2(-imag, real)
        selected_square += rms_component * rms_component
        if amplitude > 1e-14:
            components.append(HarmonicComponent(order, order * waveform.frequency_hz, amplitude, rms_component, phase))
    ac_square = max(0.0, rms * rms - dc * dc)
    truncation = math.sqrt(max(0.0, ac_square - selected_square))
    return HarmonicSpectrum(
        waveform_name=waveform.name,
        fundamental_frequency_hz=waveform.frequency_hz,
        dc_a=dc,
        rms_a=rms,
        ac_rms_a=math.sqrt(ac_square),
        components=tuple(components),
        sample_count=n,
        harmonic_limit=maximum_order,
        resampled=resampled,
        truncation_rms_a=truncation,
        diagnostics=tuple(diagnostics),
    )


def _processed_descriptor(spectrum: HarmonicSpectrum, waveform: CurrentWaveform) -> dict[str, Any]:
    max_order = spectrum.harmonic_limit
    by_order = {item.order: item for item in spectrum.components}
    amplitudes = [spectrum.dc_a]
    frequencies = [0.0]
    for order in range(1, max_order + 1):
        item = by_order.get(order)
        amplitudes.append(item.amplitude_a if item is not None else 0.0)
        frequencies.append(order * spectrum.fundamental_frequency_hz)
    peak = max(waveform.current_a)
    negative_peak = min(waveform.current_a)
    fundamental = next((item.rms_a for item in spectrum.components if item.order == 1), 0.0)
    return {
        "harmonics": {"amplitudes": amplitudes, "frequencies": frequencies},
        "processed": {
            "label": "custom_periodic",
            "effectiveFrequency": spectrum.fundamental_frequency_hz,
            "acEffectiveFrequency": spectrum.fundamental_frequency_hz,
            "rms": spectrum.rms_a,
            "offset": spectrum.dc_a,
            "average": spectrum.dc_a,
            "peak": peak,
            "negativePeak": negative_peak,
            "positivePeak": peak,
            "peakToPeak": peak - negative_peak,
            "thd": spectrum.ac_rms_a / max(abs(fundamental), 1e-30),
            "dutyCycle": None,
        },
        "waveform": {"data": list(waveform.current_a), "time": list(waveform.time_s)},
    }


class WindingLossService:
    """Calculate winding DC/AC losses without entering the production engine."""

    model_version = MODEL_VERSION

    def __init__(self, provider: OpenMagneticsProvider | None = None):
        self.provider = provider
        self.adapter = MasGeometryAdapter()

    @staticmethod
    def _lookup(mapping: Mapping[str, Any], block: WindingSegmentGeometry) -> Any:
        aliases = [block.name, block.winding]
        if block.role.lower() in _PRIMARY_ROLES:
            aliases += ["Primary", "primary", "P"]
        elif block.role.lower() in _SECONDARY_ROLES:
            aliases += ["Secondary", "secondary", "S"]
        for alias in aliases:
            if alias in mapping:
                return mapping[alias]
        lowered = {str(key).lower(): value for key, value in mapping.items()}
        for alias in aliases:
            if str(alias).lower() in lowered:
                return lowered[str(alias).lower()]
        return None

    @staticmethod
    def _electrical_name(layout: LayoutGeometry, block: WindingSegmentGeometry) -> str:
        if layout.template.template_id == "PSP" and block.role.lower() in _PRIMARY_ROLES:
            return "Primary"
        if layout.template.template_id == "PSP" and block.role.lower() in _SECONDARY_ROLES:
            return "Secondary"
        return block.name

    @staticmethod
    def _block_length(block: WindingSegmentGeometry) -> tuple[float, float]:
        parallel_count = max(int(block.parallels), 1)
        if block.turns_geometry:
            conductor_length = sum(item.length_m for item in block.turns_geometry)
            mean_branch = conductor_length / parallel_count
            lead_per_branch = max(block.branch_length_m - block.mean_turn_length_m, 0.0)
            return conductor_length + lead_per_branch * parallel_count, mean_branch + lead_per_branch
        branch = block.branch_length_m if block.branch_length_m > 0 else block.mean_turn_length_m
        return branch * parallel_count, branch

    def _resolve_spec(self, wire_specs: Mapping[str, Any], layout: LayoutGeometry, block: WindingSegmentGeometry) -> LitzWireSpecification | None:
        value = self._lookup(wire_specs, block)
        return value if isinstance(value, LitzWireSpecification) else None

    def _provider_wire_rdc_per_m(self, spec: LitzWireSpecification) -> tuple[float | None, dict[str, Any] | None]:
        if self.provider is None or not self.provider.available:
            return None, None
        result = self.provider.calculate_wire_dc_resistance_per_meter(spec.model)
        return (float(result["value"]) if result.get("status") == "ok" and result.get("value") is not None else None), result

    def _build_spectra(self, layout: LayoutGeometry, waveforms: Mapping[str, Any], harmonic_limit: int) -> tuple[dict[str, CurrentWaveform], dict[str, HarmonicSpectrum], list[dict[str, Any]]]:
        normalized: dict[str, CurrentWaveform] = {}
        spectra: dict[str, HarmonicSpectrum] = {}
        diagnostics: list[dict[str, Any]] = []
        for block in layout.blocks:
            raw = self._lookup(waveforms, block)
            if raw is None:
                diagnostics.append(_diagnostic("MISSING_WAVEFORM", f"缺少 {block.name} 的电流波形。", field=f"waveforms.{block.name}"))
                continue
            try:
                waveform = _as_waveform(block.name, raw)
                spectrum = analyze_current_waveform(waveform, harmonic_limit)
            except (TypeError, ValueError) as exc:
                diagnostics.append(_diagnostic("WAVEFORM_ANALYSIS_FAILED", str(exc), field=f"waveforms.{block.name}"))
                continue
            normalized[block.name] = waveform
            spectra[block.name] = spectrum
            diagnostics.extend(item for item in spectrum.diagnostics)
        return normalized, spectra, diagnostics

    def _native_result(
        self,
        layout: LayoutGeometry,
        wire_specs: Mapping[str, Any],
        spectra: Mapping[str, HarmonicSpectrum],
        *,
        temperature_c: float,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        diagnostics: list[dict[str, Any]] = []
        blocks: dict[str, dict[str, Any]] = {}
        electrical: dict[str, dict[str, Any]] = {}
        for block in layout.blocks:
            spec = self._resolve_spec(wire_specs, layout, block)
            spectrum = spectra.get(block.name)
            if spec is None:
                diagnostics.append(_diagnostic("MISSING_LITZ_SPECIFICATION", f"缺少 {block.name} 的 LitzWireSpecification。", field=f"wire_specs.{block.name}"))
                continue
            if spectrum is None:
                continue
            total_length, branch_length = self._block_length(block)
            rdc_per_m = None
            resistance_source = "resistivity_area_model"
            if spec.resistivity_ohm_m is not None and spec.bare_copper_area_m2:
                rdc_per_m = spec.resistivity_at(temperature_c) / spec.bare_copper_area_m2
            else:
                rdc_per_m, provider_result = self._provider_wire_rdc_per_m(spec)
                resistance_source = "openmagnetics_calculate_dc_resistance_per_meter"
                if rdc_per_m is None:
                    diagnostics.append(_diagnostic("MISSING_RESISTIVITY", f"{block.name} 没有电阻率，且第三方直流电阻接口不可用。", field=f"wire_specs.{block.name}.resistivity_ohm_m"))
                    continue
            parallels = max(int(block.parallels), 1)
            rdc_ohm = rdc_per_m * branch_length / parallels
            ohmic_w = spectrum.rms_a * spectrum.rms_a * rdc_ohm
            electrical_name = self._electrical_name(layout, block)
            item = {
                "name": block.name,
                "electrical_winding": electrical_name,
                "turns": block.turns,
                "parallels": parallels,
                "wire_model": spec.model,
                "length_m": total_length,
                "branch_length_m": branch_length,
                "copper_area_m2": spec.bare_copper_area_m2,
                "occupied_area_m2": spec.occupied_area_m2,
                "rdc_per_m_ohm_per_m": rdc_per_m,
                "rdc_ohm": rdc_ohm,
                "temperature_c": temperature_c,
                "current_dc_a": spectrum.dc_a,
                "current_rms_a": spectrum.rms_a,
                "ohmic_loss_w": ohmic_w,
                "resistance_source": resistance_source,
                "spectrum": spectrum.as_dict(),
            }
            blocks[block.name] = item
            aggregate = electrical.setdefault(electrical_name, {"name": electrical_name, "blocks": [], "length_m": 0.0, "rdc_ohm": 0.0, "ohmic_loss_w": 0.0})
            aggregate["blocks"].append(block.name)
            aggregate["length_m"] += total_length
            aggregate["rdc_ohm"] += rdc_ohm
            aggregate["ohmic_loss_w"] += ohmic_w
            aggregate["current_rms_a"] = spectrum.rms_a
            aggregate["current_dc_a"] = spectrum.dc_a
        total = sum(item["ohmic_loss_w"] for item in electrical.values())
        return {
            "status": "ok" if not diagnostics else "partial",
            "model": "native_dc",
            "model_version": MODEL_VERSION,
            "value": total if not diagnostics else None,
            "unit": "W",
            "ohmic_loss_w": total,
            "dc_loss_w": total,
            "ac_loss_w": None,
            "skin_loss_w": None,
            "proximity_loss_w": None,
            "windings": blocks,
            "electrical_windings": electrical,
            "diagnostics": diagnostics,
            "unmodeled_mechanisms": ["single_strand_skin_effect", "litz_bundle_internal_loss", "external_proximity_effect"],
            "note": "native_dc 使用总波形 RMS 的 Rdc 基线损耗；没有把未计算的 AC 机制默认为零。",
        }, diagnostics

    @staticmethod
    def _attach_processed_waveforms(operating_point: Mapping[str, Any], waveforms: Mapping[str, CurrentWaveform], spectra: Mapping[str, HarmonicSpectrum]) -> dict[str, Any]:
        result = copy.deepcopy(dict(operating_point))
        excitations = result.get("excitationsPerWinding", result.get("excitations_per_winding", []))
        for excitation in excitations if isinstance(excitations, list) else []:
            if not isinstance(excitation, Mapping):
                continue
            name = str(excitation.get("name", ""))
            waveform = waveforms.get(name)
            spectrum = spectra.get(name)
            if waveform is None or spectrum is None:
                continue
            current = excitation.get("current")
            if not isinstance(current, Mapping):
                current = {"waveform": {"data": list(waveform.current_a), "time": list(waveform.time_s)}}
                excitation["current"] = current
            current["harmonics"] = _processed_descriptor(spectrum, waveform)["harmonics"]
            current["processed"] = _processed_descriptor(spectrum, waveform)["processed"]
        return result

    def _electrical_waveform_inputs(
        self,
        layout: LayoutGeometry,
        waveforms: Mapping[str, CurrentWaveform],
        spectra: Mapping[str, HarmonicSpectrum],
    ) -> tuple[dict[str, CurrentWaveform], dict[str, HarmonicSpectrum]]:
        electrical_waveforms: dict[str, CurrentWaveform] = {}
        electrical_spectra: dict[str, HarmonicSpectrum] = {}
        for block in layout.blocks:
            electrical_name = self._electrical_name(layout, block)
            if electrical_name not in electrical_waveforms and block.name in waveforms and block.name in spectra:
                electrical_waveforms[electrical_name] = waveforms[block.name]
                electrical_spectra[electrical_name] = spectra[block.name]
        return electrical_waveforms, electrical_spectra

    def _openmagnetics_full(
        self,
        layout: LayoutGeometry,
        waveforms: Mapping[str, CurrentWaveform],
        spectra: Mapping[str, HarmonicSpectrum],
        *,
        operating_point: Mapping[str, Any] | None,
        temperature_c: float,
    ) -> dict[str, Any]:
        if self.provider is None or not self.provider.available:
            return {"status": "unavailable", "model": "openmagnetics_full", "value": None, "diagnostics": [_diagnostic("OPENMAGNETICS_UNAVAILABLE", "OpenMagnetics Provider 不可用。", field="provider")]}
        if operating_point is None:
            return {"status": "input_invalid", "model": "openmagnetics_full", "value": None, "diagnostics": [_diagnostic("MISSING_OPERATING_POINT", "完整第三方绕组损耗需要实际端电压和端电流 operating_point；不能只由电流或直流母线电压推造。", field="operating_point")]}
        try:
            magnetic = self.adapter.to_magnetic(layout)
            electrical_waveforms, electrical_spectra = self._electrical_waveform_inputs(layout, waveforms, spectra)
            processed_op = self._attach_processed_waveforms(operating_point, electrical_waveforms, electrical_spectra)
            result = self.provider.calculate_winding_losses(magnetic, processed_op, temperature_c)
            if result.get("status") != "ok":
                return {"status": "error", "model": "openmagnetics_full", "value": None, "diagnostics": result.get("errors", []), "provider_result": result}
            per_winding = result.get("details", {}).get("per_winding_w", [])
            components = {"ohmic_loss_w": self._optional_sum(per_winding, "ohmic_w"), "skin_loss_w": self._optional_sum(per_winding, "skin_w"), "proximity_loss_w": self._optional_sum(per_winding, "proximity_w")}
            missing = [name for name, value in components.items() if value is None]
            diagnostics = [_diagnostic("MISSING_LOSS_COMPONENT", f"第三方结果缺少 {name}，未将其当作零。", field=f"details.{name}") for name in missing]
            return {
                "status": "ok" if not missing else "partial",
                "model": "openmagnetics_full",
                "model_version": MODEL_VERSION,
                "value": result.get("value") if not missing else None,
                "unit": "W",
                "total_loss_w": result.get("value"),
                **components,
                "per_winding": per_winding,
                "diagnostics": diagnostics,
                "unmodeled_mechanisms": missing,
                "provider_result": result,
            }
        except Exception as exc:
            return {"status": "error", "model": "openmagnetics_full", "value": None, "diagnostics": [_diagnostic("OPENMAGNETICS_WINDING_LOSS_FAILED", f"{type(exc).__name__}: {exc}")]}

    @staticmethod
    def _optional_sum(items: Sequence[Mapping[str, Any]], key: str) -> float | None:
        values = [float(item[key]) for item in items if isinstance(item, Mapping) and item.get(key) is not None]
        return sum(values) if values else None

    def _openmagnetics_skin(
        self,
        layout: LayoutGeometry,
        waveforms: Mapping[str, CurrentWaveform],
        spectra: Mapping[str, HarmonicSpectrum],
        *,
        operating_point: Mapping[str, Any] | None,
        temperature_c: float,
    ) -> dict[str, Any]:
        if self.provider is None or not self.provider.available:
            return {"status": "unavailable", "model": "openmagnetics_skin", "value": None, "diagnostics": [_diagnostic("OPENMAGNETICS_UNAVAILABLE", "OpenMagnetics Provider 不可用。", field="provider")]}
        if operating_point is None:
            return {"status": "input_invalid", "model": "openmagnetics_skin", "value": None, "diagnostics": [_diagnostic("MISSING_OPERATING_POINT", "集肤损耗需要带有实际电流波形的 operating_point。", field="operating_point")]}
        try:
            magnetic = self.adapter.to_magnetic(layout)
            electrical_waveforms, electrical_spectra = self._electrical_waveform_inputs(layout, waveforms, spectra)
            processed_op = self._attach_processed_waveforms(operating_point, electrical_waveforms, electrical_spectra)
            result = self.provider.calculate_skin_effect_losses_processed(magnetic["coil"], processed_op, temperature_c)
            if result.get("status") != "ok":
                return {"status": "error", "model": "openmagnetics_skin", "value": None, "diagnostics": result.get("errors", []), "provider_result": result}
            ohmic = result.get("details", {}).get("ohmic_w")
            skin = result.get("value")
            return {
                "status": "partial",
                "model": "openmagnetics_skin",
                "model_version": MODEL_VERSION,
                "value": None,
                "unit": "W",
                "ohmic_loss_w": ohmic,
                "skin_loss_w": skin,
                "proximity_loss_w": None,
                "total_loss_w": (ohmic + skin) if ohmic is not None and skin is not None else None,
                "diagnostics": [_diagnostic("MISSING_FIELD_DATA", "本入口只执行第三方集肤阶段；邻近损耗未在同一结果中得到，不宣称为完整绕组损耗。", field="proximity_loss_w", severity="warning")],
                "unmodeled_mechanisms": ["external_proximity_effect"],
                "provider_result": result,
            }
        except Exception as exc:
            return {"status": "error", "model": "openmagnetics_skin", "value": None, "diagnostics": [_diagnostic("OPENMAGNETICS_SKIN_FAILED", f"{type(exc).__name__}: {exc}")]}

    def calculate(
        self,
        layout: LayoutGeometry,
        *,
        wire_specs: Mapping[str, Any],
        waveforms: Mapping[str, Any],
        model: str = "native_dc",
        operating_point: Mapping[str, Any] | None = None,
        temperature_c: float = 25.0,
        harmonic_limit: int = 31,
    ) -> dict[str, Any]:
        if model not in {"native_dc", "openmagnetics_skin", "openmagnetics_full", "comparison"}:
            return _failure(model, [_diagnostic("UNKNOWN_WINDING_LOSS_MODEL", f"不支持绕组损耗模型 {model}。", field="model")], layout=layout)
        if not layout.feasible:
            return _failure(model, [_diagnostic(item.code, item.message, field=item.field) for item in layout.violations], layout=layout)
        if temperature_c <= -273.15:
            return _failure(model, [_diagnostic("INVALID_TEMPERATURE", "温度必须高于绝对零度。", field="temperature_c")], layout=layout)
        try:
            normalized_waveforms, spectra, waveform_diagnostics = self._build_spectra(layout, waveforms, harmonic_limit)
        except Exception as exc:
            return _failure(model, [_diagnostic("WAVEFORM_ANALYSIS_FAILED", str(exc))], layout=layout)
        if waveform_diagnostics and any(item.get("severity", "error") == "error" for item in waveform_diagnostics):
            return _failure(model, waveform_diagnostics, layout=layout)
        native, native_diagnostics = self._native_result(layout, wire_specs, spectra, temperature_c=temperature_c)
        native["diagnostics"] = waveform_diagnostics + native.get("diagnostics", [])
        native["provenance"] = dict(layout.provenance)
        native["wire_specifications"] = {str(key): value.as_dict() for key, value in wire_specs.items() if isinstance(value, LitzWireSpecification)}
        native["temperature_c"] = temperature_c
        native["harmonic_limit"] = harmonic_limit
        if model == "native_dc":
            return native
        if model == "openmagnetics_skin":
            third_party = self._openmagnetics_skin(layout, normalized_waveforms, spectra, operating_point=operating_point, temperature_c=temperature_c)
            third_party["waveform_spectra"] = {name: spectrum.as_dict() for name, spectrum in spectra.items()}
            return third_party | {"native_dc_baseline": native, "provenance": dict(layout.provenance)}
        if model == "openmagnetics_full":
            third_party = self._openmagnetics_full(layout, normalized_waveforms, spectra, operating_point=operating_point, temperature_c=temperature_c)
            third_party["waveform_spectra"] = {name: spectrum.as_dict() for name, spectrum in spectra.items()}
            return third_party | {"native_dc_baseline": native, "provenance": dict(layout.provenance)}
        full = self._openmagnetics_full(layout, normalized_waveforms, spectra, operating_point=operating_point, temperature_c=temperature_c)
        return {
            "status": "ok" if native.get("status") == "ok" and full.get("status") == "ok" else "partial",
            "model": "comparison",
            "model_version": MODEL_VERSION,
            "value": None,
            "unit": "W",
            "native_dc": native,
            "openmagnetics_full": full,
            "diagnostics": waveform_diagnostics + full.get("diagnostics", []),
            "provenance": dict(layout.provenance),
            "comparison_note": "native_dc 是 Rdc 基线；OpenMagnetics full 是第三方完整绕组损耗路径，只有分项定义不重叠且全部存在时才可比较总值。",
        }
