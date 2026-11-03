"""pymoo 0.6.x mixed-variable NSGA-II adapter."""

from __future__ import annotations

import copy
import time
from threading import Event
from typing import Any

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.callback import Callback
from pymoo.core.problem import Problem
from pymoo.core.mixed import MixedVariableDuplicateElimination, MixedVariableMating, MixedVariableSampling
from pymoo.operators.survival.rank_and_crowding.classes import RankAndCrowding
from pymoo.optimize import minimize
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

from .case import PhysicalDesignCase
from .evaluator import Phase6AEvaluator
from .models import DesignVariableSpace, Phase6AConfig


class OptimizationCancelled(RuntimeError):
    pass


class OptimizationTimedOut(RuntimeError):
    pass


class Phase6AProblem(Problem):
    """Elementwise problem whose X is a dict of real/integer/choice values."""

    def __init__(self, evaluator: Phase6AEvaluator):
        self.evaluator = evaluator
        super().__init__(vars=evaluator.variable_space.variables(), n_obj=2, n_ieq_constr=evaluator.constraint_count, elementwise=True)

    def _evaluate(self, x: dict[str, Any], out: dict[str, Any], **kwargs: Any) -> None:
        record = self.evaluator.evaluate(x)
        out["F"] = np.asarray(record["objectives"], dtype=float)
        out["G"] = np.asarray(record["constraint_vector"], dtype=float)


class Phase6ACallback(Callback):
    def __init__(self, evaluator: Phase6AEvaluator, cancel_event: Event | None = None):
        super().__init__()
        self.evaluator = evaluator
        self.cancel_event = cancel_event
        self.started = time.monotonic()
        self.data["progress"] = []

    def notify(self, algorithm: Any) -> None:
        self.evaluator.current_generation = int(getattr(algorithm, "n_gen", 0) or 0)
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise OptimizationCancelled("optimization cancelled")
        if self.evaluator.config.timeout_s is not None and time.monotonic() - self.started > self.evaluator.config.timeout_s:
            raise OptimizationTimedOut("optimization timeout")
        self.data["progress"].append({"generation": int(getattr(algorithm, "n_gen", 0)), **self.evaluator.summary()})


def _mark_pareto(evaluator: Phase6AEvaluator) -> list[dict[str, Any]]:
    records = [record for record in evaluator.unique_records.values() if record.get("research_feasible")]
    for record in evaluator.unique_records.values():
        record["pareto_rank"] = None
    if not records:
        return []
    matrix = np.asarray([record["objectives"] for record in records], dtype=float)
    front = NonDominatedSorting().do(matrix, only_non_dominated_front=True)
    pareto: list[dict[str, Any]] = []
    for index in front:
        record = records[int(index)]
        record["pareto_rank"] = 0
        pareto.append(copy.deepcopy(record))
    for record in evaluator.records:
        key = record.get("evaluation_key")
        source = evaluator.unique_records.get(key)
        if source is not None:
            record["pareto_rank"] = source.get("pareto_rank")
    return pareto


def optimize_phase6a(
    case: PhysicalDesignCase,
    variable_space: DesignVariableSpace,
    config: Phase6AConfig | None = None,
    *,
    cancel_event: Event | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Run a bounded, reproducible mixed-variable NSGA-II optimization."""

    config = config or Phase6AConfig()
    evaluator = Phase6AEvaluator(case, variable_space, config)
    evaluator.attach_controls(cancel_event=cancel_event, progress_callback=progress_callback)
    callback = Phase6ACallback(evaluator, cancel_event=cancel_event)
    duplicate = MixedVariableDuplicateElimination()
    algorithm = NSGA2(
        pop_size=config.population_size,
        sampling=MixedVariableSampling(),
        mating=MixedVariableMating(eliminate_duplicates=duplicate),
        eliminate_duplicates=duplicate,
        survival=RankAndCrowding(),
    )
    status = "completed"
    error: str | None = None
    try:
        minimize(Phase6AProblem(evaluator), algorithm, termination=("n_gen", config.generations), seed=config.seed, verbose=False, callback=callback)
    except OptimizationCancelled as exc:
        status, error = "cancelled", str(exc)
    except OptimizationTimedOut as exc:
        status, error = "timeout", str(exc)
    except Exception as exc:
        status, error = "optimizer_error", f"{type(exc).__name__}: {exc}"
    pareto = _mark_pareto(evaluator)
    if status == "completed" and not pareto:
        status = "no_research_feasible"
    summary = evaluator.summary()
    result = {
        "status": status,
        "error": error,
        "config": config.as_dict(),
        "variable_space": variable_space.as_dict(),
        "case": case.as_dict(),
        "summary": summary,
        "pareto": pareto,
        "all_unique_candidates": list(evaluator.unique_records.values()),
        "all_evaluation_attempts": list(evaluator.records),
        "progress": callback.data.get("progress", []),
        "reproducibility": {
            "seed": config.seed,
            "model_version": config.model_version,
            "candidate_builder": "sst-phase6a-candidate-builder-0.1.0",
            "pymoo": "0.6.2-compatible-mixed-api",
            "synthetic_fallback": False,
        },
    }
    return result
