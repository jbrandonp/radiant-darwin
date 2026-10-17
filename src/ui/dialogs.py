"""
Façade de réexportation rétrocompatible pour les boîtes de dialogue Qt.
Les dialogues sont désormais organisés dans le sous-paquet `src.ui.dialogs` :
- `creation_dialogs.py` : Dialogues de primitives et visserie (Box, Cylinder, Cone, etc.)
- `feature_dialogs.py` : Dialogues d'opérations (Extrude, Revolve, Hole, Shell, Loft, etc.)
- `analysis_dialogs.py` : Dialogues d'analyse et simulation (FEA, SheetMetal, Render, Measure, etc.)
"""
from __future__ import annotations

from src.ui.dialogs import (
    CreateBoxDialog,
    CreateCylinderDialog,
    CreateSphereDialog,
    CreateConeDialog,
    CreateTorusDialog,
    CreateWedgeDialog,
    CreatePipeDialog,
    FastenerDialog,
    ExtrudeDialog,
    RevolveDialog,
    HoleDialog,
    ShellDialog,
    CombineDialog,
    LoftDialog,
    SweepDialog,
    FilletDialog,
    ChamferDialog,
    DraftDialog,
    FEADialog,
    ParametersDialog,
    SheetMetalDialog,
    RenderDialog,
    MeasureDialog,
    MeshAnalysisDialog,
    SectionCutDialog,
)

__all__ = [
    "CreateBoxDialog",
    "CreateCylinderDialog",
    "CreateSphereDialog",
    "CreateConeDialog",
    "CreateTorusDialog",
    "CreateWedgeDialog",
    "CreatePipeDialog",
    "FastenerDialog",
    "ExtrudeDialog",
    "RevolveDialog",
    "HoleDialog",
    "ShellDialog",
    "CombineDialog",
    "LoftDialog",
    "SweepDialog",
    "FilletDialog",
    "ChamferDialog",
    "DraftDialog",
    "FEADialog",
    "ParametersDialog",
    "SheetMetalDialog",
    "RenderDialog",
    "MeasureDialog",
    "MeshAnalysisDialog",
    "SectionCutDialog",
]
