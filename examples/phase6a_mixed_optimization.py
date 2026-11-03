"""Run the Phase 6A real-provider mixed-variable optimization.

Example (from repository root):
    python examples/phase6a_mixed_optimization.py --population 4 --generations 2

The script refuses to substitute the synthetic Demo if PyOpenMagnetics is not
available. Results are written under .runtime/, which is intentionally ignored
by Git because they are reproducible run artifacts rather than source data.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

# When executed as ``python examples/...py``, Python initially places the
# examples directory on sys.path rather than the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.optimization.phase6a import DesignVariableSpace, Phase6AConfig, build_external_case, optimize_phase6a
from backend.app.providers.openmagnetics import OpenMagneticsProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="SST Phase 6A real mixed-variable NSGA-II")
    parser.add_argument("--population", type=int, default=4)
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--max-evaluations", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20261103)
    parser.add_argument("--turns-ratio-tolerance", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--np-min", type=int, default=16)
    parser.add_argument("--np-max", type=int, default=24)
    parser.add_argument("--ns-min", type=int, default=4)
    parser.add_argument("--ns-max", type=int, default=8)
    parser.add_argument("--p1-min", type=int, default=1)
    parser.add_argument("--p1-max", type=int, default=23)
    parser.add_argument("--output", default=".runtime/phase6a_mixed_optimization.json")
    parser.add_argument("--csv", dest="csv_output", default=".runtime/phase6a_mixed_optimization.csv")
    args = parser.parse_args()

    provider = OpenMagneticsProvider()
    if not provider.available:
        payload = {"status": "provider_unavailable", "provider": provider.status(), "synthetic_fallback": False}
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    case = build_external_case(provider)
    space = DesignVariableSpace(
        np_bounds=(args.np_min, args.np_max), ns_bounds=(args.ns_min, args.ns_max), p1_bounds=(args.p1_min, min(args.p1_max, args.np_max - 1)),
        interwinding_gap_bounds_m=(0.0004, 0.0015), core_clearance_bounds_m=(0.0003, 0.0012),
        layout_choices=("PS", "PSP"), primary_wire_choices=case.primary_wire_choices,
        secondary_wire_choices=case.secondary_wire_choices,
    )
    config = Phase6AConfig(seed=args.seed, population_size=args.population, generations=args.generations, max_evaluations=args.max_evaluations, timeout_s=args.timeout, turns_ratio_tolerance=args.turns_ratio_tolerance)
    started = time.perf_counter()
    result = optimize_phase6a(case, space, config)
    elapsed = time.perf_counter() - started
    attempts = result.get("all_evaluation_attempts", [])
    result["run_metadata"] = {
        "wall_time_s": elapsed,
        "average_candidate_elapsed_s": (sum(float(item.get("elapsed_s", 0.0)) for item in attempts) / len(attempts)) if attempts else 0.0,
        "provider_available": provider.available,
        "synthetic_fallback": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = Path(args.csv_output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = result["all_unique_candidates"]
    columns = ["candidate_hash", "status", "research_feasible", "pareto_rank", "Np", "Ns", "P1", "P2", "layout", "interwinding_gap_m", "core_clearance_m", "total_loss_W", "volume_m3"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            variables = row.get("variables", {})
            objectives = row.get("objectives", [None, None])
            writer.writerow({
                "candidate_hash": row.get("candidate_hash"), "status": row.get("status"), "research_feasible": row.get("research_feasible"), "pareto_rank": row.get("pareto_rank"),
                "Np": variables.get("Np"), "Ns": variables.get("Ns"), "P1": variables.get("P1"), "P2": variables.get("P2"), "layout": variables.get("layout"),
                "interwinding_gap_m": variables.get("interwinding_gap_m"), "core_clearance_m": variables.get("core_clearance_m"), "total_loss_W": objectives[0], "volume_m3": objectives[1],
            })
    print(json.dumps({"status": result["status"], "summary": result["summary"], "pareto_count": len(result["pareto"]), "json": str(output), "csv": str(csv_path)}, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"completed", "no_research_feasible"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
