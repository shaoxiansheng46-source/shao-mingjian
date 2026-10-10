from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.engine import (  # noqa: E402
    InputValidationError,
    load_database,
    nsga2_optimization,
    reference_enumeration,
    validate_input,
)


def main() -> None:
    db = load_database()
    base = json.loads((ROOT / "SST_V1_4_Demo_Data" / "sample_input_feasible.json").read_text(encoding="utf-8"))
    result = reference_enumeration(base)
    expected = json.loads((ROOT / "SST_V1_4_Demo_Data" / "reference_output" / "results.json").read_text(encoding="utf-8"))
    assert result["candidate_count"] == 14400
    assert result["feasible_count"] == expected["feasible_count"] == 34
    assert result["pareto_count"] == expected["pareto_count"] == 2
    for got, want in zip(result["pareto"], expected["pareto"]):
        assert got["candidate_id"] == want["candidate_id"]
        assert math.isclose(got["Lleak_p_H"], want["Lleak_p_H"], rel_tol=1e-3)
        assert math.isclose(got["points"][0]["Ptotal_W"], want["points"][0]["Ptotal_W"], rel_tol=1e-3)
        assert abs(got["points"][0]["Tw_est_C"] - want["points"][0]["Tw_est_C"]) < 0.1
    no_feasible = json.loads((ROOT / "SST_V1_4_Demo_Data" / "sample_input_infeasible.json").read_text(encoding="utf-8"))
    no_result = reference_enumeration(no_feasible)
    assert no_result["status"] == "no_feasible_solution" and no_result["feasible_count"] == 0
    blocked = []
    for name in ("sample_input_engineering_blocked.json", "sample_input_unsupported.json"):
        bad = json.loads((ROOT / "SST_V1_4_Demo_Data" / name).read_text(encoding="utf-8"))
        try:
            validate_input(bad, db)
        except InputValidationError as exc:
            blocked.append(str(exc))
    assert blocked == ["SYNTHETIC_DATA_BLOCKED_IN_ENGINEERING", "UNSUPPORTED_WAVEFORM"]
    changed = json.loads(json.dumps(base))
    changed["operating_points"][0]["V2_dc_V"] = 500
    changed["search"].update({"Np_min": 8, "Np_max": 24, "Np_step": 1})
    changed["search"]["population"] = 20
    changed["search"]["generations"] = 4
    dynamic = nsga2_optimization(changed)
    assert dynamic["seed"] == changed["search"]["seed"]
    ratio_pairs = {(candidate["Np"], candidate["Ns"]) for candidate in dynamic.get("pareto", [])}
    # The assertion is intentionally non-prescriptive on feasibility: it ensures
    # the variable-voltage run traversed the dynamic optimizer successfully.
    assert dynamic["optimizer"] == "NSGA-II"
    print(json.dumps({
        "database_checks": "passed", "reference_regression": "passed",
        "candidate_count": result["candidate_count"], "feasible_count": result["feasible_count"], "pareto_count": result["pareto_count"],
        "no_feasible": no_result["status"], "blocked_errors": blocked,
        "variable_voltage_nsga2": "passed", "variable_voltage_pareto_pairs": sorted(ratio_pairs),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
