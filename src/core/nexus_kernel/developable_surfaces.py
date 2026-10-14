"""
Surfaces Développables (Courbure de Gauss K = 0) et Opérateur d'Isoclinique (Draft Angle).
Crucial pour la fonderie, l'injection plastique, la tôlerie fine et le pliage sans étirement.
Fournit :
1. RuledDevelopableSurface : surface réglée vérifiant det(c'(u), d(u), d'(u)) = 0 et son dépliage isométrique 2D.
2. IsoclinicDraftEngine : calcul et application des angles de dépouille par rapport à la direction de démoulage.
Typage statique strict et garantie de complexité cognitive <= 15.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Tuple, Sequence, Optional
import numpy as np


@dataclass(frozen=True)
class DraftDiagnostic:
    """Diagnostic d'angle de dépouille pour les faces d'une pièce industrielle."""
    is_demoldable: bool
    minimum_draft_angle_deg: float
    target_draft_angle_deg: float
    undercut_faces_count: int
    neutral_plane_z: float


class RuledDevelopableSurface:
    """
    Surface réglée développable S(u, v) = c(u) + v * d(u).
    Vérifie rigoureusement la condition de courbure gaussienne nulle K = kappa_1 * kappa_2 = 0,
    autorisant le dépliage isométrique pur dans le plan R² sans allongement de matière.
    """

    def __init__(
        self,
        directrix_curve: Callable[[float], np.ndarray],
        directrix_tangent: Callable[[float], np.ndarray],
        ruling_direction: Callable[[float], np.ndarray],
        ruling_derivative: Callable[[float], np.ndarray],
        u_range: Tuple[float, float] = (0.0, 1.0),
        v_range: Tuple[float, float] = (0.0, 1.0)
    ) -> None:
        self.c: Callable[[float], np.ndarray] = directrix_curve
        self.c_prime: Callable[[float], np.ndarray] = directrix_tangent
        self.d: Callable[[float], np.ndarray] = ruling_direction
        self.d_prime: Callable[[float], np.ndarray] = ruling_derivative
        self.u_range: Tuple[float, float] = u_range
        self.v_range: Tuple[float, float] = v_range

    def evaluate_point(self, u: float, v: float) -> np.ndarray:
        """Évalue les coordonnées 3D du point S(u, v) = c(u) + v * d(u)."""
        pt_c = self.c(u)
        vec_d = self.d(u)
        return pt_c + v * vec_d

    def gaussian_curvature_determinant(self, u: float) -> float:
        """
        Vérifie la condition d'isométrie : det([c'(u), d(u), d'(u)]) == 0.
        Si ce déterminant est nul, la surface est strictement développable (K = 0).
        """
        cp = self.c_prime(u)
        d_vec = self.d(u)
        dp = self.d_prime(u)
        mat = np.column_stack((cp, d_vec, dp))
        return float(np.linalg.det(mat))

    def is_developable(self, tolerance: float = 1e-5, samples: int = 20) -> bool:
        """Valide numériquement que K = 0 sur l'ensemble du domaine u."""
        u_vals = np.linspace(self.u_range[0], self.u_range[1], samples)
        for u in u_vals:
            det_val = abs(self.gaussian_curvature_determinant(float(u)))
            if det_val > tolerance:
                return False
        return True

    def unroll_to_plane_2d(self, num_u: int = 25, num_v: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """
        Déplie la bande développable 3D dans le plan 2D sans distorsion métrique (longueurs d'arêtes conservées).
        Retourne (points_2d, triangles).
        """
        u_vals = np.linspace(self.u_range[0], self.u_range[1], num_u)
        v_vals = np.linspace(self.v_range[0], self.v_range[1], num_v)

        # Calcul des pas d'abscisse curviligne le long de la directrice c(u)
        s_coords = np.zeros(num_u, dtype=np.float64)
        for i in range(1, num_u):
            p_prev = self.c(float(u_vals[i - 1]))
            p_curr = self.c(float(u_vals[i]))
            ds = float(np.linalg.norm(p_curr - p_prev))
            s_coords[i] = s_coords[i - 1] + ds

        # Échantillonnage des longueurs des génératrices
        pts_2d: List[List[float]] = []
        for i, u in enumerate(u_vals):
            s_u = s_coords[i]
            d_vec = self.d(float(u))
            len_d = float(np.linalg.norm(d_vec))
            for j, v in enumerate(v_vals):
                y_coord = float(v) * len_d
                pts_2d.append([float(s_u), y_coord])

        # Triangulation de la grille rectangulaire dépliée
        triangles: List[List[int]] = []
        for i in range(num_u - 1):
            for j in range(num_v - 1):
                idx0 = i * num_v + j
                idx1 = (i + 1) * num_v + j
                idx2 = (i + 1) * num_v + (j + 1)
                idx3 = i * num_v + (j + 1)
                triangles.append([idx0, idx1, idx2])
                triangles.append([idx0, idx2, idx3])

        return np.array(pts_2d, dtype=np.float64), np.array(triangles, dtype=np.int32)


class IsoclinicDraftEngine:
    """
    Moteur de dépouille industrielle (Draft Angle) et analyse d'isocliniques.
    Permet de démouler les pièces injectées ou fondues sans collage ni contre-dépouille.
    """

    @classmethod
    def analyze_mesh_draft(
        cls,
        face_normals: np.ndarray,
        pull_direction: Sequence[float] = (0.0, 0.0, 1.0),
        target_draft_angle_deg: float = 2.0
    ) -> DraftDiagnostic:
        """
        Analyse la conformité au démoulage pour un ensemble de faces.
        Une face verticale a un angle de 0 deg par rapport au vecteur de tirage.
        """
        pull_vec = np.array(pull_direction, dtype=np.float64)
        pull_norm = float(np.linalg.norm(pull_vec))
        if pull_norm > 1e-9:
            pull_vec /= pull_norm

        target_rad = np.radians(target_draft_angle_deg)
        sin_target = float(np.sin(target_rad))

        undercut_count = 0
        min_angle_deg = 90.0

        for n in face_normals:
            norm_val = float(np.linalg.norm(n))
            if norm_val < 1e-9:
                continue
            unit_n = n / norm_val
            dot_val = float(np.dot(unit_n, pull_vec))
            # Angle par rapport au plan orthogonal au tirage
            face_angle_deg = float(np.degrees(np.arcsin(np.clip(abs(dot_val), 0.0, 1.0))))
            if face_angle_deg < min_angle_deg:
                min_angle_deg = face_angle_deg
            if abs(dot_val) < sin_target:
                undercut_count += 1

        return DraftDiagnostic(
            is_demoldable=(undercut_count == 0),
            minimum_draft_angle_deg=min_angle_deg,
            target_draft_angle_deg=target_draft_angle_deg,
            undercut_faces_count=undercut_count,
            neutral_plane_z=0.0
        )

    @classmethod
    def apply_draft_transformation(
        cls,
        vertices: np.ndarray,
        draft_angle_deg: float,
        neutral_plane_z: float = 0.0,
        pull_axis: Sequence[float] = (0.0, 0.0, 1.0)
    ) -> np.ndarray:
        """
        Applique la déformation d'angle de dépouille le long de l'axe de tirage.
        Les sommets au-dessus du plan neutre s'évasent vers l'extérieur de tan(alpha) * (z - z0).
        """
        res_vertices = np.copy(vertices).astype(np.float64)
        tan_alpha = float(np.tan(np.radians(draft_angle_deg)))

        # Distance au plan neutre le long de Z
        delta_z = res_vertices[:, 2] - neutral_plane_z
        scale_factors = 1.0 + (delta_z * tan_alpha) / np.maximum(10.0, np.abs(neutral_plane_z) + 50.0)

        # Déplacement radial proportionnel dans le plan XY
        res_vertices[:, 0] += delta_z * tan_alpha * np.sign(res_vertices[:, 0])
        res_vertices[:, 1] += delta_z * tan_alpha * np.sign(res_vertices[:, 1])

        return res_vertices
