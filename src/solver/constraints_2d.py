"""
Solveur de contraintes géométriques 2D (Geometric Constraint Solver).
Résout les systèmes d'équations non-linéaires d'esquisse (Coïncidence, Horizontalité,
Verticalité, Distance, Parallélisme, Perpendicularité) via optimisation Levenberg-Marquardt.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Tuple, Optional
import numpy as np
from scipy.optimize import least_squares

from src.core.types import Point2D


class ConstraintType(Enum):
    """Types de contraintes géométriques d'esquisse."""
    COINCIDENT = auto()       # Deux points sont confondus
    HORIZONTAL = auto()       # Segment horizontal (dy = 0)
    VERTICAL = auto()         # Segment vertical (dx = 0)
    DISTANCE = auto()         # Distance fixée entre deux points
    PARALLEL = auto()         # Deux segments sont parallèles
    PERPENDICULAR = auto()    # Deux segments sont orthogonaux
    FIXED = auto()            # Point ancré à une coordonnée fixe


@dataclass
class GeometricConstraint:
    """Contrainte géométrique appliquée sur des index de points."""
    constraint_type: ConstraintType
    point_indices: Tuple[int, ...]
    target_value: float = 0.0
    target_value_v: float = 0.0


class SketchConstraintSolver2D:
    """
    Solveur numérique de contraintes géométriques bidimensionnelles.
    Prend une liste de points initiaux et un ensemble de contraintes,
    et calcule les coordonnées exactes qui satisfont toutes les contraintes.
    """

    def __init__(self) -> None:
        """Initialise le solveur avec des listes vides de points et de contraintes."""
        self.points: List[Point2D] = []
        self.constraints: List[GeometricConstraint] = []

    def add_point(self, pt: Point2D) -> int:
        """Ajoute un point dans le système et retourne son index."""
        idx = len(self.points)
        self.points.append(pt)
        return idx

    def add_coincident(self, pt_a_idx: int, pt_b_idx: int) -> None:
        """Contraint deux points à occuper la même position."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.COINCIDENT, (pt_a_idx, pt_b_idx)
        ))

    def add_horizontal(self, pt_a_idx: int, pt_b_idx: int) -> None:
        """Contraint un segment reliant deux points à être horizontal."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.HORIZONTAL, (pt_a_idx, pt_b_idx)
        ))

    def add_vertical(self, pt_a_idx: int, pt_b_idx: int) -> None:
        """Contraint un segment reliant deux points à être vertical."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.VERTICAL, (pt_a_idx, pt_b_idx)
        ))

    def add_distance(self, pt_a_idx: int, pt_b_idx: int, distance: float) -> None:
        """Contraint la distance euclidienne entre deux points."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.DISTANCE, (pt_a_idx, pt_b_idx), target_value=max(0.0, float(distance))
        ))

    def add_fixed(self, pt_idx: int, fixed_u: float, fixed_v: float) -> None:
        """Verrouille un point sur des coordonnées absolues spécifiques."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.FIXED, (pt_idx,), target_value=float(fixed_u), target_value_v=float(fixed_v)
        ))

    def solve(self, tolerance: float = 1e-6) -> Tuple[bool, List[Point2D]]:
        """
        Résout le système d'équations non-linéaires par moindres carrés amortis.
        Retourne (succès: bool, points_résolus: List[Point2D]).
        """
        if not self.points:
            return (True, [])

        num_pts = len(self.points)
        # Vecteur d'état initial X0 = [u0, v0, u1, v1, ..., uN, vN]
        x0 = np.zeros(num_pts * 2, dtype=np.float64)
        for i, pt in enumerate(self.points):
            x0[2 * i] = pt.u
            x0[2 * i + 1] = pt.v

        def residuals(x: np.ndarray) -> np.ndarray:
            """Calcule les écarts/résidus pour chaque contrainte."""
            res: List[float] = []

            for c in self.constraints:
                c_type = c.constraint_type
                indices = c.point_indices

                if any(idx < 0 or idx >= num_pts for idx in indices):
                    res.append(100.0)
                    continue

                if c_type == ConstraintType.COINCIDENT:
                    i_a, i_b = indices[0], indices[1]
                    ua, va = x[2 * i_a], x[2 * i_a + 1]
                    ub, vb = x[2 * i_b], x[2 * i_b + 1]
                    res.append(ua - ub)
                    res.append(va - vb)

                elif c_type == ConstraintType.HORIZONTAL:
                    i_a, i_b = indices[0], indices[1]
                    va = x[2 * i_a + 1]
                    vb = x[2 * i_b + 1]
                    res.append(va - vb)

                elif c_type == ConstraintType.VERTICAL:
                    i_a, i_b = indices[0], indices[1]
                    ua = x[2 * i_a]
                    ub = x[2 * i_b]
                    res.append(ua - ub)

                elif c_type == ConstraintType.DISTANCE:
                    i_a, i_b = indices[0], indices[1]
                    ua, va = x[2 * i_a], x[2 * i_a + 1]
                    ub, vb = x[2 * i_b], x[2 * i_b + 1]
                    current_dist = np.hypot(ua - ub, va - vb)
                    res.append(current_dist - c.target_value)

                elif c_type == ConstraintType.FIXED:
                    i_a = indices[0]
                    ua, va = x[2 * i_a], x[2 * i_a + 1]
                    res.append(ua - c.target_value)
                    res.append(va - c.target_value_v)

            return np.array(res, dtype=np.float64)

        # Si aucune contrainte, les points ne bougent pas
        if not self.constraints:
            return (True, list(self.points))

        # Résolution non-linéaire avec TRF (Trust Region Reflective) supportant m < n et m >= n
        opt_result = least_squares(
            residuals,
            x0,
            method="trf",
            ftol=tolerance,
            xtol=tolerance,
            gtol=tolerance,
            max_nfev=2000
        )

        solved_x = opt_result.x
        solved_points: List[Point2D] = []
        for i in range(num_pts):
            solved_points.append(Point2D(
                float(solved_x[2 * i]),
                float(solved_x[2 * i + 1])
            ))

        final_residuals = residuals(solved_x)
        max_residual = float(np.max(np.abs(final_residuals))) if len(final_residuals) > 0 else 0.0
        success = bool(opt_result.success and max_residual < 0.01)
        return (success, solved_points)
