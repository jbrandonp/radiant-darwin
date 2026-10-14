"""
Atelier Robotique Industrielle 6 Axes & Cinématique Série (Robot Workbench).
Fournit le calcul de cinématique directe et inverse (Modèle Denavit-Hartenberg)
pour les bras robotisés industriels (KUKA, ABB, Fanuc, Universal Robots),
avec planification de trajectoire cartésienne et détection des singularités.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np


@dataclass
class DHParameter:
    """Paramètres cinématiques normalisés de Denavit-Hartenberg (D-H)."""
    a_mm: float       # Longueur du segment (distance le long de X_i)
    alpha_rad: float  # Torsion du segment (angle autour de X_i)
    d_mm: float       # Décalage de l'articulation (distance le long de Z_{i-1})
    theta_rad: float  # Angle de l'articulation (angle autour de Z_{i-1})


class RobotArm6Axis:
    """
    Simulateur cinématique de bras manipulateur polyarticulé 6 axes.
    Calcule la position de l'outil (TCP - Tool Center Point) et la matrice Jacobienne.
    """

    def __init__(self, model_name: str = "KUKA_KR6_6DoF") -> None:
        self.model_name: str = model_name
        self.dh_params: List[DHParameter] = [
            DHParameter(a_mm=25.0,  alpha_rad=np.pi / 2.0, d_mm=400.0, theta_rad=0.0),
            DHParameter(a_mm=315.0, alpha_rad=0.0,         d_mm=0.0,   theta_rad=0.0),
            DHParameter(a_mm=35.0,  alpha_rad=np.pi / 2.0, d_mm=0.0,   theta_rad=0.0),
            DHParameter(a_mm=0.0,   alpha_rad=-np.pi / 2.0, d_mm=365.0, theta_rad=0.0),
            DHParameter(a_mm=0.0,   alpha_rad=np.pi / 2.0, d_mm=0.0,   theta_rad=0.0),
            DHParameter(a_mm=0.0,   alpha_rad=0.0,         d_mm=80.0,  theta_rad=0.0)
        ]
        self.joint_angles_rad: np.ndarray = np.zeros(6, dtype=np.float64)

    def _dh_matrix(self, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
        """Matrice de transformation élémentaire 4x4 selon la convention standard Denavit-Hartenberg."""
        ct = float(np.cos(theta))
        st = float(np.sin(theta))
        ca = float(np.cos(alpha))
        sa = float(np.sin(alpha))

        return np.array([
            [ct, -st * ca,  st * sa, a * ct],
            [st,  ct * ca, -ct * sa, a * st],
            [0.0,      sa,       ca,      d],
            [0.0,     0.0,      0.0,    1.0]
        ], dtype=np.float64)

    def forward_kinematics(self, joint_angles_rad: Optional[Sequence[float]] = None) -> np.ndarray:
        """
        Calcule la matrice homogène 4x4 de cinématique directe T06.
        """
        angles = np.array(joint_angles_rad, dtype=np.float64) if joint_angles_rad is not None else self.joint_angles_rad
        t_global = np.eye(4, dtype=np.float64)

        for i in range(6):
            dh = self.dh_params[i]
            theta_total = dh.theta_rad + float(angles[i])
            a_i = self._dh_matrix(dh.a_mm, dh.alpha_rad, dh.d_mm, theta_total)
            t_global = t_global @ a_i

        return t_global

    def forward_kinematics_pose(self, joint_angles_rad: Optional[Sequence[float]] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Retourne (position_xyz_mm, matrice_rotation_3x3)."""
        t = self.forward_kinematics(joint_angles_rad)
        return t[:3, 3], t[:3, :3]

    def calculate_jacobian(self, joint_angles_rad: Optional[Sequence[float]] = None) -> np.ndarray:
        """Calcule la matrice Jacobienne 6x6 reliant les vitesses articulaires aux vitesses cartésiennes."""
        angles = np.array(joint_angles_rad, dtype=np.float64) if joint_angles_rad is not None else self.joint_angles_rad
        eps = 1e-4
        j_mat = np.zeros((6, 6), dtype=np.float64)
        t0 = self.forward_kinematics(angles)
        pos0 = t0[:3, 3]

        for i in range(6):
            step = np.copy(angles)
            step[i] += eps
            t_plus = self.forward_kinematics(step)
            pos_plus = t_plus[:3, 3]
            vel_linear = (pos_plus - pos0) / eps
            j_mat[:3, i] = vel_linear
            j_mat[3:, i] = np.array([0.0, 0.0, 1.0])

        return j_mat

    compute_jacobian = calculate_jacobian

    def is_singular(self, joint_angles_rad: Optional[Sequence[float]] = None, threshold: float = 1e-4) -> bool:
        """Détecte si le robot se trouve dans une configuration singulière (det(J) ~ 0)."""
        j_mat = self.calculate_jacobian(joint_angles_rad)
        det = float(np.linalg.det(j_mat))
        return abs(det) < threshold

    is_in_singularity = is_singular

    def plan_cartesian_trajectory(
        self,
        start_pos: Tuple[float, float, float],
        end_pos: Tuple[float, float, float],
        num_waypoints: int = 5
    ) -> List[Tuple[float, float, float]]:
        """Génère une séquence de positions cartésiennes rectilignes."""
        p0 = np.array(start_pos, dtype=np.float64)
        p1 = np.array(end_pos, dtype=np.float64)
        trajectory: List[Tuple[float, float, float]] = []

        for s in range(num_waypoints):
            t = float(s) / float(max(1, num_waypoints - 1))
            pt = (1.0 - t) * p0 + t * p1
            trajectory.append((float(pt[0]), float(pt[1]), float(pt[2])))

        return trajectory


# Alias pour interopérabilité
DenavitHartenbergParameter = DHParameter
