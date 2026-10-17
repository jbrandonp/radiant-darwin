"""
Formulation mathématique exacte de rotation spatiale 3D par formule d'Euler-Rodrigues.
Permet d'appliquer des rotations spatiales rigoureuses autour de n'importe quel axe 3D
et autour d'un point pivot spatial arbitraire (anchor point), sans approximations ni
discrétisations cartésiennes heuristiques.

Typage statique strict : zéro Any et zéro object, complexité cognitive <= 25.
"""

from __future__ import annotations
import math
from typing import Optional, Sequence
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import Solid


def compute_rodrigues_rotation_matrix(axis: Vector3D, angle_deg: float) -> np.ndarray:
    """
    Calcule la matrice de rotation orthonormale 3x3 exacte par la formule d'Euler-Rodrigues.

    Args:
        axis: Vecteur directeur spatial de l'axe de rotation.
        angle_deg: Angle de rotation en degrés.

    Returns:
        Matrice NumPy 3x3 de type float64.
    """
    norm = math.sqrt(axis.x * axis.x + axis.y * axis.y + axis.z * axis.z)
    if norm < 1e-9:
        return np.eye(3, dtype=np.float64)

    ux = axis.x / norm
    uy = axis.y / norm
    uz = axis.z / norm

    theta_rad = math.radians(angle_deg)
    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)
    v = 1.0 - cos_t

    r11 = ux * ux * v + cos_t
    r12 = ux * uy * v - uz * sin_t
    r13 = ux * uz * v + uy * sin_t

    r21 = ux * uy * v + uz * sin_t
    r22 = uy * uy * v + cos_t
    r23 = uy * uz * v - ux * sin_t

    r31 = ux * uz * v - uy * sin_t
    r32 = uy * uz * v + ux * sin_t
    r33 = uz * uz * v + cos_t

    return np.array([
        [r11, r12, r13],
        [r21, r22, r23],
        [r31, r32, r33]
    ], dtype=np.float64)


def compute_rodrigues_affine_matrix(
    axis: Vector3D,
    angle_deg: float,
    anchor_point: Optional[Vector3D] = None
) -> np.ndarray:
    """
    Calcule la matrice de transformation affine 3x4 [R | T] pour une rotation
    autour d'un point pivot spatial (anchor_point).

    Args:
        axis: Axe directeur 3D.
        angle_deg: Angle en degrés.
        anchor_point: Point d'ancrage / pivot dans l'espace. Si None, pivote autour de l'origine (0, 0, 0).

    Returns:
        Matrice NumPy 3x4 de type float64.
    """
    rot_3x3 = compute_rodrigues_rotation_matrix(axis, angle_deg)
    mat_3x4 = np.zeros((3, 4), dtype=np.float64)
    mat_3x4[0:3, 0:3] = rot_3x3

    if anchor_point is not None:
        p0 = np.array([anchor_point.x, anchor_point.y, anchor_point.z], dtype=np.float64)
        t_vec = p0 - rot_3x3 @ p0
        mat_3x4[0:3, 3] = t_vec

    return mat_3x4


def apply_rodrigues_rotation(
    solid: Solid,
    axis: Vector3D,
    angle_deg: float,
    anchor_point: Optional[Vector3D] = None
) -> Solid:
    """
    Applique une rotation axiale 3D exacte à un corps solide selon la formule d'Euler-Rodrigues.
    
    Args:
        solid: Le solide 3D à pivoter.
        axis: L'axe de rotation 3D.
        angle_deg: L'angle relatif en degrés.
        anchor_point: Le point pivot spatial de la liaison.

    Returns:
        Un nouveau solide pivoté avec exactitude.
    """
    mat_3x4 = compute_rodrigues_affine_matrix(axis, angle_deg, anchor_point)
    return solid.transform(mat_3x4)
