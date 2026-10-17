"""
Package de cinématique unifiée et liaisons mécaniques spatiales.
Fournit :
- La rotation exacte d'Euler-Rodrigues autour de n'importe quel axe et point pivot spatial
- L'accès unifié aux solveurs de liaisons cinématiques et transmissions mécaniques
"""

from __future__ import annotations

from src.assembly.kinematics.rodrigues import (
    compute_rodrigues_rotation_matrix,
    compute_rodrigues_affine_matrix,
    apply_rodrigues_rotation,
)

__all__ = [
    "compute_rodrigues_rotation_matrix",
    "compute_rodrigues_affine_matrix",
    "apply_rodrigues_rotation",
]
