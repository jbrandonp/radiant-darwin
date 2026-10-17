"""
Shim rétrocompatible pour le solveur d'esquisse interactif et diagnostic DoF.
La logique du solveur d'esquisse a été unifiée dans le paquet dédié :
`src.solver.live_drag_solver` et `src.solver.unified_solver`.
"""
from __future__ import annotations

from src.solver.live_drag_solver import (
    DragConstraintType,
    DofDiagnosticStatus,
    DofDiagnosticResult,
    DragConstraint,
    diagnose_degrees_of_freedom,
    LiveDragSolver,
)
from src.solver.unified_solver import (
    SolverMode,
    UnifiedSketchSolver,
)

__all__ = [
    "DragConstraintType",
    "DofDiagnosticStatus",
    "DofDiagnosticResult",
    "DragConstraint",
    "diagnose_degrees_of_freedom",
    "LiveDragSolver",
    "SolverMode",
    "UnifiedSketchSolver",
]
