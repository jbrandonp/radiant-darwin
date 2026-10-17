"""
Package d'opérations géométriques et volumiques modulaires.
Divisé en :
- datums : Plans de référence fixes et dynamiques
- patterns : Répétitions linéaires, circulaires, miroirs et multi-transformations
- machining : Formes volumiques et usinages (révolution, perçage, poche, rainure, etc.)
- surfaces : Lissages, balayages, congés, chanfreins, dépouilles, hélices, évidements
"""
from __future__ import annotations

from src.core.operations.datums import (
    DatumPlaneFeature,
    DatumAttachmentMode,
    DynamicDatumPlaneFeature,
)
from src.core.operations.patterns import (
    LinearPatternFeature,
    CircularPatternFeature,
    MirrorFeature,
    MultiTransformStep,
    MultiTransformFeature,
)
from src.core.operations.machining import (
    RevolveFeature,
    HoleFeature,
    PocketFeature,
    GrooveFeature,
    PipeFeature,
    RibFeature,
    SplitFeature,
)
from src.core.operations.surfaces import (
    _resample_profile,
    ShellFeature,
    LoftFeature,
    SweepFeature,
    FilletFeature,
    ChamferFeature,
    DraftFeature,
    HelixFeature,
    SubtractiveLoftFeature,
    SubtractiveSweepFeature,
    VariableRadiusFilletFeature,
    MultiRailLoftFeature,
)

__all__ = [
    "DatumPlaneFeature",
    "DatumAttachmentMode",
    "DynamicDatumPlaneFeature",
    "LinearPatternFeature",
    "CircularPatternFeature",
    "MirrorFeature",
    "MultiTransformStep",
    "MultiTransformFeature",
    "RevolveFeature",
    "HoleFeature",
    "PocketFeature",
    "GrooveFeature",
    "PipeFeature",
    "RibFeature",
    "SplitFeature",
    "_resample_profile",
    "ShellFeature",
    "LoftFeature",
    "SweepFeature",
    "FilletFeature",
    "ChamferFeature",
    "DraftFeature",
    "HelixFeature",
    "SubtractiveLoftFeature",
    "SubtractiveSweepFeature",
    "VariableRadiusFilletFeature",
    "MultiRailLoftFeature",
]
