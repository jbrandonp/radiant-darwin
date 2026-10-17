"""Subpackage de boîtes de dialogue Qt."""
from __future__ import annotations

from src.ui.dialogs.creation_dialogs import (
    CreateBoxDialog,
    CreateCylinderDialog,
    CreateSphereDialog,
    CreateConeDialog,
    CreateTorusDialog,
    CreateWedgeDialog,
    CreatePipeDialog,
    FastenerDialog,
)
from src.ui.dialogs.feature_dialogs import (
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
)
from src.ui.dialogs.analysis_dialogs import (
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
