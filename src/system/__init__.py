"""
Package système pour CAD Studio.
Gère les pools de threads et processus asynchrones, les préférences utilisateur,
et l'historique transactionnel (Undo/Redo).
"""

from src.system.worker_pool import (
    CADWorkerPool,
    WorkerPool,
    TPMSWorkerParams,
    TPMSWorkerResult,
    TessellationWorkerParams,
    TessellationWorkerResult,
    FEAWorkerParams,
    FEAWorkerResult,
    dispatch_to_qt_event_loop,
)
from src.system.preferences import (
    CADPreferences,
    PreferencesManager,
    UnitLength,
    CameraNavigationPreset,
    ThemeMode,
)
from src.system.undo_redo import (
    CADCommand,
    AddFeatureCommand,
    RemoveFeatureCommand,
    ModifyParameterCommand,
    UndoRedoManager,
)

__all__ = [
    "CADWorkerPool",
    "WorkerPool",
    "TPMSWorkerParams",
    "TPMSWorkerResult",
    "TessellationWorkerParams",
    "TessellationWorkerResult",
    "FEAWorkerParams",
    "FEAWorkerResult",
    "dispatch_to_qt_event_loop",
    "CADPreferences",
    "PreferencesManager",
    "UnitLength",
    "CameraNavigationPreset",
    "ThemeMode",
    "CADCommand",
    "AddFeatureCommand",
    "RemoveFeatureCommand",
    "ModifyParameterCommand",
    "UndoRedoManager",
]
