"""
Solveur de contraintes géométriques 2D (Geometric Constraint Solver).
Résout les systèmes d'équations non-linéaires d'esquisse (Coïncidence, Horizontalité,
Verticalité, Distance, Parallélisme, Perpendicularité) via optimisation Levenberg-Marquardt.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Tuple, Optional, Union
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
    EQUAL = auto()            # Deux segments ont la même longueur
    ANGLE = auto()            # Angle fixé entre deux segments
    POINT_ON_LINE = auto()    # Point aligné sur un segment de droite
    TANGENT = auto()          # Segment de droite tangent à un cercle


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

    def add_parallel(self, pt_a1_idx: int, pt_a2_idx: int, pt_b1_idx: int, pt_b2_idx: int) -> None:
        """Contraint deux segments de droite (A1-A2 et B1-B2) à être parallèles."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.PARALLEL, (pt_a1_idx, pt_a2_idx, pt_b1_idx, pt_b2_idx)
        ))

    def add_perpendicular(self, pt_a1_idx: int, pt_a2_idx: int, pt_b1_idx: int, pt_b2_idx: int) -> None:
        """Contraint deux segments de droite (A1-A2 et B1-B2) à être perpendiculaires."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.PERPENDICULAR, (pt_a1_idx, pt_a2_idx, pt_b1_idx, pt_b2_idx)
        ))

    def add_equal(self, pt_a1_idx: int, pt_a2_idx: int, pt_b1_idx: int, pt_b2_idx: int) -> None:
        """Contraint deux segments de droite à avoir la même longueur euclidienne."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.EQUAL, (pt_a1_idx, pt_a2_idx, pt_b1_idx, pt_b2_idx)
        ))

    def add_angle(
        self,
        pt_a1_idx: int,
        pt_a2_idx: int,
        pt_b1_idx: int,
        pt_b2_idx: int,
        angle_deg: float = 90.0,
        target_angle_deg: Optional[float] = None
    ) -> None:
        """Contraint l'angle géométrique entre deux segments de droite en degrés."""
        val = float(target_angle_deg if target_angle_deg is not None else angle_deg)
        self.constraints.append(GeometricConstraint(
            ConstraintType.ANGLE, (pt_a1_idx, pt_a2_idx, pt_b1_idx, pt_b2_idx), target_value=val
        ))

    def add_point_on_line(self, pt_target_or_line1: int, pt_line1_or_line2: int, pt_line2_or_target: int) -> None:
        """Contraint un point à être aligné sur la droite reliant deux autres points."""
        self.constraints.append(GeometricConstraint(
            ConstraintType.POINT_ON_LINE, (pt_line1_or_line2, pt_line2_or_target, pt_target_or_line1)
        ))

    def add_tangent(
        self,
        pt_line1_idx: int,
        pt_line2_idx: int,
        center: Union[int, Point2D],
        radius: float
    ) -> None:
        """Contraint un segment de droite à être tangent à un cercle (distance centre-droite = rayon)."""
        if isinstance(center, Point2D):
            c_idx = self.add_point(center)
            self.add_fixed(c_idx, center.u, center.v)
        else:
            c_idx = int(center)
        self.constraints.append(GeometricConstraint(
            ConstraintType.TANGENT, (pt_line1_idx, pt_line2_idx, c_idx), target_value=max(0.001, float(radius))
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

        # Si aucune contrainte, les points ne bougent pas
        if not self.constraints:
            return (True, list(self.points))

        # Résolution non-linéaire avec TRF (Trust Region Reflective) supportant m < n et m >= n
        opt_result = least_squares(
            self._evaluate_residuals,
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

        final_residuals = self._evaluate_residuals(solved_x)
        max_residual = float(np.max(np.abs(final_residuals))) if len(final_residuals) > 0 else 0.0
        success = bool(opt_result.success and max_residual < 0.01)
        return (success, solved_points)

    def _evaluate_residuals(self, x: np.ndarray) -> np.ndarray:
        """Calcule le vecteur des résidus de contraintes pour un état x = [u0, v0, ...]."""
        num_pts = len(self.points)
        res: List[float] = []

        for c in self.constraints:
            c_type = c.constraint_type
            indices = c.point_indices
            invalid_index = False
            for idx in indices:
                if idx < 0 or idx >= num_pts:
                    invalid_index = True
                    break
            if invalid_index:
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

            elif c_type == ConstraintType.PARALLEL:
                i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
                dx_a = x[2 * i_a2] - x[2 * i_a1]
                dy_a = x[2 * i_a2 + 1] - x[2 * i_a1 + 1]
                dx_b = x[2 * i_b2] - x[2 * i_b1]
                dy_b = x[2 * i_b2 + 1] - x[2 * i_b1 + 1]
                res.append(dx_a * dy_b - dy_a * dx_b)

            elif c_type == ConstraintType.PERPENDICULAR:
                i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
                dx_a = x[2 * i_a2] - x[2 * i_a1]
                dy_a = x[2 * i_a2 + 1] - x[2 * i_a1 + 1]
                dx_b = x[2 * i_b2] - x[2 * i_b1]
                dy_b = x[2 * i_b2 + 1] - x[2 * i_b1 + 1]
                res.append(dx_a * dx_b + dy_a * dy_b)

            elif c_type == ConstraintType.EQUAL:
                i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
                dist_a = np.hypot(x[2 * i_a2] - x[2 * i_a1], x[2 * i_a2 + 1] - x[2 * i_a1 + 1])
                dist_b = np.hypot(x[2 * i_b2] - x[2 * i_b1], x[2 * i_b2 + 1] - x[2 * i_b1 + 1])
                res.append(dist_a - dist_b)

            elif c_type == ConstraintType.ANGLE:
                i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
                dx_a = x[2 * i_a2] - x[2 * i_a1]
                dy_a = x[2 * i_a2 + 1] - x[2 * i_a1 + 1]
                dx_b = x[2 * i_b2] - x[2 * i_b1]
                dy_b = x[2 * i_b2 + 1] - x[2 * i_b1 + 1]
                len_a = float(np.hypot(dx_a, dy_a))
                len_b = float(np.hypot(dx_b, dy_b))
                if len_a > 1e-9 and len_b > 1e-9:
                    cos_target = float(np.cos(np.radians(c.target_value)))
                    dot_prod = (dx_a * dx_b + dy_a * dy_b) / (len_a * len_b)
                    res.append(dot_prod - cos_target)
                else:
                    res.append(0.0)

            elif c_type == ConstraintType.POINT_ON_LINE:
                i_l1, i_l2, i_p = indices[0], indices[1], indices[2]
                dx_l = x[2 * i_l2] - x[2 * i_l1]
                dy_l = x[2 * i_l2 + 1] - x[2 * i_l1 + 1]
                dx_p = x[2 * i_p] - x[2 * i_l1]
                dy_p = x[2 * i_p + 1] - x[2 * i_l1 + 1]
                len_l = float(np.hypot(dx_l, dy_l))
                if len_l > 1e-9:
                    res.append((dx_l * dy_p - dy_l * dx_p) / len_l)
                else:
                    res.append(0.0)

            elif c_type == ConstraintType.TANGENT:
                i_l1, i_l2, i_c = indices[0], indices[1], indices[2]
                x1, y1 = x[2 * i_l1], x[2 * i_l1 + 1]
                x2, y2 = x[2 * i_l2], x[2 * i_l2 + 1]
                xc, yc = x[2 * i_c], x[2 * i_c + 1]
                dx = x2 - x1
                dy = y2 - y1
                line_len = float(np.hypot(dx, dy))
                if line_len > 1e-9:
                    dist_center = abs(dx * (y1 - yc) - dy * (x1 - xc)) / line_len
                    res.append(dist_center - c.target_value)
                else:
                    res.append(0.0)

        return np.array(res, dtype=np.float64)

    def calculate_degrees_of_freedom(self) -> Tuple[int, str]:
        """
        Calcule les degrés de liberté (DoF) du système d'esquisse (FreeCAD Sketcher Solver Diagnostics).
        Évalue le rang de la matrice Jacobienne numérique des contraintes indépendantes.

        Returns:
            Tuple[int, str]: (DoF, message_diagnostic)
        """
        num_pts = len(self.points)
        num_vars = 2 * num_pts
        if num_vars == 0:
            return (0, "Esquisse vide (0 DoF)")

        if not self.constraints:
            return (num_vars, f"Sous-contrainte ({num_vars} degrés de liberté)")

        # Vecteur de coordonnées initial
        x0 = np.zeros(num_vars, dtype=np.float64)
        for i, pt in enumerate(self.points):
            x0[2 * i] = pt.u
            x0[2 * i + 1] = pt.v

        f0 = self._evaluate_residuals(x0)
        num_equations = len(f0)
        if num_equations == 0:
            return (num_vars, f"Sous-contrainte ({num_vars} degrés de liberté)")

        # Calcul du Jacobien numérique J (m x n) par différences finies
        eps = 1e-7
        j_mat = np.zeros((num_equations, num_vars), dtype=np.float64)
        for j in range(num_vars):
            x_step = x0.copy()
            x_step[j] += eps
            f_step = self._evaluate_residuals(x_step)
            j_mat[:, j] = (f_step - f0) / eps

        rank = int(np.linalg.matrix_rank(j_mat, tol=1e-5))
        dof = max(0, num_vars - rank)

        # Détection des contraintes redondantes ou contradictoires
        has_significant_residual = bool(np.max(np.abs(f0)) > 0.05) if len(f0) > 0 else False
        is_overconstrained = bool(num_equations > rank and has_significant_residual)

        if is_overconstrained:
            status = f"Sur-contrainte / Conflit ({num_equations - rank} équation(s) redondante(s) ou contradictoire(s))"
        elif dof == 0:
            status = "Entièrement contrainte (0 DoF)"
        else:
            status = f"Sous-contrainte ({dof} degré{'s' if dof > 1 else ''} de liberté)"

        return (dof, status)


# Alias pour compatibilité
ConstraintSolver2D = SketchConstraintSolver2D


