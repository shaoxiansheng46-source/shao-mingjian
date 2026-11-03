"""Phase 5A unified candidate-performance evaluation boundary.

The package composes the already-validated geometry, leakage and winding-loss
services for one immutable candidate and one immutable operating-point
snapshot.  It intentionally does not enter the production optimizer, UI or
synthetic engine.
"""

from .models import (
    EvaluationCandidate,
    EvaluationContext,
    OperatingPointSnapshot,
    canonical_hash,
)
from .service import UnifiedEvaluationService

__all__ = [
    "EvaluationCandidate",
    "EvaluationContext",
    "OperatingPointSnapshot",
    "UnifiedEvaluationService",
    "canonical_hash",
]
