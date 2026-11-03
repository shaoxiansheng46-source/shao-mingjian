"""Phase 6A independent orchestration and mixed-variable tests.

Tests using ``RecordingEvaluationService`` validate only the orchestration
contract. They are not presented as physical validation. The real-provider
integration is exercised separately by the example and is skipped when the
isolated PyOpenMagnetics runtime is not on PYTHONPATH.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.mixed import MixedVariableDuplicateElimination, MixedVariableMating, MixedVariableSampling
from pymoo.optimize import minimize
from pymoo.operators.survival.rank_and_crowding.classes import RankAndCrowding

from backend.app.evaluation import UnifiedEvaluationService
from backend.app.optimization.phase6a import CandidateBuilder, DesignVariableSpace, Phase6AConfig, Phase6AEvaluator, build_synthetic_case
from backend.app.optimization.phase6a.optimizer import Phase6AProblem, optimize_phase6a
from backend.app.providers.openmagnetics import OpenMagneticsProvider


@pytest.fixture()
def case():
    return build_synthetic_case()


@pytest.fixture()
def space(case):
    return DesignVariableSpace(
        np_bounds=(16, 24), ns_bounds=(4, 8), p1_bounds=(1, 23),
        interwinding_gap_bounds_m=(0.0004, 0.0015), core_clearance_bounds_m=(0.0003, 0.0012),
        layout_choices=("PS", "PSP"), primary_wire_choices=case.primary_wire_choices, secondary_wire_choices=case.secondary_wire_choices,
    )


def values(**overrides):
    result = {"Np": 20, "Ns": 5, "P1": 9, "interwinding_gap_m": 0.0005, "core_clearance_m": 0.0005, "layout": "PSP", "primary_wire": "TEST_LITZ", "secondary_wire": "TEST_LITZ"}
    result.update(overrides)
    return result


def test_mixed_variables_are_integer_choice_and_real(space):
    variables = space.variables()
    assert variables["Np"].__class__.__name__ == "Integer"
    assert variables["Ns"].__class__.__name__ == "Integer"
    assert variables["layout"].__class__.__name__ == "Choice"
    assert space.normalize(values())["Np"] == 20
    with pytest.raises(ValueError, match="NON_INTEGER_VARIABLE"):
        space.normalize(values(Np=20.5))


def test_psp_series_split_and_geometry_changes(case, space):
    builder = CandidateBuilder(case, space)
    psp = builder.build(values(P1=9))
    assert psp.status == "geometry_feasible"
    assert [block.name for block in psp.layout.blocks] == ["P1", "S", "P2"]
    assert psp.layout.blocks[0].turns + psp.layout.blocks[2].turns == 20
    assert psp.layout.connection["type"] == "series"
    assert psp.layout.connection["direction"] == "same"
    changed = builder.build(values(P1=11, interwinding_gap_m=0.0012))
    assert changed.layout.blocks[0].turns != psp.layout.blocks[0].turns
    assert changed.layout.blocks[1].radial_start_m > psp.layout.blocks[1].radial_start_m


def test_ps_and_psp_have_different_actual_layout(case, space):
    builder = CandidateBuilder(case, space)
    ps = builder.build(values(layout="PS"))
    psp = builder.build(values(layout="PSP"))
    assert ps.layout.feasible and psp.layout.feasible
    assert len(ps.layout.blocks) == 2
    assert len(psp.layout.blocks) == 3
    assert ps.candidate_hash != psp.candidate_hash
    assert ps.layout.as_dict() != psp.layout.as_dict()


def test_unmanufacturable_structure_is_rejected(case, space):
    builder = CandidateBuilder(case, space)
    result = builder.build(values(Np=24, Ns=8, P1=1, interwinding_gap_m=0.0015, core_clearance_m=0.0012))
    assert result.status == "geometry_infeasible"
    assert any(item["code"] == "WINDOW_RADIAL_OVERFLOW" for item in result.violations)


class RecordingEvaluationService:
    """A test double for cache/orchestration only; never used as production fallback."""

    def __init__(self):
        self.calls = 0

    def evaluate(self, candidate, operating_point, **kwargs):
        self.calls += 1
        total_turns = sum(block.turns for block in candidate.layout.blocks)
        return {
            "status": "partial",
            "candidate_hash": f"stub-{total_turns}",
            "openmagnetics": {"calculations": {"openmagnetics": {"core_losses": {"value": 1.0 + total_turns / 100.0, "details": {"magnetic_flux_density_peak_t": 0.02}, "status": "ok"}, "magnetizing_inductance": {"value": 500e-6, "status": "ok"}}}},
            "losses": {"winding": {"openmagnetics_full": {"value": 0.5, "status": "ok"}}},
            "electromagnetic": {"leakage": {"value": 1e-6, "status": "ok"}},
            "diagnostics": [],
        }


def test_cache_reuses_same_candidate_and_result(case, space):
    stub = RecordingEvaluationService()
    evaluator = Phase6AEvaluator(case, space, Phase6AConfig(lm_min_h=100e-6, lm_max_h=1e-3, bmax_max_t=0.2), evaluation_service=stub)
    first = evaluator.evaluate(values(layout="PS"))
    second = evaluator.evaluate(values(layout="PS"))
    assert stub.calls == 1
    assert first["objectives"] == second["objectives"]
    assert second["cache_hit"] is True
    assert evaluator.summary()["cache_hits"] == 1


def test_provider_unavailable_does_not_silently_fallback(case, space):
    external_like = deepcopy(case)
    object.__setattr__(external_like, "requires_external_provider", True)
    object.__setattr__(external_like, "provider", OpenMagneticsProvider(initialize=False))
    evaluator = Phase6AEvaluator(external_like, space, Phase6AConfig())
    record = evaluator.evaluate(values(layout="PS"))
    assert record["status"] == "provider_unavailable"
    assert record["research_feasible"] is False
    assert record["objectives"][0] == 1.0e9
    assert any(item["code"] == "OPENMAGNETICS_UNAVAILABLE" for item in record["diagnostics"])


def test_pymoo_nsga2_uses_mixed_variables_and_non_dominated_sorting(space):
    class AlgorithmOnlyEvaluator:
        variable_space = space
        constraint_count = 1

        @staticmethod
        def evaluate(x):
            return {"objectives": [float(x["Np"]), float(x["interwinding_gap_m"])], "constraint_vector": [-1.0]}

    problem = Phase6AProblem(AlgorithmOnlyEvaluator())
    duplicate = MixedVariableDuplicateElimination()
    algorithm = NSGA2(pop_size=6, sampling=MixedVariableSampling(), mating=MixedVariableMating(eliminate_duplicates=duplicate), eliminate_duplicates=duplicate, survival=RankAndCrowding())
    result = minimize(problem, algorithm, termination=("n_gen", 2), seed=17, verbose=False)
    assert len(result.pop) > 0
    assert all(float(item["Np"]).is_integer() and float(item["Ns"]).is_integer() for item in result.pop.get("X"))
    assert all(item["layout"] in {"PS", "PSP"} for item in result.pop.get("X"))


def test_no_provider_run_has_no_fake_pareto(case, space):
    external_like = deepcopy(case)
    object.__setattr__(external_like, "requires_external_provider", True)
    object.__setattr__(external_like, "provider", OpenMagneticsProvider(initialize=False))
    result = optimize_phase6a(external_like, space, Phase6AConfig(population_size=3, generations=1, max_evaluations=6, timeout_s=30))
    assert result["status"] == "no_research_feasible"
    assert result["pareto"] == []
    assert result["summary"]["research_feasible"] == 0
