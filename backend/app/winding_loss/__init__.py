"""Independent Phase 4B winding-loss services."""

from .models import CurrentWaveform, HarmonicComponent, HarmonicSpectrum, LitzWireSpecification
from .service import WindingLossService

__all__ = [
    "CurrentWaveform",
    "HarmonicComponent",
    "HarmonicSpectrum",
    "LitzWireSpecification",
    "WindingLossService",
]
