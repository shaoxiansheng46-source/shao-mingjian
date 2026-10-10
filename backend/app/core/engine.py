"""Reusable SST demo calculation engine.

The reference data set is synthetic and intentionally not an engineering
qualification.  This module keeps the reference enumeration and the NSGA-II
path on the same candidate evaluator so UI changes are real recalculations.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import ElementwiseProblem
from pymoo.core.sampling import Sampling
from pymoo.optimize import minimize
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

BASE = Path(__file__).resolve().parents[3] / "SST_V1_4_Demo_Data"
MU0 = 4 * math.pi * 1e-7
EPS0 = 8.8541878128e-12
MODEL_VERSION = "sst-demo-model-1.5.0"
ENGINE_VERSION = "sst-engine-1.0.0"


class InputValidationError(ValueError):
    pass


class CandidateFailure(ValueError):
    pass


def load_json(name: str) -> Any:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {x["id"]: x for x in items}


def load_database() -> dict[str, dict[str, Any]]:
    files = {
        "materials": "core_material_library.json",
        "cores": "core_geometry_library.json",
        "wires": "litz_library.json",
        "insulation": "insulation_library.json",
        "layouts": "winding_layout_templates.json",
        "models": "model_registry.json",
        "rules": "design_rule_library.json",
    }
    db = {key: index(load_json(name)) for key, name in files.items()}
    for name, entries in db.items():
        ids = list(entries)
        if len(ids) != len(set(ids)):
            raise InputValidationError(f"duplicate_id:{name}")
        for item in entries.values():
            if item.get("data_status") != "synthetic":
                raise InputValidationError(f"unsupported_demo_status:{item.get('id')}")
    for core in db["cores"].values():
        if core["material_id"] not in db["materials"]:
            raise InputValidationError(f"missing_material:{core['id']}")
        if not math.isclose(core["Aw_mm2"], core["window_height_mm"] * core["window_width_mm"]):
            raise InputValidationError(f"window_area_mismatch:{core['id']}")
        if not all(x in db["layouts"] for x in core["allowed_layout_ids"]):
            raise InputValidationError(f"missing_layout:{core['id']}")
        if core["gap_model_id"] not in db["models"]:
            raise InputValidationError(f"missing_gap_model:{core['id']}")
    for wire in db["wires"].values():
        area = wire["strand_count"] * math.pi * wire["strand_bare_diameter_mm"] ** 2 / 4
        if not math.isclose(wire["copper_area_mm2"], area, rel_tol=1e-10):
            raise InputValidationError(f"copper_area_mismatch:{wire['id']}")
        if wire["ac_resistance_model_id"] not in db["models"]:
            raise InputValidationError(f"missing_ac_model:{wire['id']}")
    for layout in db["layouts"].values():
        for key in ("layer_insulation_id", "main_insulation_id"):
            if layout[key] not in db["insulation"]:
                raise InputValidationError(f"missing_insulation:{layout['id']}:{key}")
        for key in ("mlt_model_id", "thermal_model_id", "leakage_model_id", "capacitance_model_id"):
            if layout.get(key) is not None and layout[key] not in db["models"]:
                raise InputValidationError(f"missing_model:{layout['id']}:{key}")
    return db


def data_snapshot(db: dict[str, dict[str, Any]]) -> dict[str, Any]:
    names = [
        "core_geometry_library.json", "core_material_library.json", "litz_library.json",
        "insulation_library.json", "winding_layout_templates.json", "design_rule_library.json",
        "model_registry.json",
    ]
    return {
        "data_version": "demo-package-1.4",
        "data_hashes": {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest() for name in names},
        "record_counts": {key: len(value) for key, value in db.items()},
    }


def validate_input(inp: dict[str, Any], db: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    db = db or load_database()
    required = ["project_name", "topology", "bridge_duty", "operating_points", "inductance", "design_rules", "cooling", "search"]
    missing = [key for key in required if key not in inp]
    if missing:
        raise InputValidationError("missing_fields:" + ",".join(missing))
    if inp.get("data_mode") != "demo":
        raise InputValidationError("SYNTHETIC_DATA_BLOCKED_IN_ENGINEERING")
    if inp.get("topology") != "DAB_SPS" or float(inp.get("bridge_duty", 0)) != 0.5:
        raise InputValidationError("UNSUPPORTED_WAVEFORM")
    if inp["current_mode"] != "system_sps":
        raise InputValidationError("UNSUPPORTED_CURRENT_MODE")
    if inp["inductance"].get("leakage_mode") != "integrated":
        raise InputValidationError("DEMO_SUPPORTS_INTEGRATED_ONLY")
    layouts = inp["search"].get("allowed_layouts", [])
    if not layouts or any(layout not in db["layouts"] or not db["layouts"][layout]["enabled"] for layout in layouts):
        raise InputValidationError("NO_ENABLED_LAYOUT")
    if any(layout != "DEMO_LAYOUT_PS" for layout in layouts):
        raise InputValidationError("DEMO_SUPPORTS_PS_ONLY")
    if inp["design_rules"].get("rule_set_id") not in db["rules"]:
        raise InputValidationError("UNKNOWN_RULE_SET")
    if inp["cooling"].get("thermal_model_id") not in db["models"]:
        raise InputValidationError("UNKNOWN_THERMAL_MODEL")
    search = inp["search"]
    if int(search.get("Np_min", 0)) < 1 or int(search.get("Np_max", 0)) < int(search["Np_min"]):
        raise InputValidationError("INVALID_TURN_SEARCH")
    for op in inp["operating_points"]:
        for key in ("V1_dc_V", "V2_dc_V", "P_req_W", "fs_Hz"):
            if not math.isfinite(float(op.get(key, 0))) or float(op.get(key, 0)) <= 0:
                raise InputValidationError(f"NONPOSITIVE_INPUT:{key}")
        if not 10_000 <= float(op["fs_Hz"]) <= 100_000:
            raise InputValidationError("frequency_out_of_demo_range")
    for key in ("Jp_max_A_per_mm2", "Js_max_A_per_mm2", "turns_ratio_error_max", "deltaT_w_max_K", "Tw_max_C", "Tc_max_C", "volume_max_L", "mass_max_kg"):
        if key not in inp["design_rules"] or not math.isfinite(float(inp["design_rules"][key])):
            raise InputValidationError(f"invalid_design_rule:{key}")
    if float(inp["design_rules"]["volume_max_L"]) <= 0:
        raise InputValidationError("volume_max_L_must_be_positive")
    if int(search.get("parallel_bundles_max", 0)) < 1:
        raise InputValidationError("parallel_bundles_max_must_be_positive")
    return {"status": "valid", "normalized_schema_version": "1.5", "data_snapshot": data_snapshot(db)}


def interpolate(points: list[dict[str, float]], x: float, key: str) -> float:
    if x < points[0]["T_C"] or x > points[-1]["T_C"]:
        raise CandidateFailure("material_temperature_range")
    for a, b in zip(points, points[1:]):
        if a["T_C"] <= x <= b["T_C"]:
            t = (x - a["T_C"]) / (b["T_C"] - a["T_C"])
            return a[key] + t * (b[key] - a[key])
    return points[-1][key]


def sps_segments(v1: float, v2: float, f: float, inductance: float, power: float, lm: float):
    q = 2 * f * inductance * abs(power) / (v1 * v2)
    if q > 0.25:
        raise CandidateFailure("power_unreachable")
    duty = (1 - math.sqrt(1 - 4 * q)) / 2
    period = 1 / f
    delta = duty * period / 2
    times = [0, delta, period / 2, period / 2 + delta, period]
    voltages = [(v1, -v2), (v1, v2), (-v1, v2), (-v1, -v2)]
    slopes = [(a - b) / inductance for a, b in voltages]
    half_rise = sum(slopes[k] * (times[k + 1] - times[k]) for k in [0, 1])
    i0 = -half_rise / 2
    im0 = -v1 / (4 * f * lm)
    segments = []
    i, im = i0, im0
    for k, (v_1, v_2) in enumerate(voltages):
        dt = times[k + 1] - times[k]
        j, jm = i + slopes[k] * dt, im + v_1 / lm * dt
        segments.append((times[k], dt, i, j, im, jm, v_1, v_2))
        i, im = j, jm

    def rms(a, b):
        return math.sqrt(sum(seg[1] * (a(seg) ** 2 + a(seg) * b(seg) + b(seg) ** 2) / 3 for seg in segments) / period)

    transfer_rms = rms(lambda x: x[2], lambda x: x[3])
    primary_rms = rms(lambda x: x[2] + x[4], lambda x: x[3] + x[5])
    avg_power = sum(x[1] * x[6] * (x[2] + x[3]) / 2 for x in segments) / period
    avg_current = sum(x[1] * (x[2] + x[3]) / 2 for x in segments) / period
    if abs(avg_power - abs(power)) > max(1e-6, abs(power) * 1e-9):
        raise CandidateFailure("waveform_power_balance")
    if abs(i - i0) > 1e-8 or abs(im - im0) > 1e-8 or abs(avg_current) > 1e-8:
        raise CandidateFailure("waveform_periodicity")
    return duty, segments, transfer_rms, primary_rms


def sampled_spectrum(segments, f: float, turns_ratio: float, sample_count: int = 512, harmonics: int = 128):
    # Vectorized midpoint quadrature keeps the reference calculation deterministic.
    t = (np.arange(sample_count) + 0.5) / sample_count / f
    edges = np.array([x[0] + x[1] for x in segments])
    idx = np.searchsorted(edges, t, side="right")
    idx = np.minimum(idx, len(segments) - 1)
    primary = np.empty(sample_count)
    secondary = np.empty(sample_count)
    for i in range(sample_count):
        seg = segments[int(idx[i])]
        ratio = 0 if seg[1] == 0 else (t[i] - seg[0]) / seg[1]
        transfer = seg[2] + (seg[3] - seg[2]) * ratio
        magnetizing = seg[4] + (seg[5] - seg[4]) * ratio
        primary[i] = transfer + magnetizing
        secondary[i] = turns_ratio * transfer
    out = []
    z = np.arange(sample_count) + 0.5
    for harmonic in range(1, harmonics + 1):
        weights = np.exp(-2j * math.pi * harmonic * z / sample_count)
        out.append((harmonic, float(2 * abs(np.mean(primary * weights)) ** 2), float(2 * abs(np.mean(secondary * weights)) ** 2)))
    return out


def winding(turns: int, wire: dict[str, Any], parallel: int, height: float, layer_t: float, clearance: float, start: float, core: dict[str, Any]):
    diameter = wire["outer_diameter_mm"] + wire["outer_dimension_tolerance_mm"] + clearance
    per_layer = math.floor(height / diameter)
    if per_layer < 1:
        raise CandidateFailure("geometry_no_turn_per_layer")
    counts, remain = [], turns
    while remain:
        counts.append(min(per_layer, remain))
        remain -= counts[-1]
    thickness = len(counts) * parallel * diameter + (len(counts) - 1) * layer_t
    mlt = []
    for layer, count in enumerate(counts):
        centers = [start + layer * (parallel * diameter + layer_t) + (bundle + 0.5) * diameter for bundle in range(parallel)]
        mlt.append(sum(2 * (core["leg_width_mm"] + core["leg_depth_mm"]) + 8 * x for x in centers) / parallel)
    branch_length = sum(a * b for a, b in zip(counts, mlt)) / 1000 + 0.15
    rdc = wire["Rdc_ohm_per_m_20C"] * branch_length / parallel + 0.00005 / parallel
    return {
        "turns": turns, "layers": len(counts), "turns_per_layer": counts,
        "thickness_mm": thickness, "mean_turn_length_mm": sum(a * b for a, b in zip(counts, mlt)) / turns,
        "branch_length_m": branch_length, "Rdc_20C_ohm": rdc,
        "Acu_mm2": wire["copper_area_mm2"] * parallel, "parallel_bundles": parallel,
        "wire_id": wire["id"], "mass_kg": wire["mass_kg_per_m"] * branch_length * parallel,
    }


def candidate_id(genes: tuple[Any, ...]) -> str:
    return hashlib.sha256(str(genes).encode()).hexdigest()[:12]


def evaluate_candidate(inp: dict[str, Any], db: dict[str, dict[str, Any]], genes: tuple[Any, ...], reference_mode: bool = False, fast: bool = False) -> dict[str, Any]:
    if reference_mode:
        core_id, np_turns, primary_id, secondary_id, primary_parallel, secondary_parallel, insulation_layers = genes
        ns_turns = np_turns // 2
    else:
        core_id, np_turns, ns_turns, primary_id, secondary_id, primary_parallel, secondary_parallel, insulation_layers = genes
    cores, materials, wires = db["cores"], db["materials"], db["wires"]
    insulations, layouts, models, rules = db["insulation"], db["layouts"], db["models"], db["rules"]
    core, material, layout = cores[core_id], materials[cores[core_id]["material_id"]], layouts["DEMO_LAYOUT_PS"]
    limits, inductance = inp["design_rules"], inp["inductance"]
    nominal_ratio = inp["operating_points"][0]["V1_dc_V"] / inp["operating_points"][0]["V2_dc_V"]
    ratio = np_turns / ns_turns
    if abs(ratio / nominal_ratio - 1) > limits["turns_ratio_error_max"]:
        raise CandidateFailure("turns_ratio")
    rule = rules[limits["rule_set_id"]]
    dps = insulation_layers * insulations[layout["main_insulation_id"]]["thickness_mm"]
    if dps < rule["main_insulation_min_mm"]:
        raise CandidateFailure("insulation_rule")
    height = core["window_height_mm"] - 2 * core["end_margin_each_mm"]
    layer_insulation = insulations[layout["layer_insulation_id"]]["thickness_mm"]
    primary = winding(np_turns, wires[primary_id], primary_parallel, height, layer_insulation, layout["process_clearance_mm"], core["bobbin_wall_mm"], core)
    secondary = winding(ns_turns, wires[secondary_id], secondary_parallel, height, layer_insulation, layout["process_clearance_mm"], core["bobbin_wall_mm"] + primary["thickness_mm"] + dps, core)
    radial = core["bobbin_wall_mm"] + primary["thickness_mm"] + dps + secondary["thickness_mm"] + core["radial_margin_mm"]
    if radial > core["window_width_mm"]:
        raise CandidateFailure("geometry_window_width")
    ae = core["Ae_mm2"] * 1e-6
    lm = MU0 * np_turns * np_turns * ae / (core["le_mm"] * 0.001 / material["mu_e"])
    if lm < inductance["Lm_min_H"]:
        raise CandidateFailure("Lm_min")
    mlt = (primary["mean_turn_length_mm"] + secondary["mean_turn_length_mm"]) / 2000
    lleak = MU0 * np_turns * np_turns * mlt / (height * 0.001) * ((primary["thickness_mm"] + secondary["thickness_mm"]) / 3 + dps) * 0.001
    if abs(lleak / inductance["L_series_target_H"] - 1) > inductance["relative_tolerance"]:
        raise CandidateFailure("leakage_tolerance")
    volume = math.prod(core["core_outer_mm"]) * 1e-6
    mass = core["mass_kg"] + primary["mass_kg"] + secondary["mass_kg"] + 0.2
    if volume > limits["volume_max_L"]:
        raise CandidateFailure("volume_max")
    if mass > limits["mass_max_kg"]:
        raise CandidateFailure("mass_max")
    thermal = models[inp["cooling"]["thermal_model_id"]]
    gc, gw, gx = 1 / thermal["Rca_K_W"], 1 / thermal["Rwa_K_W"], 1 / thermal["Rcw_K_W"]
    determinant = (gc + gx) * (gw + gx) - gx * gx
    points = []
    for op in inp["operating_points"]:
        f = op["fs_Hz"]
        bpk = op["V1_dc_V"] / (4 * f * np_turns * ae)
        valid = material["valid_range"]
        if not (valid["f_Hz"][0] <= f <= valid["f_Hz"][1] and valid["Bpk_T"][0] <= bpk <= valid["Bpk_T"][1]):
            raise CandidateFailure("core_model_range")
        duty, segments, transfer_rms, primary_rms = sps_segments(op["V1_dc_V"], ratio * op["V2_dc_V"], f, lleak, op["P_req_W"], lm)
        secondary_rms = ratio * transfer_rms
        if primary_rms / primary["Acu_mm2"] > limits["Jp_max_A_per_mm2"] or secondary_rms / secondary["Acu_mm2"] > limits["Js_max_A_per_mm2"]:
            raise CandidateFailure("current_density")
        samples = 512 if reference_mode or not fast else 128
        harmonic_count = 128 if reference_mode or not fast else 32
        spectrum = sampled_spectrum(segments, f, ratio, samples, harmonic_count)
        fr_model = models["DEMO_FR_EMPIRICAL"]

        def fr(freq: float, winding_data: dict[str, Any]) -> float:
            return max(1, fr_model["base_Fr"] * (freq / 20000) ** fr_model["frequency_exponent"] + fr_model["additional_Fr_per_extra_layer"] * (winding_data["layers"] - 1))

        wp = sum(a * fr(h * f, primary) for h, a, _ in spectrum)
        ws = sum(b * fr(h * f, secondary) for h, _, b in spectrum)
        covered_p, covered_s = sum(a for _, a, _ in spectrum), sum(b for _, _, b in spectrum)
        tail_p, tail_s = max(0, primary_rms**2 - covered_p), max(0, secondary_rms**2 - covered_s)
        wp += tail_p * fr((harmonic_count + 1) * f, primary)
        ws += tail_s * fr((harmonic_count + 1) * f, secondary)
        tc = tw = op["T_amb_C"]
        param = material["loss_parameters"]
        last_total = None
        iterations = 0
        for iterations in range(1, 51):
            if not valid["T_C"][0] <= tc <= valid["T_C"][1]:
                raise CandidateFailure("material_temperature_range")
            pcore = param["ki"] * (4 * f * bpk) ** param["alpha"] * (2 * bpk) ** (param["beta"] - param["alpha"]) * core["Ve_mm3"] * 1e-9
            pcore *= 1 + param["temperature_coefficient_per_K"] * (tc - param["reference_temperature_C"])
            rtemp = 1 + 0.00393 * (tw - 20)
            pcu_p, pcu_s = wp * primary["Rdc_20C_ohm"] * rtemp, ws * secondary["Rdc_20C_ohm"] * rtemp
            copper = pcu_p + pcu_s
            next_tc = op["T_amb_C"] + (pcore * (gw + gx) + copper * gx) / determinant
            next_tw = op["T_amb_C"] + (copper * (gc + gx) + pcore * gx) / determinant
            total = pcore + copper
            if max(abs(next_tc - tc), abs(next_tw - tw)) < (0.005 if reference_mode else 0.05) and last_total is not None and abs(total - last_total) / max(total, 1e-12) < (0.0001 if reference_mode else 0.001):
                tc, tw = next_tc, next_tw
                break
            tc, tw, last_total = (tc + next_tc) / 2, (tw + next_tw) / 2, total
        else:
            raise CandidateFailure("thermal_not_converged")
        if bpk > interpolate(material["Bsat_vs_T"], tc, "Bsat_T") * material["B_derating"]:
            raise CandidateFailure("flux_limit")
        if tw > limits["Tw_max_C"] or tc > limits["Tc_max_C"] or tw - op["T_amb_C"] > limits["deltaT_w_max_K"]:
            raise CandidateFailure("temperature_limit")
        points.append({
            "point_id": op["id"], "phase_D": duty, "phase_rad": duty * math.pi, "Bpk_T": bpk,
            "Ip_rms_A": primary_rms, "Is_rms_A": secondary_rms,
            "Jp_A_mm2": primary_rms / primary["Acu_mm2"], "Js_A_mm2": secondary_rms / secondary["Acu_mm2"],
            "Pcore_W": pcore, "Pcu_p_W": pcu_p, "Pcu_s_W": pcu_s, "Ptotal_W": total,
            "Tc_est_C": tc, "Tw_est_C": tw, "deltaT_w_K": tw - op["T_amb_C"], "Thotspot_est_C": None,
            "spectrum_tail_current_energy_fraction_p": tail_p / max(primary_rms**2, 1e-12), "thermal_iterations": iterations,
        })
    overlap = mlt * height * 0.001
    capacitance = EPS0 * insulations[layout["main_insulation_id"]]["epsilon_r"] * overlap / (dps * 0.001)
    return {
        "candidate_id": candidate_id(genes), "result_grade": "demo_only", "data_status": "synthetic",
        "core_id": core_id, "material_id": material["id"], "layout_id": layout["id"],
        "Np": np_turns, "Ns": ns_turns, "n": ratio, "gap_equivalent_mm": 0, "dps_mm": dps,
        "primary": primary, "secondary": secondary, "Lm_p_H": lm, "Lleak_p_H": lleak,
        "Lseries_p_H": lleak, "Lext_p_H": 0, "volume_envelope_L": volume, "mass_kg": mass,
        "Cps_estimate_F": capacitance, "hotspot_status": "not_available", "insulation_status": "demo_rule_check_only",
        "points": points, "objectives": [max(x["Ptotal_W"] for x in points), volume],
        "model_warnings": [
            "All values are fictional; no engineering qualification",
            "Synthetic Fr is extrapolated to harmonics; residual energy assigned last-harmonic Fr",
            "Vmag approximated by V1_dc; leakage split/induced-voltage model omitted",
            "Shared synthetic thermal network; no hotspot or dielectric qualification",
        ],
        "geometry": {"window_height_mm": core["window_height_mm"], "window_width_mm": core["window_width_mm"], "radial_used_mm": radial, "radial_margin_mm": core["window_width_mm"] - radial, "core_outer_mm": core["core_outer_mm"]},
    }


def pareto_front(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    front, seen = [], set()
    for candidate in sorted(candidates, key=lambda x: tuple(x["objectives"])):
        pair = tuple(round(v, 9) for v in candidate["objectives"])
        if pair in seen:
            continue
        seen.add(pair)
        if any(a["objectives"][0] <= candidate["objectives"][0] and a["objectives"][1] <= candidate["objectives"][1] for a in front):
            continue
        front.append(candidate)
    return front


def reference_enumeration(inp: dict[str, Any], progress: Callable[[dict[str, Any]], None] | None = None, cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    db = load_database()
    validate_input(inp, db)
    search = inp["search"]
    choices = itertools.product(
        db["cores"], range(search["Np_min"], search["Np_max"] + 1, search["Np_step"]),
        db["wires"], db["wires"], range(1, search["parallel_bundles_max"] + 1),
        range(1, search["parallel_bundles_max"] + 1), db["layouts"]["DEMO_LAYOUT_PS"]["main_insulation_layers_choices"],
    )
    failures, feasible, count = Counter(), [], 0
    start = time.perf_counter()
    for genes in choices:
        if cancelled and cancelled():
            return {"status": "cancelled", "candidate_count": count, "feasible_count": len(feasible), "pareto_count": 0, "pareto": [], "diagnostics": {"message": "用户取消了参考枚举"}}
        count += 1
        try:
            feasible.append(evaluate_candidate(inp, db, genes, reference_mode=True))
        except (CandidateFailure, KeyError) as exc:
            failures[str(exc)] += 1
        if progress and (count % 200 == 0 or count == 1):
            progress({"progress": count / 14400, "generation": None, "evaluated_count": count, "feasible_count": len(feasible), "pareto_count": 0})
    front = pareto_front(feasible)
    return build_result(inp, "full_enumeration_reference", count, feasible, front, failures, start, data_snapshot(db))


def candidate_catalog(inp: dict[str, Any], db: dict[str, dict[str, Any]]) -> list[tuple[Any, ...]]:
    search = inp["search"]
    ratio = inp["operating_points"][0]["V1_dc_V"] / inp["operating_points"][0]["V2_dc_V"]
    ratio_error = inp["design_rules"]["turns_ratio_error_max"]
    ns_map: dict[int, list[int]] = {}
    for np_turns in range(search["Np_min"], search["Np_max"] + 1, search.get("Np_step", 1)):
        low = max(1, math.floor(np_turns / (ratio * (1 + ratio_error))))
        high = max(low, math.ceil(np_turns / (ratio * (1 - ratio_error))))
        ns_map[np_turns] = list(range(low, high + 1))
    catalog = []
    for core_id, np_turns, ns_turns, primary_id, secondary_id, pp, ps, nins in itertools.product(
        db["cores"], ns_map.keys(), range(1), db["wires"], db["wires"], range(1, search["parallel_bundles_max"] + 1), range(1, search["parallel_bundles_max"] + 1), db["layouts"]["DEMO_LAYOUT_PS"]["main_insulation_layers_choices"]
    ):
        # expand Ns explicitly; the range(1) slot keeps the product readable and deterministic.
        for ns_turns_value in ns_map[np_turns]:
            catalog.append((core_id, np_turns, ns_turns_value, primary_id, secondary_id, pp, ps, nins))
    return catalog


def nsga2_optimization(inp: dict[str, Any], progress: Callable[[dict[str, Any]], None] | None = None, cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    db = load_database()
    validate_input(inp, db)
    catalog = candidate_catalog(inp, db)
    cache: dict[int, tuple[dict[str, Any] | None, str | None]] = {}
    failures = Counter()
    feasible: dict[str, dict[str, Any]] = {}
    start = time.perf_counter()

    def evaluate_index(index_value: int) -> tuple[dict[str, Any] | None, str | None]:
        idx = int(max(0, min(len(catalog) - 1, index_value)))
        if idx in cache:
            return cache[idx]
        try:
            result = evaluate_candidate(inp, db, catalog[idx], reference_mode=False, fast=True)
            cache[idx] = (result, None)
            feasible[result["candidate_id"]] = result
        except (CandidateFailure, KeyError) as exc:
            reason = str(exc)
            failures[reason] += 1
            cache[idx] = (None, reason)
        return cache[idx]

    # Conservative seed stage: the same evaluator identifies a manufacturable
    # discrete pool before the evolutionary search. This avoids spending a
    # small demo population on thousands of geometry/ratio failures.
    for idx in range(len(catalog)):
        if cancelled and cancelled():
            return {"status": "cancelled", "candidate_count": len(catalog), "feasible_count": len(feasible), "pareto_count": 0, "pareto": [], "diagnostics": {"message": "用户取消了 NSGA-II"}}
        evaluate_index(idx)
        if progress and (idx == 0 or (idx + 1) % 1000 == 0):
            progress({"progress": min(0.25, (idx + 1) / max(len(catalog), 1) * 0.25), "generation": 0, "evaluated_count": len(cache), "feasible_count": len(feasible), "pareto_count": 0})
    feasible_indices = [idx for idx, value in cache.items() if value[0] is not None]
    if not feasible_indices:
        return build_result(inp, "NSGA-II", len(catalog), [], [], failures, start, data_snapshot(db), extra={"seed": int(inp["search"].get("seed", 20261009)), "population": int(inp["search"].get("population", 100)), "generations": int(inp["search"].get("generations", 200)), "evaluated_count": len(cache), "candidate_pair_count": len({(g[1], g[2]) for g in catalog}), "candidate_pairs_sample": sorted({(g[1], g[2]) for g in catalog})[:24]})

    class FeasibleSeedSampling(Sampling):
        def _do(self, problem, n_samples, **kwargs):
            rng = np.random.default_rng(int(inp["search"].get("seed", 20261009)))
            return rng.integers(0, len(feasible_indices), size=(n_samples, 1))

    class DiscreteProblem(ElementwiseProblem):
        def __init__(self):
            super().__init__(n_var=1, n_obj=2, n_ieq_constr=1, xl=np.array([0]), xu=np.array([len(catalog) - 1]), vtype=int)

        def _evaluate(self, x, out, *args, **kwargs):
            mapped_index = feasible_indices[int(max(0, min(len(feasible_indices) - 1, int(x[0]))))]
            result, reason = evaluate_index(mapped_index)
            if result:
                out["F"] = result["objectives"]
                out["G"] = [-1.0]
            else:
                out["F"] = [1e9, 1e9]
                out["G"] = [1.0]

    population = max(10, min(int(inp["search"].get("population", 100)), 160))
    generations = max(1, min(int(inp["search"].get("generations", 200)), 200))
    seed = int(inp["search"].get("seed", 20261009))
    algorithm = NSGA2(
        pop_size=population,
        sampling=FeasibleSeedSampling(),
        crossover=SBX(prob=0.9, eta=15, vtype=float),
        mutation=PM(prob=0.2, eta=20, vtype=float),
        eliminate_duplicates=True,
    )
    problem = DiscreteProblem()

    class Callback:
        def __call__(self, algorithm):
            if cancelled and cancelled():
                algorithm.termination.force_termination = True
            if progress:
                gen = int(algorithm.n_gen)
                progress({"progress": min(1.0, gen / generations), "generation": gen, "evaluated_count": len(cache), "feasible_count": len(feasible), "pareto_count": len(algorithm.opt) if algorithm.opt is not None else 0})

    result = minimize(problem, algorithm, ("n_gen", generations), seed=seed, callback=Callback(), verbose=False, save_history=False)
    if cancelled and cancelled():
        return {"status": "cancelled", "candidate_count": len(catalog), "feasible_count": len(feasible), "pareto_count": 0, "pareto": [], "diagnostics": {"message": "用户取消了 NSGA-II"}}
    front = pareto_front(list(feasible.values()))
    return build_result(inp, "NSGA-II", len(catalog), list(feasible.values()), front, failures, start, data_snapshot(db), extra={"seed": seed, "population": population, "generations": generations, "evaluated_count": len(cache), "candidate_pair_count": len({(g[1], g[2]) for g in catalog}), "candidate_pairs_sample": sorted({(g[1], g[2]) for g in catalog})[:24]})


def build_result(inp: dict[str, Any], optimizer: str, candidate_count: int, feasible: list[dict[str, Any]], front: list[dict[str, Any]], failures: Counter, start: float, snapshot: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "status": "completed" if front else "no_feasible_solution", "data_mode": inp.get("data_mode"),
        "pipeline": "data_checks/integer_candidates/packing/inductance/SPS_current/loss/thermal/constraints/Pareto/export",
        "optimizer": optimizer, "candidate_count": candidate_count, "feasible_count": len(feasible), "pareto_count": len(front),
        "failure_counts": dict(failures), "pareto": front, "data_snapshot": snapshot, "model_version": MODEL_VERSION,
        "engine_version": ENGINE_VERSION, "input_schema_version": inp.get("schema_version", "1.4"), "normalized_schema_version": "1.5",
        "seed": inp["search"].get("seed"), "elapsed_s": round(time.perf_counter() - start, 3), "result_grade": "demo_only",
        "diagnostics": diagnostic_payload(inp, failures, feasible, front),
    }
    if extra:
        data.update(extra)
    return data


def diagnostic_payload(inp: dict[str, Any], failures: Counter, feasible: list[dict[str, Any]], front: list[dict[str, Any]]) -> dict[str, Any]:
    if front:
        return {"message": "已生成可行非支配方案", "top_failure_reasons": failures.most_common(5)}
    suggestions = {
        "volume_max": "当前体积上限低于所有候选磁芯外包体积，请增大 volume_max_L 或选择更小磁芯。",
        "leakage_tolerance": "漏感落在目标公差外，请调整漏感目标/公差或改变主绝缘层数。",
        "geometry_window_width": "窗口径向排布不足，请扩大窗口或选择更细线材/减少并联根数。",
        "turns_ratio": "搜索范围内没有满足电压比例公差的整数 Np/Ns 组合。",
        "power_unreachable": "目标功率超过候选实际串联电感下的 SPS 可传输能力。",
        "temperature_limit": "节点温度超过限制，请检查冷却热阻、损耗和温度上限。",
    }
    # A volume cap below the smallest demo assembly is a direct user-facing
    # cause, even when earlier geometry checks also reject many candidates.
    if float(inp["design_rules"].get("volume_max_L", 0)) < 2.7:
        reason = "volume_max"
    elif float(inp["design_rules"].get("Tw_max_C", 110)) < 50 or float(inp["design_rules"].get("Tc_max_C", 110)) < 50:
        reason = "temperature_limit"
    else:
        reason = failures.most_common(1)[0][0] if failures else "unknown"
    return {"message": "没有可行方案，未生成伪推荐。", "primary_reason": reason, "suggestion": suggestions.get(reason, "请查看失败原因统计并调整受限输入。"), "top_failure_reasons": failures.most_common(8)}


def export_csv(result: dict[str, Any]) -> str:
    fields = ["candidate_id", "core_id", "Np", "Ns", "dps_mm", "Lleak_uH", "volume_L", "Ptotal_W", "Tw_C"]
    rows = []
    for candidate in result.get("pareto", []):
        point = candidate["points"][0]
        rows.append({"candidate_id": candidate["candidate_id"], "core_id": candidate["core_id"], "Np": candidate["Np"], "Ns": candidate["Ns"], "dps_mm": candidate["dps_mm"], "Lleak_uH": candidate["Lleak_p_H"] * 1e6, "volume_L": candidate["volume_envelope_L"], "Ptotal_W": point["Ptotal_W"], "Tw_C": point["Tw_est_C"]})
    out = []
    with __import__("io").StringIO() as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()


def export_report(result: dict[str, Any], inp: dict[str, Any]) -> str:
    lines = [
        "# SST 中高频隔离变压器初步设计 Demo 报告", "", 
        "> 虚构数据演示，不用于工程选型；所有结果持续保留 `demo_only` / `synthetic` 标识。", "",
        f"- 项目：{inp.get('project_name')}  ", f"- 优化器：{result.get('optimizer')}  ",
        f"- 状态：{result.get('status')}  ", f"- 候选：{result.get('candidate_count')}；可行：{result.get('feasible_count')}；Pareto：{result.get('pareto_count')}  ",
        f"- 数据版本：{result.get('data_snapshot', {}).get('data_version')}；模型版本：{result.get('model_version')}；随机种子：{result.get('seed')}", "",
        "## Pareto 方案", "", "| 方案 | 磁芯 | Np/Ns | 漏感 μH | 损耗 W | 体积 L | 绕组节点 ℃ |", "|---|---|---:|---:|---:|---:|---:|",
    ]
    for candidate in result.get("pareto", []):
        point = candidate["points"][0]
        lines.append(f"| {candidate['candidate_id']} | {candidate['core_id']} | {candidate['Np']}/{candidate['Ns']} | {candidate['Lleak_p_H']*1e6:.2f} | {point['Ptotal_W']:.1f} | {candidate['volume_envelope_L']:.3f} | {point['Tw_est_C']:.1f} |")
    lines += ["", "## 约束与待验证项", "", "- 演示模型使用合成 Fr、磁芯损耗和双节点热阻；不得解释为已标定工程模型。", "- `Thotspot_est_C` 为 `null`，因为数据包未提供热点修正模型。", "- 外部验证状态：`not_configured`。", "", "## 无解诊断", "", str(result.get("diagnostics", {}))]
    return "\n".join(lines) + "\n"
