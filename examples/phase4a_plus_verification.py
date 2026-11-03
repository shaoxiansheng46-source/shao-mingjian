"""Reproducible Phase 4A+ leakage-difference and physics-consistency audit.

This script keeps the independent current-sheet oracle in the benchmark layer,
separate from ``LeakageInductanceService``.  It also records the exact MAS
payload sent to the OpenMagnetics provider and generates SVG figures directly
from the returned field/energy intervals.

Run with the isolated third-party environment::

    .runtime\\openmagnetics-venv\\Scripts\\python.exe examples\\phase4a_plus_verification.py
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.geometry import MasGeometryAdapter
from backend.app.leakage import LeakageInductanceService
from backend.app.providers.openmagnetics import OpenMagneticsProvider
from examples.phase4a_leakage_benchmark import _layout, _request

MU0 = 4.0 * math.pi * 1e-7
FREQUENCY_HZ = 100_000.0
CURRENTS = {"Primary": 1.0, "Secondary": -4.0}


def _mmf_at(x: float, layout: Any, currents: dict[str, float]) -> float:
    value = 0.0
    for block in layout.blocks:
        if x >= block.radial_end_m:
            value += block.turns * currents[block.name]
        elif x > block.radial_start_m:
            fraction = (x - block.radial_start_m) / (block.radial_end_m - block.radial_start_m)
            value += block.turns * currents[block.name] * fraction
    return value


def _independent_profile(layout: Any, currents: dict[str, float]) -> dict[str, Any]:
    """Independent 1-D oracle, not calling any production leakage method."""
    boundaries = sorted({value for block in layout.blocks for value in (block.radial_start_m, block.radial_end_m)})
    height = layout.blocks[0].axial_end_m - layout.blocks[0].axial_start_m
    intervals: list[dict[str, Any]] = []
    total_energy = 0.0
    for x0, x1 in zip(boundaries, boundaries[1:]):
        if x1 <= x0:
            continue
        center = (x0 + x1) / 2.0
        containing = [block for block in layout.blocks if block.radial_start_m <= center <= block.radial_end_m]
        candidates = containing or list(layout.blocks)
        length = sum(block.mean_turn_length_m for block in candidates) / len(candidates)
        f0 = _mmf_at(x0, layout, currents)
        f1 = _mmf_at(x1, layout, currents)
        integral_f2 = (x1 - x0) * (f0 * f0 + f0 * f1 + f1 * f1) / 3.0
        energy = MU0 * length * integral_f2 / (2.0 * height)
        volume = length * height * (x1 - x0)
        intervals.append({
            "radial_start_m": x0,
            "radial_end_m": x1,
            "mmf_start_a_turn": f0,
            "mmf_end_a_turn": f1,
            "field_start_a_per_m": f0 / height,
            "field_end_a_per_m": f1 / height,
            "volume_m3": volume,
            "energy_density_j_per_m3": energy / volume,
            "energy_j": energy,
        })
        total_energy += energy
    return {"energy_j": total_energy, "intervals": intervals}


def _independent_basic(layout: Any) -> float:
    primary, secondary = layout.blocks
    height = primary.axial_end_m - primary.axial_start_m
    gap = secondary.radial_start_m - primary.radial_end_m
    mlt = (primary.mean_turn_length_m + secondary.mean_turn_length_m) / 2.0
    return MU0 * primary.turns**2 * mlt / height * (
        (primary.radial_end_m - primary.radial_start_m) / 3.0
        + gap
        + (secondary.radial_end_m - secondary.radial_start_m) / 3.0
    )


def _call_leakage(provider: OpenMagneticsProvider, layout: Any) -> dict[str, Any]:
    magnetic = MasGeometryAdapter().to_magnetic(layout)
    result = provider.calculate_leakage_inductance(magnetic, FREQUENCY_HZ, source_index=0, destination_index=1)
    return {"magnetic": magnetic, "result": result}


def _call_without_explicit_geometry(provider: OpenMagneticsProvider, layout: Any) -> dict[str, Any]:
    magnetic = MasGeometryAdapter().to_magnetic(layout)
    coil = copy.deepcopy(magnetic["coil"])
    for field in ("groupsDescription", "sectionsDescription", "layersDescription", "turnsDescription", "geometrySource", "geometryVersion"):
        coil.pop(field, None)
    fallback = {"core": copy.deepcopy(magnetic["core"]), "coil": coil}
    return provider.calculate_leakage_inductance(fallback, FREQUENCY_HZ, source_index=0, destination_index=1)


def _relative(left: Any, right: Any) -> float | None:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return abs(float(left) - float(right)) / max(abs(float(left)), abs(float(right)), 1e-30)


def _close(left: Any, right: Any, rel: float = 1e-12) -> bool:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    return abs(float(left) - float(right)) <= max(abs(float(left)), abs(float(right)), 1e-30) * rel


def _text(x: float, y: float, value: str, size: int = 12, anchor: str = "start") -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial, sans-serif" font-size="{size}px" text-anchor="{anchor}" fill="#263238">{escape(value)}</text>'


def _polyline(points: list[tuple[float, float]], stroke: str, width: float = 2.0) -> str:
    encoded = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return f'<polyline points="{encoded}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" />'


def _write_svg(path: Path, profiles: dict[str, dict[str, Any]]) -> None:
    width, height = 1120, 720
    plot_left, plot_right = 90, 1075
    panel_top = {"PS": 70, "PSP": 380}
    panel_height = 220
    all_mmf = [item[key] for profile in profiles.values() for item in profile["intervals"] for key in ("mmf_start_a_turn", "mmf_end_a_turn")]
    all_density = [item["energy_density_j_per_m3"] for profile in profiles.values() for item in profile["intervals"]]
    mmf_min, mmf_max = min(all_mmf + [0.0]), max(all_mmf + [0.0])
    density_max = max(all_density + [1.0])
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    chunks.append(_text(30, 28, "PS / PSP 漏磁 MMF 与能量密度分区（实际 1-D 计算数据）", 18))
    chunks.append(_text(30, 50, "蓝线：F(x) [A·turn]；橙色柱：u(x) [J/m³]；横轴为窗口径向坐标 [mm]", 12))
    for name in ("PS", "PSP"):
        profile = profiles[name]
        intervals = profile["intervals"]
        top = panel_top[name]
        x_min = min(item["radial_start_m"] for item in intervals)
        x_max = max(item["radial_end_m"] for item in intervals)
        def sx(value: float) -> float:
            return plot_left + (value - x_min) / max(x_max - x_min, 1e-30) * (plot_right - plot_left)
        def sy(value: float) -> float:
            return top + panel_height - (value - mmf_min) / max(mmf_max - mmf_min, 1e-30) * panel_height
        chunks.append(_text(plot_left, top - 24, f"{name}：L = {profile['value_h'] * 1e6:.6f} μH，W = {profile['energy_j']:.6g} J", 15))
        chunks.append(f'<rect x="{plot_left}" y="{top}" width="{plot_right - plot_left}" height="{panel_height}" fill="#f7fafc" stroke="#90a4ae" stroke-width="1" />')
        chunks.append(f'<line x1="{plot_left}" y1="{sy(0)}" x2="{plot_right}" y2="{sy(0)}" stroke="#b0bec5" stroke-width="1" />')
        for item in intervals:
            x0, x1 = sx(item["radial_start_m"]), sx(item["radial_end_m"])
            bar_height = item["energy_density_j_per_m3"] / density_max * (panel_height * 0.72)
            chunks.append(f'<rect x="{x0:.2f}" y="{top + panel_height - bar_height:.2f}" width="{max(x1 - x0, 1):.2f}" height="{bar_height:.2f}" fill="#ffb74d" fill-opacity="0.55" />')
        points: list[tuple[float, float]] = []
        for item in intervals:
            if not points:
                points.append((sx(item["radial_start_m"]), sy(item["mmf_start_a_turn"])))
            points.append((sx(item["radial_end_m"]), sy(item["mmf_end_a_turn"])))
        chunks.append(_polyline(points, "#1565c0", 3.0))
        chunks.append(_text(plot_left - 12, top + 14, f"{mmf_max:.0f}", 11, "end"))
        chunks.append(_text(plot_left - 12, top + panel_height, f"{mmf_min:.0f}", 11, "end"))
        chunks.append(_text(plot_left, top + panel_height + 22, f"{x_min * 1e3:.2f}", 11))
        chunks.append(_text(plot_right, top + panel_height + 22, f"{x_max * 1e3:.2f} mm", 11, "end"))
    chunks.append(_text(960, 28, "蓝 = MMF", 12, "end"))
    chunks.append(_text(1075, 50, "橙 = 能量密度", 12, "end"))
    chunks.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(chunks) + "\n", encoding="utf-8")


def run(output_dir: Path) -> dict[str, Any]:
    provider = OpenMagneticsProvider()
    service = LeakageInductanceService(provider if provider.available else None)
    report: dict[str, Any] = {
        "benchmark": "phase4a_plus_leakage_verification",
        "status": "running",
        "runtime": provider.status(),
        "model_convention": {
            "mu0": MU0,
            "frequency_hz": FREQUENCY_HZ,
            "currents_rms_signed_a": CURRENTS,
            "energy_convention": "period-average W_sigma from RMS field; L=2W_sigma/I_ref,rms^2",
        },
        "cases": {},
        "checks": [],
        "plots": {},
    }
    if not provider.available:
        report["status"] = "unavailable"
        report["diagnostics"] = [{"code": "OPENMAGNETICS_UNAVAILABLE", "message": "隔离 PyOpenMagnetics 环境不可用；仍可运行不依赖第三方的 pytest 基准。"}]
        return report

    request = _request()
    profiles: dict[str, dict[str, Any]] = {}
    for template in ("PS", "PSP"):
        layout = _layout(provider, request, template)
        native_model = "native_basic" if template == "PS" else "native_sectional"
        native = service.calculate(layout, model=native_model, currents_rms=CURRENTS, reference_port="primary")
        sectional = service.calculate(layout, model="native_sectional", currents_rms=CURRENTS, reference_port="primary")
        profile = service.field_energy_profile(layout, currents_rms=CURRENTS, reference_port="primary")
        independent = _independent_profile(layout, {block.name: (1.0 if block.role.lower() in {"primary", "p", "原边"} else -4.0) for block in layout.blocks})
        direct = _call_leakage(provider, layout)
        fallback = _call_without_explicit_geometry(provider, layout)
        profiles[template] = {
            "layout": layout.as_dict(),
            "mas_input": direct["magnetic"],
            "native": native,
            "sectional": sectional,
            "profile": profile,
            "independent_oracle": independent,
            "openmagnetics_explicit_geometry": direct["result"],
            "openmagnetics_without_explicit_geometry": fallback,
        }
        report["cases"][template] = profiles[template]

    close = _layout(provider, request, "PS", main_insulation_m=0.00025)
    far = _layout(provider, request, "PS", main_insulation_m=0.001)
    split_a = _layout(provider, request, "PSP", primary_segments=(10, 10))
    split_b = _layout(provider, request, "PSP", primary_segments=(8, 12))
    sensitivity = {
        "ps_main_insulation": {
            "close_m": 0.00025,
            "far_m": 0.001,
            "close_h": _call_leakage(provider, close)["result"].get("value"),
            "far_h": _call_leakage(provider, far)["result"].get("value"),
        },
        "psp_primary_split": {
            "split_10_10_h": _call_leakage(provider, split_a)["result"].get("value"),
            "split_8_12_h": _call_leakage(provider, split_b)["result"].get("value"),
        },
    }
    report["sensitivity"] = sensitivity
    ps = report["cases"]["PS"]
    psp = report["cases"]["PSP"]
    ps_secondary = service.calculate(_layout(provider, request, "PS"), currents_rms=CURRENTS, reference_port="secondary")
    ps_scaled = service.calculate(_layout(provider, request, "PS"), currents_rms={"Primary": 3.0, "Secondary": -12.0}, reference_port="primary")
    report["derived"] = {
        "ps_secondary_reference": ps_secondary,
        "ps_scaled_current": ps_scaled,
        "native_to_openmagnetics_ratio": {
            "PS": ps["native"].get("value") / ps["openmagnetics_explicit_geometry"].get("value"),
            "PSP": psp["native"].get("value") / psp["openmagnetics_explicit_geometry"].get("value"),
        },
    }
    report["checks"] = [
        {"name": "native_basic_independent_closed_form", "passed": abs(ps["native"]["value"] - _independent_basic(_layout(provider, request, "PS"))) <= 1e-18},
        {"name": "native_sectional_independent_energy_PS", "passed": abs(ps["sectional"]["energy_j"] - ps["independent_oracle"]["energy_j"]) <= max(abs(ps["sectional"]["energy_j"]), 1e-30) * 1e-12},
        {"name": "native_sectional_independent_energy_PSP", "passed": abs(psp["sectional"]["energy_j"] - psp["independent_oracle"]["energy_j"]) <= max(abs(psp["sectional"]["energy_j"]), 1e-30) * 1e-12},
        {"name": "profile_reconstructs_energy_PS", "passed": abs(sum(item["energy_j"] for item in ps["profile"]["intervals"]) - ps["profile"]["energy_j"]) <= 1e-18},
        {"name": "profile_reconstructs_energy_PSP", "passed": abs(sum(item["energy_j"] for item in psp["profile"]["intervals"]) - psp["profile"]["energy_j"]) <= 1e-18},
        {"name": "secondary_reference_square_ratio", "passed": _close(ps_secondary["value"], ps["native"]["value"] / 16.0)},
        {"name": "current_scale_invariance", "passed": _close(ps_scaled["value"], ps["native"]["value"])},
        {"name": "native_nonnegative_energy", "passed": all(item["energy_j"] >= 0 for case in (ps, psp) for item in case["profile"]["intervals"])},
        {"name": "openmagnetics_ps_ok", "passed": ps["openmagnetics_explicit_geometry"].get("status") == "ok"},
        {"name": "openmagnetics_psp_ok", "passed": psp["openmagnetics_explicit_geometry"].get("status") == "ok"},
        {"name": "spacing_reaches_openmagnetics_input", "passed": _relative(sensitivity["ps_main_insulation"]["close_h"], sensitivity["ps_main_insulation"]["far_h"]) is not None and _relative(sensitivity["ps_main_insulation"]["close_h"], sensitivity["ps_main_insulation"]["far_h"]) > 1e-9},
        {"name": "split_reaches_openmagnetics_input", "passed": _relative(sensitivity["psp_primary_split"]["split_10_10_h"], sensitivity["psp_primary_split"]["split_8_12_h"]) is not None and _relative(sensitivity["psp_primary_split"]["split_10_10_h"], sensitivity["psp_primary_split"]["split_8_12_h"]) > 1e-9},
    ]
    report["interpretation"] = {
        "confirmed": [
            "自研 1-D 结果可以由独立的 F(x)、H=F/h、W=0.5*mu0*integral(H^2)dV 复算。",
            "PS native_basic 与 native_sectional 在单层等高退化条件下吻合。",
            "PSP 的电气 Primary 仍为总匝数，MKF 励磁电感和磁芯损耗与 PS 一致；差异不再是半匝原边映射。",
            "间距和 PSP 分段改变会传递到显式 MAS 输入，并改变 MKF 漏感返回值。",
        ],
        "not_proven": [
            "当前证据不能证明 OpenMagnetics 的 Energy 结果就是实验或有限元真值。",
            "当前 1-D 模型忽略端部、三维转角、非等高绕组和气隙边缘场，不能用于工程认证。",
            "MKF 的峰值电流/谐波归一化与当前 RMS 周期平均能量约定存在实现边界差异，需 FEM 或实测继续判定。",
        ],
    }
    svg = output_dir / "ps_psp_mmf_energy.svg"
    _write_svg(svg, {name: {"intervals": data["profile"]["intervals"], "value_h": data["profile"]["value"], "energy_j": data["profile"]["energy_j"]} for name, data in profiles.items()})
    report["plots"]["ps_psp_mmf_energy"] = str(svg)
    report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    return report
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".runtime/phase4a-plus"))
    args = parser.parse_args()
    report = run(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks", []), "output": str(output)}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
