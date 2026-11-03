"""CandidateBuilder: mixed variables -> actual Phase 3 geometry candidate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...evaluation.models import EvaluationCandidate, canonical_hash
from ...geometry import WindingLayout, WindingSpec, build_layout
from .case import PhysicalDesignCase
from .models import DesignVariableSpace


@dataclass(frozen=True)
class BuildResult:
    status: str
    variables: dict[str, Any]
    candidate: EvaluationCandidate | None
    layout: Any | None
    candidate_hash: str
    violations: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "variables": dict(self.variables),
            "candidate": self.candidate.as_dict() if self.candidate else None,
            "layout": self.layout.as_dict() if self.layout is not None else None,
            "candidate_hash": self.candidate_hash,
            "violations": list(self.violations),
        }


class CandidateBuilder:
    """Build one real, serializable structure; it never evaluates physics."""

    def __init__(self, case: PhysicalDesignCase, variable_space: DesignVariableSpace):
        self.case = case
        self.variable_space = variable_space

    def build(self, values: Mapping[str, Any]) -> BuildResult:
        # pymoo's Integer variable can arrive as numpy.int64. Convert scalar
        # values before hashing so the cache boundary remains JSON-canonical.
        plain_values = {str(key): item.item() if hasattr(item, "item") else item for key, item in values.items()}
        raw_hash = canonical_hash({"variables": plain_values, "snapshot": self.case.data_snapshot})
        try:
            variables = self.variable_space.normalize(values)
        except (TypeError, ValueError) as exc:
            return BuildResult("invalid_variables", {}, None, None, raw_hash, [{"code": "INVALID_DESIGN_VARIABLES", "message": str(exc), "severity": "error"}])

        primary_option = self.case.wire_options.get(variables["primary_wire"])
        secondary_option = self.case.wire_options.get(variables["secondary_wire"])
        if primary_option is None or secondary_option is None:
            return BuildResult("unsupported", variables, None, None, raw_hash, [{"code": "UNSUPPORTED_WIRE_CHOICE", "message": "所选真实导线不在本算例数据库快照中。", "severity": "error"}])

        primary_wire = primary_option["wire"]
        secondary_wire = secondary_option["wire"]
        specs = [
            WindingSpec("Primary", "primary", variables["Np"], primary_wire, parallels=1),
            WindingSpec("Secondary", "secondary", variables["Ns"], secondary_wire, parallels=1),
        ]
        template = WindingLayout(
            template_id=variables["layout"],
            block_order=["P", "S"] if variables["layout"] == "PS" else ["P1", "S", "P2"],
            process_clearance_m=0.00015,
            layer_insulation_m=0.0002,
            main_insulation_m=variables["interwinding_gap_m"],
            winding_to_core_clearance_m=variables["core_clearance_m"],
            end_margin_m=0.003,
        )
        primary_segments = (variables["P1"], variables["P2"]) if variables["layout"] == "PSP" else None
        provenance = {
            "data_status": self.case.data_snapshot.get("data_status", "unknown"),
            "synthetic": bool(self.case.data_snapshot.get("synthetic", False)),
            "demo_only": bool(self.case.data_snapshot.get("demo_only", False)),
            "engineering_approved": False,
            "phase6a_candidate_builder": "sst-phase6a-candidate-builder-0.1.0",
        }
        layout = build_layout(self.case.core, specs, template, primary_segments=primary_segments, provenance=provenance)
        wire_specs = {
            "Primary": primary_option["spec"],
            "Secondary": secondary_option["spec"],
            "P": primary_option["spec"],
            "S": secondary_option["spec"],
            "P1": primary_option["spec"],
            "P2": primary_option["spec"],
        }
        candidate_hash = canonical_hash({"variables": variables, "layout": layout.as_dict(), "data_snapshot": self.case.data_snapshot})
        candidate = EvaluationCandidate(
            layout=layout,
            wire_specs=wire_specs,
            data_snapshot=self.case.data_snapshot,
            record_ids={"core": self.case.core.core_id, "material": self.case.core.material_name, "primary_wire": variables["primary_wire"], "secondary_wire": variables["secondary_wire"]},
            candidate_id=f"phase6a-{candidate_hash[:12]}",
        )
        violations = [item.as_dict() for item in layout.violations]
        return BuildResult("geometry_feasible" if layout.feasible else "geometry_infeasible", variables, candidate, layout, candidate_hash, violations)
