"""Executable V1.1 acceptance smoke checks.

The assertions use model invariants and independently calculated input
variations; they do not substitute fixed candidate counts for optimization.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.engine import CandidateFailure, candidate_catalog, evaluate_candidate, load_database, nsga2_optimization
FIXTURE = ROOT / "SST_V1_4_Demo_Data" / "v1_1" / "examples" / "sample_input_combined.json"
OUTPUT = ROOT / "SST_V1_4_Demo_Data" / "v1_1" / "self_test_results.json"


def main() -> None:
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db = load_database()
    gene = ("DEMO_CORE_SET2_XL", 10, 5, "DEMO_LITZ_6000x0p1", "DEMO_LITZ_12000x0p1", 2, 2, 2, "DEMO_LAYOUT_PSP_V1_1", "DEMO_EXT_L_10UH", None)
    combined = evaluate_candidate(base, db, gene)
    assert combined["gap_equivalent_mm"] > 0
    assert combined["primary_blocks"][0]["turns"] + combined["primary_blocks"][1]["turns"] == 10
    assert combined["Lseries_p_H"] == combined["Lleak_p_H"] + combined["Lext_p_H"]

    impossible = copy.deepcopy(base)
    impossible["v1_1"]["gap"]["Lm_target_H"] = 0.0001
    try:
        evaluate_candidate(impossible, db, gene)
    except CandidateFailure as exc:
        assert str(exc) == "gap_out_of_manufacturing_range"
    else:
        raise AssertionError("unreachable gap target was accepted")

    ratio_case = copy.deepcopy(base)
    ratio_case["operating_points"][0]["V1_dc_V"] = 1500
    ratio_case["operating_points"][0]["V2_dc_V"] = 800
    ratio_case["search"].update({"Np_min": 10, "Np_max": 16, "Np_step": 1})
    pairs = {(x[1], x[2]) for x in candidate_catalog(ratio_case, db)}
    assert (15, 8) in pairs

    power_case = copy.deepcopy(base)
    power_case["operating_points"][0]["P_req_W"] = 50000
    lower_power = evaluate_candidate(power_case, db, gene)
    assert lower_power["points"][0]["Psystem_total_W"] != combined["points"][0]["Psystem_total_W"]

    no_solution = copy.deepcopy(base)
    no_solution["design_rules"]["mass_max_kg"] = 1
    no_solution_result = nsga2_optimization(no_solution)
    assert no_solution_result["status"] == "no_feasible_solution"

    output = {
        "status": "passed",
        "checks": ["combined_case", "gap_unreachable", "integer_voltage_pairs", "power_recalculation", "mass_no_solution"],
        "combined_result": {"candidate_id": combined["candidate_id"], "Np": combined["Np"], "Ns": combined["Ns"], "gap_mm": combined["gap_equivalent_mm"], "Lseries_uH": combined["Lseries_p_H"] * 1e6, "system_loss_W": combined["points"][0]["Psystem_total_W"]},
        "result_metadata": {"data_version": no_solution_result["data_snapshot"]["data_version"], "model_version": no_solution_result["model_version"], "seed": no_solution_result["seed"]},
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
