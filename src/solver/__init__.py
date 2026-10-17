"""
Package du solveur de contraintes géométriques 2D (CAD Studio Solver Layer).
Fournit :
- La résolution non linéaire Levenberg-Marquardt des contraintes géométriques
- Le solveur de glisser-déplacer interactif à 60 FPS
- La façade UnifiedSketchSolver pour une intégration transparente
- Le diagnostic complet des degrés de liberté (DDL / DoF)

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

from src.solver.constraints_2d import (
    ConstraintType,
    GeometricConstraint,
    GeometricConstraint2D,
    SketchConstraintSolver2D,
)
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
    # Solveur non linéaire Levenberg-Marquardt
    "ConstraintType",
    "GeometricConstraint",
    "GeometricConstraint2D",
    "SketchConstraintSolver2D",
    # Solveur dynamique temps réel & Diagnostic DoF
    "DragConstraintType",
    "DofDiagnosticStatus",
    "DofDiagnosticResult",
    "DragConstraint",
    "diagnose_degrees_of_freedom",
    "LiveDragSolver",
    # Façade unifiée
    "SolverMode",
    "UnifiedSketchSolver",
]
