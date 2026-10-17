"""
Façade de réexportation rétrocompatible pour les fonctionnalités volumiques 3D avancées.
Les opérations sont désormais modulaires et organisées dans le sous-paquet `src.core.operations` :
- `datums.py` : Plans de référence fixes et dynamiques
- `patterns.py` : Répétitions linéaires, circulaires, miroirs et multi-transformations
- `machining.py` : Révolution, perçage, poche, rainure, nervure, découpe, tuyau
- `surfaces.py` : Lissages, balayages, congés, chanfreins, dépouilles, hélices, évidements
"""
from __future__ import annotations

from src.core.operations import (
    DatumPlaneFeature,
    DatumAttachmentMode,
    DynamicDatumPlaneFeature,
    LinearPatternFeature,
    CircularPatternFeature,
    MirrorFeature,
    MultiTransformStep,
    MultiTransformFeature,
    RevolveFeature,
    HoleFeature,
    PocketFeature,
    GrooveFeature,
    PipeFeature,
    RibFeature,
    SplitFeature,
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
