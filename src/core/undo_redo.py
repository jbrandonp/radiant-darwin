"""
Shim de rétrocompatibilité pour le gestionnaire transactionnel Undo/Redo.
Redirige de manière transparente vers src.system.undo_redo.
"""

from __future__ import annotations
from src.system.undo_redo import (
    CADCommand,
    AddFeatureCommand,
    RemoveFeatureCommand,
    ModifyParameterCommand,
    TransformBodyCommand,
    UndoRedoManager,
)

__all__ = [
    "CADCommand",
    "AddFeatureCommand",
    "RemoveFeatureCommand",
    "ModifyParameterCommand",
    "TransformBodyCommand",
    "UndoRedoManager",
]
