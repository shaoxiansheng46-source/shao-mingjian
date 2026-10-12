import copy
import json
import math
from pathlib import Path

import pytest

from backend.app.core.engine import (
    CandidateFailure,
    MU0,
    candidate_catalog,
    evaluate_candidate,
    load_database,
    nsga2_optimization,
)


ROOT = Path(__file__).resolve().parents[2]


def combined_input():
    return json.loads((ROOT / "SST_V1_4_Demo_Data" / "v1_1" / "examples" / "sample_input_combined.json").read_text(encoding="utf-8"))


def known_gene():
    return ("DEMO_CORE_SET2_XL", 10, 5, "DEMO_LITZ_6000x0p1", "DEMO_LITZ_12000x0p1", 2, 2, 2, "DEMO_LAYOUT_PSP_V1_1", "DEMO_EXT_L_10UH", None)


def test_combined_case_is_real_and_quantized():
    db = load_database()
    result = evaluate_candidate(combined_input(), db, known_gene())
    assert result["data_status"] == "synthetic"
    assert result["layout_id"] == "DEMO_LAYOUT_PSP_V1_1"
    assert result["core_assembly_count"] == 2
    assert result["external_inductor_id"] == "DEMO_EXT_L_10UH"
    assert result["gap_equivalent_mm"] > 0
    assert math.isclose(result["gap_equivalent_mm"] / result["geometry"].get("gap_step_mm", 0.05), round(result["gap_equivalent_mm"] / 0.05), abs_tol=1e-8)
    assert result["primary_blocks"][0]["turns"] + result["primary_blocks"][1]["turns"] == result["Np"]
    assert len(result["Cps_interface_estimates_F"]) == 2
    assert result["Cps_estimate_F"] is None
    assert result["Lseries_p_H"] == pytest.approx(result["Lleak_p_H"] + result["Lext_p_H"])
    assert result["points"][0]["Psystem_total_W"] > result["points"][0]["Ptotal_W"]


def test_gap_equation_and_unreachable_target():
    db = load_database()
    inp = combined_input()
    result = evaluate_candidate(inp, db, known_gene())
    core = db["assemblies"]["DEMO_CORE_SET2_XL"]
    material = db["materials"][core["material_id"]]
    target = inp["v1_1"]["gap"]["Lm_target_H"]
    reluctance = core["le_mm"] * 1e-3 / material["mu_e"]
    expected_raw_gap_mm = (MU0 * result["Np"] ** 2 * core["Ae_mm2"] * 1e-6 / target - reluctance) * 1e3
    assert abs(result["gap_required_mm"] - expected_raw_gap_mm) < 1e-9
    impossible = copy.deepcopy(inp)
    impossible["v1_1"]["gap"]["Lm_target_H"] = 0.0001
    with pytest.raises(CandidateFailure, match="gap_out_of_manufacturing_range"):
        evaluate_candidate(impossible, db, known_gene())


def test_psp_odd_split_and_voltage_ratio_generates_integer_pairs():
    db = load_database()
    inp = combined_input()
    inp["operating_points"][0]["V2_dc_V"] = 800 / (13 / 7)
    inp["operating_points"][0]["P_req_W"] = 1000
    inp["inductance"]["relative_tolerance"] = 1.0
    inp["design_rules"]["Jp_max_A_per_mm2"] = 100
    inp["design_rules"]["Js_max_A_per_mm2"] = 100
    gene = ("DEMO_CORE_SET2_XL", 13, 7, "DEMO_LITZ_6000x0p1", "DEMO_LITZ_6000x0p1", 1, 1, 2, "DEMO_LAYOUT_PSP_V1_1", "DEMO_EXT_L_10UH", None)
    result = evaluate_candidate(inp, db, gene)
    assert [x["turns"] for x in result["primary_blocks"]] == [6, 7]
    catalog = candidate_catalog(inp, db)
    assert any(g[1] == 13 and g[2] == 7 for g in catalog)


def test_external_inductor_cannot_be_negative_compensation():
    db = load_database()
    inp = combined_input()
    inp["inductance"]["L_series_target_H"] = 0.00001
    inp["inductance"]["relative_tolerance"] = 0.01
    with pytest.raises(CandidateFailure, match="leakage_exceeds_target_no_negative_external"):
        evaluate_candidate(inp, db, known_gene())


def test_secondary_external_inductor_uses_n_squared_and_secondary_current():
    db = load_database()
    inp = combined_input()
    inp["v1_1"]["external"]["external_inductor_ids"] = ["DEMO_EXT_L_10UH_S"]
    inp["operating_points"][0]["P_req_W"] = 10000
    inp["inductance"]["L_series_target_H"] = 0.00006
    inp["inductance"]["relative_tolerance"] = 0.1
    gene = ("DEMO_CORE_SET2_XL", 10, 5, "DEMO_LITZ_6000x0p1", "DEMO_LITZ_12000x0p1", 2, 2, 2, "DEMO_LAYOUT_PSP_V1_1", "DEMO_EXT_L_10UH_S", None)
    result = evaluate_candidate(inp, db, gene)
    assert result["n"] == pytest.approx(2.0)
    assert result["Lext_p_H"] == pytest.approx(40e-6)
    assert result["external_points"][0]["current_A"] == pytest.approx(result["points"][0]["Is_rms_A"])


def test_nsga2_combined_and_core_constraint_filter():
    inp = combined_input()
    result = nsga2_optimization(inp)
    assert result["status"] == "completed"
    assert result["feasible_count"] > 0
    assert result["v1_1"]["enabled"] is True
    constrained = copy.deepcopy(inp)
    constrained["design_rules"]["mass_max_kg"] = 1
    no_solution = nsga2_optimization(constrained)
    assert no_solution["status"] == "no_feasible_solution"
    assert no_solution["diagnostics"]["primary_reason"] in {"mass_max", "geometry_window_width", "turns_ratio"}
