"""Geometry-driven leakage-inductance models for Phase 4A.

The service is intentionally independent from the legacy synthetic evaluator.
It consumes the Phase 3 :class:`LayoutGeometry` and uses an explicit 1-D
current-sheet/field-energy model.  It does not claim to reproduce the full
3-D analytical model in the cited literature.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from math import isfinite
from typing import Any

from ..geometry.mas_geometry import MasGeometryAdapter
from ..geometry.models import LayerGeometry, LayoutGeometry, WindingSegmentGeometry

MU0 = 4.0e-7 * 3.141592653589793
MODEL_VERSION = "sst-phase4a-leakage-0.1.0"
_PRIMARY_ROLES = {"primary", "p", "原边"}
_SECONDARY_ROLES = {"secondary", "s", "副边"}


def _role(block: WindingSegmentGeometry) -> str:
    return block.role.lower()


def _diagnostic(code: str, message: str, *, field: str | None = None, severity: str = "error") -> dict[str, Any]:
    return {"code": code, "message": message, "field": field, "severity": severity}


def _failure(status: str, diagnostics: list[dict[str, Any]], *, model: str, reference_port: str) -> dict[str, Any]:
    return {
        "status": status,
        "value": None,
        "unit": "H",
        "reference_port": reference_port,
        "model": model,
        "model_version": MODEL_VERSION,
        "energy_j": None,
        "zones": [],
        "diagnostics": diagnostics,
        "uncertainty_note": "当前结果仅适用于本服务声明的 1-D 窗口场模型，未经过有限元或实物标定。",
    }


class LeakageInductanceService:
    """Calculate short-circuit leakage inductance referred to one port.

    ``currents_rms`` contains signed RMS winding currents.  For PSP, either
    ``Primary``/``Secondary`` or the physical ``P1``/``S``/``P2`` names are
    accepted.  The two primary blocks must carry the same series current.
    ``native_sectional`` integrates the square of the piecewise-linear MMF
    over the actual Phase 3 radial layers.  ``native_basic`` is the restricted
    two-layer PS closed form.  ``openmagnetics_comparison`` runs the provider
    independently and returns both values.
    """

    model_version = MODEL_VERSION

    def __init__(self, provider: Any | None = None):
        self.provider = provider
        self.adapter = MasGeometryAdapter()

    @staticmethod
    def _lookup(mapping: Mapping[str, Any], block: WindingSegmentGeometry) -> Any:
        aliases = [block.name, block.winding]
        if _role(block) in _PRIMARY_ROLES:
            aliases += ["Primary", "primary", "P"]
        elif _role(block) in _SECONDARY_ROLES:
            aliases += ["Secondary", "secondary", "S"]
        for key in aliases:
            if key in mapping:
                return mapping[key]
        lowered = {str(key).lower(): value for key, value in mapping.items()}
        for key in aliases:
            if str(key).lower() in lowered:
                return lowered[str(key).lower()]
        return None

    def _signed_currents(
        self,
        layout: LayoutGeometry,
        currents_rms: Mapping[str, Any] | None,
        current_directions: Mapping[str, Any] | None,
    ) -> tuple[dict[str, float] | None, list[dict[str, Any]]]:
        if not isinstance(currents_rms, Mapping) or not currents_rms:
            return None, [_diagnostic("MISSING_CURRENTS", "漏感能量法需要原边和副边的有符号 RMS 电流。", field="currents_rms")]
        values: dict[str, float] = {}
        diagnostics: list[dict[str, Any]] = []
        for block in layout.blocks:
            raw = self._lookup(currents_rms, block)
            if raw is None:
                diagnostics.append(_diagnostic("MISSING_WINDING_CURRENT", f"缺少 {block.name} 的 RMS 电流。", field=f"currents_rms.{block.name}"))
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                diagnostics.append(_diagnostic("INVALID_WINDING_CURRENT", f"{block.name} 电流必须是数值。", field=f"currents_rms.{block.name}"))
                continue
            if not isfinite(value) or value == 0:
                diagnostics.append(_diagnostic("INVALID_WINDING_CURRENT", f"{block.name} 电流必须是有限非零值。", field=f"currents_rms.{block.name}"))
                continue
            direction = self._lookup(current_directions, block) if isinstance(current_directions, Mapping) else None
            if direction is not None:
                try:
                    sign = 1.0 if float(direction) >= 0 else -1.0
                except (TypeError, ValueError):
                    diagnostics.append(_diagnostic("INVALID_CURRENT_DIRECTION", f"{block.name} 电流方向必须为数值符号。", field=f"current_directions.{block.name}"))
                    continue
                value = abs(value) * sign
            values[block.name] = value
        return (values if not diagnostics else None), diagnostics

    @staticmethod
    def _scope_diagnostics(layout: LayoutGeometry, model: str) -> tuple[str | None, list[dict[str, Any]]]:
        diagnostics: list[dict[str, Any]] = []
        if layout.template.template_id not in {"PS", "PSP"}:
            diagnostics.append(_diagnostic("OUT_OF_MODEL_SCOPE", "4A 只支持 Phase 3 的 PS 和 PSP 径向分段结构。", field="template"))
        if not layout.feasible:
            diagnostics.extend(item.as_dict() for item in layout.violations)
            return "INVALID_GEOMETRY", diagnostics
        if layout.template.radial_or_axial.lower() != "radial":
            diagnostics.append(_diagnostic("OUT_OF_MODEL_SCOPE", "当前漏感模型只支持径向分块、轴向匝、径向层。", field="template.radial_or_axial"))
        if len(layout.blocks) < 2:
            diagnostics.append(_diagnostic("OUT_OF_MODEL_SCOPE", "至少需要原边和副边两个绕组块。", field="blocks"))
        heights = []
        for block in layout.blocks:
            width = block.radial_end_m - block.radial_start_m
            height = block.axial_end_m - block.axial_start_m
            if width <= 0 or height <= 0 or not isfinite(width) or not isfinite(height):
                diagnostics.append(_diagnostic("INVALID_GEOMETRY", f"{block.name} 存在非正或非有限的几何尺寸。", field=f"blocks.{block.name}"))
            heights.append((block.axial_start_m, block.axial_end_m))
            for layer in block.layers:
                if layer.radial_end_m <= layer.radial_start_m:
                    diagnostics.append(_diagnostic("INVALID_GEOMETRY", f"{block.name} 的层宽必须为正。", field=f"blocks.{block.name}.layers"))
        if heights and any(abs(start - heights[0][0]) > 1e-12 or abs(end - heights[0][1]) > 1e-12 for start, end in heights[1:]):
            diagnostics.append(_diagnostic("OUT_OF_MODEL_SCOPE", "不同绕组高度的端部漏磁尚未建模；请使用等高绕组或后续 3-D 模型。", field="blocks.axial_extent"))
        for left, right in zip(layout.blocks, layout.blocks[1:]):
            gap = right.radial_start_m - left.radial_end_m
            if gap <= 0:
                diagnostics.append(_diagnostic("INVALID_INSULATION_SPACING", f"{left.name} 与 {right.name} 的物理间距必须为正。", field="interfaces"))
        if model == "native_basic":
            if layout.template.template_id != "PS" or len(layout.blocks) != 2:
                diagnostics.append(_diagnostic("OUT_OF_MODEL_SCOPE", "native_basic 只适用于两块单层 PS。", field="model"))
            if any(block.layer_count != 1 for block in layout.blocks):
                diagnostics.append(_diagnostic("OUT_OF_MODEL_SCOPE", "native_basic 不覆盖多层绕组。", field="blocks.layer_count"))
        if any(item["code"] == "OUT_OF_MODEL_SCOPE" for item in diagnostics):
            return "OUT_OF_MODEL_SCOPE", diagnostics
        if any(item["code"] in {"INVALID_GEOMETRY", "INVALID_INSULATION_SPACING"} for item in diagnostics):
            return "INVALID_GEOMETRY", diagnostics
        return ("INVALID_INPUT" if diagnostics else None), diagnostics

    @staticmethod
    def _layer_length(block: WindingSegmentGeometry, layer: LayerGeometry) -> float:
        lengths = [turn.length_m for turn in block.turns_geometry if turn.layer_index == layer.layer_index]
        return sum(lengths) / len(lengths) if lengths else block.mean_turn_length_m

    @staticmethod
    def _mmf_at(x: float, blocks: list[WindingSegmentGeometry], currents: Mapping[str, float]) -> float:
        mmf = 0.0
        for block in blocks:
            current = currents[block.name]
            if x >= block.radial_end_m:
                mmf += block.turns * current
            elif x > block.radial_start_m:
                fraction = (x - block.radial_start_m) / (block.radial_end_m - block.radial_start_m)
                mmf += block.turns * current * max(0.0, min(1.0, fraction))
        return mmf

    @staticmethod
    def _zone_for_interval(x0: float, x1: float, blocks: list[WindingSegmentGeometry]) -> tuple[str, float]:
        center = (x0 + x1) / 2.0
        for block in blocks:
            if block.radial_start_m <= center <= block.radial_end_m:
                for layer in block.layers:
                    if layer.radial_start_m <= center <= layer.radial_end_m:
                        return f"{block.name}.layer_{layer.layer_index}", LeakageInductanceService._layer_length(block, layer)
                return block.name, block.mean_turn_length_m
        touching = []
        for block in blocks:
            distance = min(abs(center - block.radial_start_m), abs(center - block.radial_end_m))
            touching.append((distance, block.mean_turn_length_m))
        return "interface", sum(item[1] for item in sorted(touching)[:2]) / min(2, len(touching))

    def _sectional_intervals(
        self,
        layout: LayoutGeometry,
        currents: Mapping[str, float],
        reference_current: float,
    ) -> tuple[float, list[dict[str, Any]], list[dict[str, Any]]]:
        boundaries = sorted({coordinate for block in layout.blocks for coordinate in (block.radial_start_m, block.radial_end_m)})
        for block in layout.blocks:
            boundaries.extend(layer.radial_start_m for layer in block.layers)
            boundaries.extend(layer.radial_end_m for layer in block.layers)
        boundaries = sorted(set(boundaries))
        height = layout.blocks[0].axial_end_m - layout.blocks[0].axial_start_m
        contributions: dict[str, dict[str, float]] = defaultdict(lambda: {"energy_j": 0.0, "radial_width_m": 0.0})
        intervals: list[dict[str, Any]] = []
        for x0, x1 in zip(boundaries, boundaries[1:]):
            if x1 <= x0:
                continue
            f0 = self._mmf_at(x0, layout.blocks, currents)
            f1 = self._mmf_at(x1, layout.blocks, currents)
            integral_f2 = (x1 - x0) * (f0 * f0 + f0 * f1 + f1 * f1) / 3.0
            zone, length = self._zone_for_interval(x0, x1, layout.blocks)
            # H_t = F/h for a uniform axial current sheet.  The field-energy
            # volume includes the same axial height h, so the integral is
            # 0.5*mu0*length/h * integral(F^2 dx), not divided by h^2.
            energy = 0.5 * MU0 * length * integral_f2 / height
            contributions[zone]["energy_j"] += energy
            contributions[zone]["radial_width_m"] += x1 - x0
            midpoint_mmf = 0.5 * (f0 + f1)
            volume = length * height * (x1 - x0)
            intervals.append({
                "radial_start_m": x0,
                "radial_end_m": x1,
                "zone": zone,
                "mean_turn_length_m": length,
                "height_m": height,
                "volume_m3": volume,
                "mmf_start_a_turn": f0,
                "mmf_end_a_turn": f1,
                "mmf_mid_a_turn": midpoint_mmf,
                "field_start_a_per_m": f0 / height,
                "field_end_a_per_m": f1 / height,
                "field_mid_a_per_m": midpoint_mmf / height,
                "energy_density_j_per_m3": energy / volume if volume > 0 else None,
                "energy_j": energy,
                "leakage_h_referred": 2.0 * energy / (reference_current * reference_current),
            })
        total = sum(item["energy_j"] for item in contributions.values())
        zones = []
        for name, item in contributions.items():
            zones.append({"zone": name, "energy_j": item["energy_j"], "radial_width_m": item["radial_width_m"], "leakage_h_referred": 2.0 * item["energy_j"] / (reference_current * reference_current)})
        return total, intervals, zones

    def _sectional_energy(self, layout: LayoutGeometry, currents: Mapping[str, float], reference_current: float) -> tuple[float, list[dict[str, Any]]]:
        total, _, zones = self._sectional_intervals(layout, currents, reference_current)
        return total, zones

    def field_energy_profile(
        self,
        layout: LayoutGeometry,
        *,
        currents_rms: Mapping[str, Any] | None = None,
        current_directions: Mapping[str, Any] | None = None,
        reference_port: str = "primary",
    ) -> dict[str, Any]:
        """Return the actual 1-D MMF/field/energy partition used by 4A.

        This is an analysis endpoint, not a second leakage model.  It runs the
        same input checks as ``native_sectional`` and exposes every radial
        integration interval so benchmark scripts and plots can be audited
        against the final energy value.
        """

        reference_port = reference_port.lower()
        if reference_port not in {"primary", "secondary"}:
            return _failure("input_invalid", [_diagnostic("INVALID_REFERENCE_PORT", "参考端口只能是 primary 或 secondary。", field="reference_port")], model="native_sectional_profile", reference_port=reference_port)
        scope_status, scope_diagnostics = self._scope_diagnostics(layout, "native_sectional")
        if scope_diagnostics:
            return _failure(scope_status or "input_invalid", scope_diagnostics, model="native_sectional_profile", reference_port=reference_port)
        currents, current_diagnostics = self._signed_currents(layout, currents_rms, current_directions)
        if current_diagnostics or currents is None:
            return _failure("input_invalid", current_diagnostics, model="native_sectional_profile", reference_port=reference_port)
        primary_blocks = [block for block in layout.blocks if _role(block) in _PRIMARY_ROLES]
        secondary_blocks = [block for block in layout.blocks if _role(block) in _SECONDARY_ROLES]
        if not primary_blocks or not secondary_blocks:
            return _failure("input_invalid", [_diagnostic("MISSING_PRIMARY_SECONDARY", "漏感分析需要原边和副边。", field="blocks")], model="native_sectional_profile", reference_port=reference_port)
        primary_current = currents[primary_blocks[0].name]
        for block in primary_blocks[1:]:
            if abs(currents[block.name] - primary_current) > max(1e-12, abs(primary_current) * 1e-9):
                return _failure("input_invalid", [_diagnostic("SERIES_CURRENT_MISMATCH", "P1/P2 串联原边必须使用相同的 RMS 电流和方向。", field=f"currents_rms.{block.name}")], model="native_sectional_profile", reference_port=reference_port)
        total_mmf = sum(block.turns * currents[block.name] for block in layout.blocks)
        max_mmf = max(sum(abs(block.turns * currents[block.name]) for block in layout.blocks), 1e-30)
        if abs(total_mmf) > max_mmf * 1e-6:
            return _failure("input_invalid", [_diagnostic("MMF_IMBALANCE", f"副边短路安匝平衡未满足，残余安匝为 {total_mmf:.6g} A·turn。", field="currents_rms")], model="native_sectional_profile", reference_port=reference_port)
        reference_blocks = primary_blocks if reference_port == "primary" else secondary_blocks
        reference_current = abs(currents[reference_blocks[0].name])
        if reference_current <= 0:
            return _failure("input_invalid", [_diagnostic("INVALID_REFERENCE_CURRENT", "参考端口电流必须非零。", field="currents_rms")], model="native_sectional_profile", reference_port=reference_port)
        total, intervals, zones = self._sectional_intervals(layout, currents, reference_current)
        value = 2.0 * total / (reference_current * reference_current)
        return {
            "status": "ok",
            "value": value,
            "unit": "H",
            "reference_port": reference_port,
            "model": "native_sectional_profile",
            "method": "native_sectional_mmf_energy",
            "model_version": MODEL_VERSION,
            "energy_j": total,
            "reference_current_rms_a": reference_current,
            "currents_rms_signed_a": dict(currents),
            "zones": zones,
            "intervals": intervals,
            "assumptions": [
                "F(x) 使用实际绕组块和实际径向边界的分段线性安匝分布。",
                "H_t=F/h；能量密度为 0.5*mu0*H_t^2，体积为平均匝长*轴向高度*径向区间。",
                "采用周期平均磁场储能和 RMS 参考电流，L=2W/I_ref,rms^2。",
            ],
            "diagnostics": [],
        }

    @staticmethod
    def _basic_result(layout: LayoutGeometry, currents: Mapping[str, float], reference_port: str) -> tuple[float, list[dict[str, Any]]]:
        primary = next(block for block in layout.blocks if _role(block) in _PRIMARY_ROLES)
        secondary = next(block for block in layout.blocks if _role(block) in _SECONDARY_ROLES)
        gap = secondary.radial_start_m - primary.radial_end_m
        height = primary.axial_end_m - primary.axial_start_m
        mlt = (primary.mean_turn_length_m + secondary.mean_turn_length_m) / 2.0
        turns = primary.turns
        l_primary = MU0 * turns * turns * mlt / height * (primary.radial_end_m - primary.radial_start_m) / 3.0
        l_gap = MU0 * turns * turns * mlt / height * gap
        l_secondary = MU0 * turns * turns * mlt / height * (secondary.radial_end_m - secondary.radial_start_m) / 3.0
        l_primary_ref = l_primary + l_gap + l_secondary
        i_ref = abs(currents[primary.name] if reference_port == "primary" else currents[secondary.name])
        i_primary = abs(currents[primary.name])
        l_ref = l_primary_ref * (i_primary / i_ref) ** 2
        return l_ref, [
            {"zone": primary.name, "energy_j": 0.5 * l_primary * i_primary * i_primary, "leakage_h_referred": l_primary * (i_primary / i_ref) ** 2},
            {"zone": "interface", "energy_j": 0.5 * l_gap * i_primary * i_primary, "leakage_h_referred": l_gap * (i_primary / i_ref) ** 2},
            {"zone": secondary.name, "energy_j": 0.5 * l_secondary * i_primary * i_primary, "leakage_h_referred": l_secondary * (i_primary / i_ref) ** 2},
        ]

    def _comparison(self, layout: LayoutGeometry, frequency_hz: float | None) -> dict[str, Any]:
        if self.provider is None or not hasattr(self.provider, "calculate_leakage_inductance"):
            return {"status": "unavailable", "value": None, "unit": "H", "diagnostics": [_diagnostic("OPENMAGNETICS_LEAKAGE_UNAVAILABLE", "当前 Provider 未暴露 OpenMagnetics 漏感接口。", field="provider")]}
        if frequency_hz is None or frequency_hz <= 0:
            return {"status": "input_invalid", "value": None, "unit": "H", "diagnostics": [_diagnostic("MISSING_FREQUENCY", "OpenMagnetics 漏感对照需要正的 frequency_hz。", field="frequency_hz")]}
        try:
            magnetic = self.adapter.to_magnetic(layout)
            return self.provider.calculate_leakage_inductance(magnetic, frequency_hz, source_index=0, destination_index=1)
        except Exception as exc:  # provider boundary converts normal errors; keep unexpected ones explicit
            return {"status": "error", "value": None, "unit": "H", "diagnostics": [_diagnostic("OPENMAGNETICS_LEAKAGE_FAILED", f"{type(exc).__name__}: {exc}")]}

    def calculate(
        self,
        layout: LayoutGeometry,
        *,
        model: str = "native_sectional",
        currents_rms: Mapping[str, Any] | None = None,
        current_directions: Mapping[str, Any] | None = None,
        reference_port: str = "primary",
        frequency_hz: float | None = None,
    ) -> dict[str, Any]:
        reference_port = reference_port.lower()
        if model not in {"native_basic", "native_sectional", "openmagnetics_comparison"}:
            return _failure("input_invalid", [_diagnostic("UNKNOWN_LEAKAGE_MODEL", f"不支持漏感模型 {model}。", field="model")], model=model, reference_port=reference_port)
        if reference_port not in {"primary", "secondary"}:
            return _failure("input_invalid", [_diagnostic("INVALID_REFERENCE_PORT", "参考端口只能是 primary 或 secondary。", field="reference_port")], model=model, reference_port=reference_port)
        scope_status, scope_diagnostics = self._scope_diagnostics(layout, model if model != "openmagnetics_comparison" else "native_sectional")
        if scope_diagnostics:
            return _failure(scope_status or "input_invalid", scope_diagnostics, model=model, reference_port=reference_port)
        currents, current_diagnostics = self._signed_currents(layout, currents_rms, current_directions)
        if current_diagnostics or currents is None:
            return _failure("input_invalid", current_diagnostics, model=model, reference_port=reference_port)
        primary_blocks = [block for block in layout.blocks if _role(block) in _PRIMARY_ROLES]
        secondary_blocks = [block for block in layout.blocks if _role(block) in _SECONDARY_ROLES]
        if not primary_blocks or not secondary_blocks:
            return _failure("input_invalid", [_diagnostic("MISSING_PRIMARY_SECONDARY", "漏感计算需要原边和副边。", field="blocks")], model=model, reference_port=reference_port)
        primary_current = currents[primary_blocks[0].name]
        for block in primary_blocks[1:]:
            if abs(currents[block.name] - primary_current) > max(1e-12, abs(primary_current) * 1e-9):
                return _failure("input_invalid", [_diagnostic("SERIES_CURRENT_MISMATCH", "P1/P2 串联原边必须使用相同的 RMS 电流和方向。", field=f"currents_rms.{block.name}")], model=model, reference_port=reference_port)
        total_mmf = sum(block.turns * currents[block.name] for block in layout.blocks)
        max_mmf = max(sum(abs(block.turns * currents[block.name]) for block in layout.blocks), 1e-30)
        if abs(total_mmf) > max_mmf * 1e-6:
            return _failure("input_invalid", [_diagnostic("MMF_IMBALANCE", f"副边短路安匝平衡未满足，残余安匝为 {total_mmf:.6g} A·turn。", field="currents_rms")], model=model, reference_port=reference_port)
        reference_blocks = primary_blocks if reference_port == "primary" else secondary_blocks
        reference_current = abs(currents[reference_blocks[0].name])
        if reference_current <= 0:
            return _failure("input_invalid", [_diagnostic("INVALID_REFERENCE_CURRENT", "参考端口电流必须非零。", field="currents_rms")], model=model, reference_port=reference_port)
        if model == "native_basic":
            value, zones = self._basic_result(layout, currents, reference_port)
            method = "native_basic_uniform_current_sheet"
        else:
            energy, zones = self._sectional_energy(layout, currents, reference_current)
            value = 2.0 * energy / (reference_current * reference_current)
            method = "native_sectional_mmf_energy"
        result = {
            "status": "ok",
            "value": value if isfinite(value) and value >= 0 else None,
            "unit": "H",
            "reference_port": reference_port,
            "source_winding": primary_blocks[0].name,
            "destination_winding": secondary_blocks[0].name,
            "model": model,
            "method": method,
            "model_version": MODEL_VERSION,
            "energy_j": 0.5 * value * reference_current * reference_current,
            "reference_current_rms_a": reference_current,
            "currents_rms_signed_a": dict(currents),
            "turns": {block.name: block.turns for block in layout.blocks},
            "zones": zones,
            "assumptions": [
                "副边短路并满足总安匝平衡。",
                "使用 RMS 电流和周期平均磁场储能 W_sigma，L=2W_sigma/I_ref,rms²。",
                "窗口内 1-D 切向漏磁场，忽略端部漏磁、三维转角和气隙边缘附加场。",
                "不同绕组高度返回 OUT_OF_MODEL_SCOPE。",
            ],
            "uncertainty_note": "这是快速解析模型；没有有限元或实物校准，不代表工程认证精度。",
            "diagnostics": [],
        }
        if model == "openmagnetics_comparison":
            comparison = self._comparison(layout, frequency_hz)
            result["openmagnetics"] = comparison
            if comparison.get("status") == "ok" and comparison.get("value") is not None:
                result["relative_difference_vs_openmagnetics"] = abs(value - comparison["value"]) / max(abs(value), abs(comparison["value"]), 1e-30)
            else:
                result["diagnostics"].append(_diagnostic("OPENMAGNETICS_COMPARISON_NOT_AVAILABLE", "自研值已计算，但第三方对照没有得到可用数值。", severity="warning"))
        return result
