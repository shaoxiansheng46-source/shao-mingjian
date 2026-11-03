"""Independent algorithm-only two-objective NSGA-II validation."""

from __future__ import annotations

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize

from examples.phase7_algorithm_benchmark import ConflictingQuadratic


def test_known_conflicting_objectives_produce_a_non_dominated_tradeoff():
    result = minimize(ConflictingQuadratic(), NSGA2(pop_size=24), termination=("n_gen", 30), seed=20261103, verbose=False)
    values = np.asarray(result.F, dtype=float)
    assert values.ndim == 2 and values.shape[1] == 2
    assert float(values[:, 0].min()) < 0.1
    assert float(values[:, 1].min()) < 0.1
    assert float(values[:, 0].max()) > 0.5
    assert float(values[:, 1].max()) > 0.5
