"""Stable, third-party-independent result models for the OpenMagnetics adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderProvenance:
    """Traceability information attached to every provider result."""

    source: str = "OpenMagnetics/MKF via PyOpenMagnetics"
    data_status: str = "external_database"
    model_version: str = "sst-openmagnetics-adapter-0.1.0"
    third_party_package: str = "PyOpenMagnetics"
    third_party_version: str | None = None
    mkf_commit: str | None = None
    mas_commit: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    field: str | None = None
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetricResult:
    """Normalized provider result.

    ``value`` is either one scalar in the declared unit or a small normalized
    summary.  The raw C++/pybind object is deliberately never exposed.
    """

    calculation: str
    value: Any = None
    unit: str | None = None
    model: str | None = None
    material: str | None = None
    status: str = "ok"
    provenance: ProviderProvenance = field(default_factory=ProviderProvenance)
    errors: list[Diagnostic] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = {
            "calculation": self.calculation,
            "value": self.value,
            "unit": self.unit,
            "model": self.model,
            "material": self.material,
            "status": self.status,
            "provenance": self.provenance.as_dict(),
            "errors": [item.as_dict() for item in self.errors],
            "details": self.details,
        }
        return data


def error_result(
    calculation: str,
    diagnostic: Diagnostic,
    provenance: ProviderProvenance,
    *,
    material: str | None = None,
    model: str | None = None,
    status: str = "error",
) -> dict[str, Any]:
    return MetricResult(
        calculation=calculation,
        value=None,
        unit=None,
        model=model,
        material=material,
        status=status,
        provenance=provenance,
        errors=[diagnostic],
    ).as_dict()
