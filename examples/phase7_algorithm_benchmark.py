"""Independent two-objective NSGA-II benchmark for Phase 7.

This is an algorithm test, not an SST design result.  The analytical problem
is f1(x)=x^2 and f2(x)=(x-1)^2 for x in [0, 1], so improving either objective
harms the other and the complete interval is the known Pareto set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import ElementwiseProblem
from pymoo.optimize import minimize


class ConflictingQuadratic(ElementwiseProblem):
    def __init__(self) -> None:
        super().__init__(n_var=1, n_obj=2, n_ieq_constr=0, xl=np.array([0.0]), xu=np.array([1.0]))

    def _evaluate(self, x, out, *args, **kwargs) -> None:
        value = float(x[0])
        out["F"] = [value * value, (value - 1.0) * (value - 1.0)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 independent NSGA-II two-objective benchmark")
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261103)
    parser.add_argument("--output", default=".runtime/phase7_algorithm_benchmark.json")
    args = parser.parse_args()

    result = minimize(ConflictingQuadratic(), NSGA2(pop_size=args.population), termination=("n_gen", args.generations), seed=args.seed, verbose=False)
    values = np.asarray(result.F, dtype=float)
    payload = {
        "status": "passed" if values.size and values.shape[1] == 2 and float(values[:, 0].min()) < 0.1 and float(values[:, 1].min()) < 0.1 else "failed",
        "algorithm_test_only": True,
        "problem": "f1=x^2, f2=(x-1)^2, x in [0,1]",
        "population": args.population,
        "generations": args.generations,
        "seed": args.seed,
        "nondominated_count": int(len(values)),
        "objective_minima": [float(values[:, index].min()) for index in range(2)] if values.size else [],
        "objective_maxima": [float(values[:, index].max()) for index in range(2)] if values.size else [],
        "note": "不得把本结果解释为变压器物理优化结果。",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
