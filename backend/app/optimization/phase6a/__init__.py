"""Phase 6A mixed engineering-variable optimization."""

from .builder import CandidateBuilder, BuildResult
from .case import PhysicalDesignCase, build_external_case, build_synthetic_case
from .evaluator import Phase6AEvaluator
from .models import DesignVariableSpace, Phase6AConfig
from .optimizer import optimize_phase6a

__all__ = [
    "BuildResult",
    "CandidateBuilder",
    "DesignVariableSpace",
    "Phase6AConfig",
    "PhysicalDesignCase",
    "Phase6AEvaluator",
    "build_synthetic_case",
    "build_external_case",
    "optimize_phase6a",
]
