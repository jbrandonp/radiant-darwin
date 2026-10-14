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
    G2_CURVATURE = auto()     # Continuité de courbure G2 (alignement des tangentes et égalité des rayons de courbure)
    EXTERNAL_REFERENCE = auto() # Projection de géométrie 3D externe dans le plan d'esquisse


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

    def add_g2_curvature(
        self,
        pt_a0_idx: int,
        pt_a1_idx: int,
        pt_joint_idx: int,
        pt_b1_idx: int,
        pt_b2_idx: int,
    ) -> None:
        """
        Contraint deux courbes se rejoignant en un point commun (pt_joint)
        à avoir une continuité de courbure G2 stricte (même tangente G1 et même rayon de courbure G2).
        """
        self.constraints.append(GeometricConstraint(
            ConstraintType.G2_CURVATURE,
            (pt_a0_idx, pt_a1_idx, pt_joint_idx, pt_b1_idx, pt_b2_idx)
        ))

    def add_external_reference(
        self,
        pt_idx: int,
        ref_u: float,
        ref_v: float
    ) -> None:
        """
        Lie un point d'esquisse à une coordonnée de référence 2D issue d'une arête 3D externe projetée.
        """
        self.constraints.append(GeometricConstraint(
            ConstraintType.EXTERNAL_REFERENCE,
            (pt_idx,),
            target_value=float(ref_u),
            target_value_v=float(ref_v)
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

        # Résolution non-linéaire avec Jacobien analytique et TRF (Trust Region Reflective)
        opt_result = least_squares(
            self._evaluate_residuals,
            x0,
            jac=self._evaluate_jacobian,
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
            res.extend(self._eval_single_constraint_residual(c, x, num_pts))
        return np.array(res, dtype=np.float64)

    def _eval_single_constraint_residual(self, c: GeometricConstraint2D, x: np.ndarray, num_pts: int) -> List[float]:
        """Calcule les résidus pour une seule contrainte géométrique."""
        c_type = c.constraint_type
        indices = c.point_indices
        for idx in indices:
            if idx < 0 or idx >= num_pts:
                return [100.0]

        if c_type == ConstraintType.COINCIDENT:
            i_a, i_b = indices[0], indices[1]
            return [float(x[2 * i_a] - x[2 * i_b]), float(x[2 * i_a + 1] - x[2 * i_b + 1])]

        if c_type == ConstraintType.HORIZONTAL:
            i_a, i_b = indices[0], indices[1]
            return [float(x[2 * i_a + 1] - x[2 * i_b + 1])]

        if c_type == ConstraintType.VERTICAL:
            i_a, i_b = indices[0], indices[1]
            return [float(x[2 * i_a] - x[2 * i_b])]

        if c_type == ConstraintType.DISTANCE:
            i_a, i_b = indices[0], indices[1]
            cur_dist = float(np.hypot(x[2 * i_a] - x[2 * i_b], x[2 * i_a + 1] - x[2 * i_b + 1]))
            return [cur_dist - c.target_value]

        if c_type in (ConstraintType.FIXED, ConstraintType.EXTERNAL_REFERENCE):
            i_a = indices[0]
            return [float(x[2 * i_a] - c.target_value), float(x[2 * i_a + 1] - c.target_value_v)]

        if c_type == ConstraintType.PARALLEL:
            i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
            dx_a = x[2 * i_a2] - x[2 * i_a1]
            dy_a = x[2 * i_a2 + 1] - x[2 * i_a1 + 1]
            dx_b = x[2 * i_b2] - x[2 * i_b1]
            dy_b = x[2 * i_b2 + 1] - x[2 * i_b1 + 1]
            return [float(dx_a * dy_b - dy_a * dx_b)]

        if c_type == ConstraintType.PERPENDICULAR:
            i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
            dx_a = x[2 * i_a2] - x[2 * i_a1]
            dy_a = x[2 * i_a2 + 1] - x[2 * i_a1 + 1]
            dx_b = x[2 * i_b2] - x[2 * i_b1]
            dy_b = x[2 * i_b2 + 1] - x[2 * i_b1 + 1]
            return [float(dx_a * dx_b + dy_a * dy_b)]

        if c_type == ConstraintType.EQUAL:
            i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
            dist_a = float(np.hypot(x[2 * i_a2] - x[2 * i_a1], x[2 * i_a2 + 1] - x[2 * i_a1 + 1]))
            dist_b = float(np.hypot(x[2 * i_b2] - x[2 * i_b1], x[2 * i_b2 + 1] - x[2 * i_b1 + 1]))
            return [dist_a - dist_b]

        if c_type == ConstraintType.ANGLE:
            i_a1, i_a2, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3]
            dx_a = x[2 * i_a2] - x[2 * i_a1]
            dy_a = x[2 * i_a2 + 1] - x[2 * i_a1 + 1]
            dx_b = x[2 * i_b2] - x[2 * i_b1]
            dy_b = x[2 * i_b2 + 1] - x[2 * i_b1 + 1]
            len_a = float(np.hypot(dx_a, dy_a))
            len_b = float(np.hypot(dx_b, dy_b))
            if len_a > 1e-9 and len_b > 1e-9:
                cos_target = float(np.cos(np.radians(c.target_value)))
                dot_prod = float((dx_a * dx_b + dy_a * dy_b) / (len_a * len_b))
                return [dot_prod - cos_target]
            return [0.0]

        if c_type == ConstraintType.POINT_ON_LINE:
            i_l1, i_l2, i_p = indices[0], indices[1], indices[2]
            dx_l = x[2 * i_l2] - x[2 * i_l1]
            dy_l = x[2 * i_l2 + 1] - x[2 * i_l1 + 1]
            dx_p = x[2 * i_p] - x[2 * i_l1]
            dy_p = x[2 * i_p + 1] - x[2 * i_l1 + 1]
            len_l = float(np.hypot(dx_l, dy_l))
            return [float((dx_l * dy_p - dy_l * dx_p) / len_l)] if len_l > 1e-9 else [0.0]

        if c_type == ConstraintType.TANGENT:
            i_l1, i_l2, i_c = indices[0], indices[1], indices[2]
            x1, y1 = x[2 * i_l1], x[2 * i_l1 + 1]
            x2, y2 = x[2 * i_l2], x[2 * i_l2 + 1]
            xc, yc = x[2 * i_c], x[2 * i_c + 1]
            dx = x2 - x1
            dy = y2 - y1
            line_len = float(np.hypot(dx, dy))
            if line_len > 1e-9:
                dist_center = float(abs(dx * (y1 - yc) - dy * (x1 - xc)) / line_len)
                return [dist_center - c.target_value]
            return [0.0]

        if c_type == ConstraintType.G2_CURVATURE:
            i_a0, i_a1, i_joint, i_b1, i_b2 = indices[0], indices[1], indices[2], indices[3], indices[4]
            v_ax = x[2 * i_joint] - x[2 * i_a1]
            v_ay = x[2 * i_joint + 1] - x[2 * i_a1 + 1]
            v_bx = x[2 * i_b1] - x[2 * i_joint]
            v_by = x[2 * i_b1 + 1] - x[2 * i_joint + 1]
            g1_res = float(v_ax * v_by - v_ay * v_bx)

            a_ax = x[2 * i_joint] - 2.0 * x[2 * i_a1] + x[2 * i_a0]
            a_ay = x[2 * i_joint + 1] - 2.0 * x[2 * i_a1 + 1] + x[2 * i_a0 + 1]
            v_a_norm_sq = float(v_ax * v_ax + v_ay * v_ay)
            a_bx = x[2 * i_b2] - 2.0 * x[2 * i_b1] + x[2 * i_joint]
            a_by = x[2 * i_b2 + 1] - 2.0 * x[2 * i_b1 + 1] + x[2 * i_joint + 1]
            v_b_norm_sq = float(v_bx * v_bx + v_by * v_by)

            g2_res = 0.0
            if v_a_norm_sq > 1e-12 and v_b_norm_sq > 1e-12:
                kappa_a = (v_ax * a_ay - v_ay * a_ax) / (v_a_norm_sq ** 1.5)
                kappa_b = (v_bx * a_by - v_by * a_bx) / (v_b_norm_sq ** 1.5)
                g2_res = float(kappa_a - kappa_b)
            return [g1_res, g2_res]

        return [0.0]

    def _evaluate_jacobian(self, x: np.ndarray) -> np.ndarray:
        """
        Calcule la matrice Jacobienne exacte J = df/dx (m équations x n variables).
        Fournit les dérivées partielles analytiques pour accélérer la convergence Levenberg-Marquardt.
        """
        num_pts = len(self.points)
        num_vars = 2 * num_pts
        f0 = self._evaluate_residuals(x)
        num_eqs = len(f0)
        j_mat = np.zeros((num_eqs, num_vars), dtype=np.float64)

        row = 0
        for c in self.constraints:
            row += self._fill_single_constraint_jacobian(c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)

        return j_mat

    def _fill_single_constraint_jacobian(
        self,
        c: GeometricConstraint2D,
        x: np.ndarray,
        j_mat: np.ndarray,
        row: int,
        num_pts: int,
        f0: np.ndarray,
        num_vars: int,
        num_eqs: int
    ) -> int:
        """Remplit les dérivées partielles analytiques pour une contrainte et retourne le nombre de lignes écrites."""
        c_type = c.constraint_type
        indices = c.point_indices

        for idx in indices:
            if idx < 0 or idx >= num_pts:
                num_sub_eqs = 2 if c_type in (ConstraintType.COINCIDENT, ConstraintType.FIXED, ConstraintType.EXTERNAL_REFERENCE, ConstraintType.G2_CURVATURE) else 1
                return num_sub_eqs

        if c_type == ConstraintType.COINCIDENT:
            ia, ib = indices[0], indices[1]
            j_mat[row, 2 * ia] = 1.0
            j_mat[row, 2 * ib] = -1.0
            j_mat[row + 1, 2 * ia + 1] = 1.0
            j_mat[row + 1, 2 * ib + 1] = -1.0
            return 2

        if c_type == ConstraintType.HORIZONTAL:
            ia, ib = indices[0], indices[1]
            j_mat[row, 2 * ia + 1] = 1.0
            j_mat[row, 2 * ib + 1] = -1.0
            return 1

        if c_type == ConstraintType.VERTICAL:
            ia, ib = indices[0], indices[1]
            j_mat[row, 2 * ia] = 1.0
            j_mat[row, 2 * ib] = -1.0
            return 1

        if c_type == ConstraintType.DISTANCE:
            ia, ib = indices[0], indices[1]
            dx = x[2 * ib] - x[2 * ia]
            dy = x[2 * ib + 1] - x[2 * ia + 1]
            dist = float(np.hypot(dx, dy))
            if dist > 1e-12:
                j_mat[row, 2 * ia] = -dx / dist
                j_mat[row, 2 * ia + 1] = -dy / dist
                j_mat[row, 2 * ib] = dx / dist
                j_mat[row, 2 * ib + 1] = dy / dist
            return 1

        if c_type in (ConstraintType.FIXED, ConstraintType.EXTERNAL_REFERENCE):
            ia = indices[0]
            j_mat[row, 2 * ia] = 1.0
            j_mat[row + 1, 2 * ia + 1] = 1.0
            return 2

        if c_type == ConstraintType.PARALLEL:
            ia1, ia2, ib1, ib2 = indices[0], indices[1], indices[2], indices[3]
            dx_a = x[2 * ia2] - x[2 * ia1]
            dy_a = x[2 * ia2 + 1] - x[2 * ia1 + 1]
            dx_b = x[2 * ib2] - x[2 * ib1]
            dy_b = x[2 * ib2 + 1] - x[2 * ib1 + 1]
            j_mat[row, 2 * ia1] = -dy_b
            j_mat[row, 2 * ia2] = dy_b
            j_mat[row, 2 * ia1 + 1] = dx_b
            j_mat[row, 2 * ia2 + 1] = -dx_b
            j_mat[row, 2 * ib1] = dy_a
            j_mat[row, 2 * ib2] = -dy_a
            j_mat[row, 2 * ib1 + 1] = -dx_a
            j_mat[row, 2 * ib2 + 1] = dx_a
            return 1

        if c_type == ConstraintType.PERPENDICULAR:
            ia1, ia2, ib1, ib2 = indices[0], indices[1], indices[2], indices[3]
            dx_a = x[2 * ia2] - x[2 * ia1]
            dy_a = x[2 * ia2 + 1] - x[2 * ia1 + 1]
            dx_b = x[2 * ib2] - x[2 * ib1]
            dy_b = x[2 * ib2 + 1] - x[2 * ib1 + 1]
            j_mat[row, 2 * ia1] = -dx_b
            j_mat[row, 2 * ia2] = dx_b
            j_mat[row, 2 * ia1 + 1] = -dy_b
            j_mat[row, 2 * ia2 + 1] = dy_b
            j_mat[row, 2 * ib1] = -dx_a
            j_mat[row, 2 * ib2] = dx_a
            j_mat[row, 2 * ib1 + 1] = -dy_a
            j_mat[row, 2 * ib2 + 1] = dy_a
            return 1

        if c_type == ConstraintType.EQUAL:
            ia1, ia2, ib1, ib2 = indices[0], indices[1], indices[2], indices[3]
            dx_a = x[2 * ia2] - x[2 * ia1]
            dy_a = x[2 * ia2 + 1] - x[2 * ia1 + 1]
            dx_b = x[2 * ib2] - x[2 * ib1]
            dy_b = x[2 * ib2 + 1] - x[2 * ib1 + 1]
            len_a = float(np.hypot(dx_a, dy_a))
            len_b = float(np.hypot(dx_b, dy_b))
            if len_a > 1e-12:
                j_mat[row, 2 * ia1] = -dx_a / len_a
                j_mat[row, 2 * ia1 + 1] = -dy_a / len_a
                j_mat[row, 2 * ia2] = dx_a / len_a
                j_mat[row, 2 * ia2 + 1] = dy_a / len_a
            if len_b > 1e-12:
                j_mat[row, 2 * ib1] = dx_b / len_b
                j_mat[row, 2 * ib1 + 1] = dy_b / len_b
                j_mat[row, 2 * ib2] = -dx_b / len_b
                j_mat[row, 2 * ib2 + 1] = -dy_b / len_b
            return 1

        # Approximation par différences finies centrales pour contraintes non-linéaires complexes
        eps = 1e-7
        num_sub_eqs = 2 if c_type == ConstraintType.G2_CURVATURE else 1
        for col in range(num_vars):
            x_step = x.copy()
            x_step[col] += eps
            f_step = self._evaluate_residuals(x_step)
            for sub_k in range(num_sub_eqs):
                if row + sub_k < num_eqs:
                    j_mat[row + sub_k, col] = (f_step[row + sub_k] - f0[row + sub_k]) / eps

        return num_sub_eqs

    def calculate_degrees_of_freedom(self) -> Tuple[int, str]:
        """
        Calcule les degrés de liberté (DoF) du système d'esquisse (FreeCAD Sketcher Solver Diagnostics).
        Évalue le rang de la matrice Jacobienne analytique des contraintes indépendantes.

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

        # Évaluation directe de la matrice Jacobienne exacte
        j_mat = self._evaluate_jacobian(x0)

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


def project_3d_edge_to_sketch_plane(
    edge_start: Tuple[float, float, float],
    edge_end: Tuple[float, float, float],
    plane_origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    plane_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    plane_u_axis: Tuple[float, float, float] = (1.0, 0.0, 0.0)
) -> Tuple[Point2D, Point2D]:
    """
    Projette une arête 3D du solide dans le système de coordonnées local (u, v) de l'esquisse.
    Permet la contrainte de géométrie externe (FreeCAD External Geometry).
    """
    n = np.array(plane_normal, dtype=np.float64)
    n_norm = float(np.linalg.norm(n))
    if n_norm > 1e-9:
        n = n / n_norm
    else:
        n = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    u = np.array(plane_u_axis, dtype=np.float64)
    u = u - float(np.dot(u, n)) * n
    u_norm = float(np.linalg.norm(u))
    if u_norm > 1e-9:
        u = u / u_norm
    else:
        arbitrary = np.array([0.0, 1.0, 0.0], dtype=np.float64) if abs(n[0]) > 0.9 else np.array([1.0, 0.0, 0.0], dtype=np.float64)
        u = np.cross(n, arbitrary)
        u = u / float(np.linalg.norm(u))

    v = np.cross(n, u)
    o = np.array(plane_origin, dtype=np.float64)

    p0 = np.array(edge_start, dtype=np.float64)
    p1 = np.array(edge_end, dtype=np.float64)

    p0_proj = p0 - float(np.dot(p0 - o, n)) * n
    p1_proj = p1 - float(np.dot(p1 - o, n)) * n

    u0 = float(np.dot(p0_proj - o, u))
    v0 = float(np.dot(p0_proj - o, v))
    u1 = float(np.dot(p1_proj - o, u))
    v1 = float(np.dot(p1_proj - o, v))

    return (Point2D(u0, v0), Point2D(u1, v1))


def fillet_2d(
    p0: Point2D,
    corner: Point2D,
    p1: Point2D,
    radius: float
) -> Tuple[Point2D, Point2D, Point2D, float]:
    """
    Calcule le congé 2D (fillet) entre deux segments sécants au point corner.

    Returns:
        Tuple[tangent_0: Point2D, tangent_1: Point2D, center: Point2D, radius: float]
    """
    v0 = np.array([p0.u - corner.u, p0.v - corner.v], dtype=np.float64)
    v1 = np.array([p1.u - corner.u, p1.v - corner.v], dtype=np.float64)

    len0 = float(np.linalg.norm(v0))
    len1 = float(np.linalg.norm(v1))
    if len0 < 1e-9 or len1 < 1e-9 or radius <= 0.0:
        return (corner, corner, corner, 0.0)

    d0 = v0 / len0
    d1 = v1 / len1

    dot = float(np.dot(d0, d1))
    dot = max(-1.0, min(1.0, dot))
    angle = float(np.arccos(dot))

    if angle < 1e-4 or angle > (np.pi - 1e-4):
        return (corner, corner, corner, 0.0)

    half_angle = angle / 2.0
    tangent_dist = radius / float(np.tan(half_angle))

    tangent_dist = min(tangent_dist, len0 * 0.99, len1 * 0.99)
    eff_radius = tangent_dist * float(np.tan(half_angle))

    t0 = Point2D(corner.u + float(d0[0]) * tangent_dist, corner.v + float(d0[1]) * tangent_dist)
    t1 = Point2D(corner.u + float(d1[0]) * tangent_dist, corner.v + float(d1[1]) * tangent_dist)

    bisector = d0 + d1
    bis_norm = float(np.linalg.norm(bisector))
    if bis_norm < 1e-9:
        return (corner, corner, corner, 0.0)
    bisector = bisector / bis_norm

    center_dist = eff_radius / float(np.sin(half_angle))
    center = Point2D(corner.u + float(bisector[0]) * center_dist, corner.v + float(bisector[1]) * center_dist)

    return (t0, t1, center, eff_radius)


def trim_intersection_2d(
    p0: Point2D,
    p1: Point2D,
    q0: Point2D,
    q1: Point2D
) -> Optional[Point2D]:
    """
    Calcule l'intersection exacte entre deux droites/segments 2D pour les opérations d'ajustement (Trim).
    """
    dx_p = p1.u - p0.u
    dy_p = p1.v - p0.v
    dx_q = q1.u - q0.u
    dy_q = q1.v - q0.v

    denom = dx_p * dy_q - dy_p * dx_q
    if abs(denom) < 1e-9:
        return None

    t = ((q0.u - p0.u) * dy_q - (q0.v - p0.v) * dx_q) / denom
    inter_u = p0.u + t * dx_p
    inter_v = p0.v + t * dy_p

    return Point2D(float(inter_u), float(inter_v))



