"""
Façade unifiée du solveur d'esquisse 2D (UnifiedSketchSolver).
Intègre harmonieusement :
- Résolution globale rigoureuse non linéaire par Levenberg-Marquardt (SketchConstraintSolver2D)
- Projection géométrique temps réel à 60 FPS pour manipulation interactive (LiveDragSolver)
- Diagnostic continu des degrés de liberté (DDL / DoF)
Typage statique strict : zéro Any, zéro object, complexité cognitive <= 25.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Tuple

from src.core.types import Point2D
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


class SolverMode(str, Enum):
    """Modes de fonctionnement du solveur d'esquisse unifié."""
    INTERACTIVE = "interactive"  # Mode 60 FPS par projection pour glisser-déplacer souris
    RIGOROUS = "rigorous"        # Mode d'optimisation non linéaire Levenberg-Marquardt
    AUTO = "auto"                # Choix automatique selon le contexte d'appel


class UnifiedSketchSolver:
    """
    Moteur unifié de résolution de contraintes d'esquisse 2D.
    Fournit une interface unique et cohérente pour l'ensemble du cycle de vie d'une esquisse.
    """

    def __init__(self, tolerance: float = 1e-5, max_iterations: int = 100) -> None:
        self.tolerance: float = tolerance
        self.max_iterations: int = max_iterations
        self._rigorous_solver: SketchConstraintSolver2D = SketchConstraintSolver2D()
        self._interactive_solver: LiveDragSolver = LiveDragSolver(tolerance=tolerance)

    @property
    def rigorous_solver(self) -> SketchConstraintSolver2D:
        """Accès au solveur d'optimisation Levenberg-Marquardt sous-jacent."""
        return self._rigorous_solver

    @property
    def interactive_solver(self) -> LiveDragSolver:
        """Accès au solveur interactif par projection temps réel."""
        return self._interactive_solver

    def solve_interactive_drag(
        self,
        dragged_index: int,
        target_pos: Point2D,
        active_constraints: List[DragConstraint]
    ) -> Point2D:
        """
        Résout le déplacement dynamique à la souris en moins de 2ms par projection directe.
        """
        return self._interactive_solver.live_drag_step(
            dragged_index=dragged_index,
            target_pos=target_pos,
            active_constraints=active_constraints
        )

    def solve_rigorous(self) -> Tuple[bool, List[Point2D]]:
        """
        Exécute la convergence globale Levenberg-Marquardt de toutes les contraintes déclarées.
        """
        return self._rigorous_solver.solve(max_iterations=self.max_iterations, tolerance=self.tolerance)

    def diagnose_dof(self, num_points: int, num_independent_constraints: int) -> DofDiagnosticResult:
        """
        Calcule le bilan d'isostatisme (degrés de liberté restants ou surcontraintes).
        """
        return diagnose_degrees_of_freedom(num_points, num_independent_constraints)

    def reset(self) -> None:
        """Réinitialise les solveurs pour une nouvelle session de calcul."""
        self._rigorous_solver = SketchConstraintSolver2D()
        self._interactive_solver = LiveDragSolver(tolerance=self.tolerance)
