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

__all__ = [
    "ConstraintType",
    "GeometricConstraint",
    "GeometricConstraint2D",
    "SketchConstraintSolver2D",
]
