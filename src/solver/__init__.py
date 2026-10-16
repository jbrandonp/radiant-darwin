"""
Package du solveur de contraintes géométriques 2D (CAD Studio Solver Layer).
Fournit la résolution non linéaire Levenberg-Marquardt des contraintes géométriques.

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

from src.solver.constraints_2d import (
    ConstraintType,
    GeometricConstraint,
    GeometricConstraint2D,
    SketchConstraintSolver2D,
)
from src.core.live_sketch_solver import (
    DragConstraintType,
    DofDiagnosticStatus,
    DofDiagnosticResult,
    DragConstraint,
    diagnose_degrees_of_freedom,
    LiveDragSolver,
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
]
