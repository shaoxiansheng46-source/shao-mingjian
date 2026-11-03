"""OpenMagnetics adapter boundary.

The package is intentionally lazy: importing it does not require PyOpenMagnetics
to be installed in the production Demo environment.
"""

from .mas_adapter import MasAdapter, MasAdapterError
from .models import MetricResult, ProviderProvenance
from .provider import OpenMagneticsProvider

__all__ = [
    "MasAdapter",
    "MasAdapterError",
    "MetricResult",
    "OpenMagneticsProvider",
    "ProviderProvenance",
]
