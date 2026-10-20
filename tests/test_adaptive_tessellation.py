"""
Tests unitaires pour le moteur de tessellation adaptative (BRepMesh_IncrementalMesh).
Vérifie le raffinement quadtree par flèche cordale et déviation angulaire,
la compacité sur surfaces planes et la densification sur surfaces à forte courbure.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.adaptive_tessellation import AdaptiveTessellator, QuadNode
from src.core.nexus_kernel.nurbs_surface import NexusNURBSSurface, make_coons_patch


def test_planar_surface_adaptive_tessellation_is_sparse() -> None:
    """Vérifie qu'une surface parfaitement plane n'entraîne aucune subdivision inutile."""
    # Plan plat Z = 0
    def eval_flat(u: float, v: float) -> np.ndarray:
        return np.array([u * 100.0, v * 100.0, 0.0], dtype=np.float64)

    def normal_flat(u: float, v: float) -> np.ndarray:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)

    verts, tris = AdaptiveTessellator.tessellate(
        eval_fn=eval_flat,
        normal_fn=normal_flat,
        linear_deflection=0.1,
        angular_deflection_deg=10.0,
        max_depth=4,
        initial_subdivisions=2
    )
    # 2x2 quads = 4 quads * 2 triangles = 8 triangles
    assert len(tris) == 8
    assert len(verts) == 9


def test_curved_dome_adaptive_tessellation_densifies() -> None:
    """Vérifie qu'un dôme hémisphérique déclenche des subdivisions adaptatives profondes."""
    radius = 50.0

    def eval_dome(u: float, v: float) -> np.ndarray:
        # u in [0, pi/2], v in [0, pi/2]
        theta = u * (math.pi / 2.0)
        phi = v * (math.pi / 2.0)
        x = radius * math.sin(theta) * math.cos(phi)
        y = radius * math.sin(theta) * math.sin(phi)
        z = radius * math.cos(theta)
        return np.array([x, y, z], dtype=np.float64)

    def normal_dome(u: float, v: float) -> np.ndarray:
        pt = eval_dome(u, v)
        norm = np.linalg.norm(pt)
        return pt / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])

    # 1. Tessellation grossière (tolérance large : 5 mm)
    verts_coarse, tris_coarse = AdaptiveTessellator.tessellate(
        eval_fn=eval_dome,
        normal_fn=normal_dome,
        linear_deflection=5.0,
        angular_deflection_deg=30.0,
        max_depth=4,
        initial_subdivisions=2
    )

    # 2. Tessellation fine (tolérance stricte : 0.2 mm)
    verts_fine, tris_fine = AdaptiveTessellator.tessellate(
        eval_fn=eval_dome,
        normal_fn=normal_dome,
        linear_deflection=0.2,
        angular_deflection_deg=10.0,
        max_depth=4,
        initial_subdivisions=2
    )

    # La tessellation fine doit produire nettement plus de facettes pour suivre la courbure
    assert len(tris_fine) > len(tris_coarse)
    assert len(verts_fine) > len(verts_coarse)

    # Vérification intégrité des indices de triangles
    assert np.all(tris_fine >= 0)
    assert np.all(tris_fine < len(verts_fine))


def test_nurbs_surface_adaptive_tessellate_method() -> None:
    """Vérifie la méthode intégrée NexusNURBSSurface.adaptive_tessellate()."""
    # Surface NURBS avec un point de contrôle central surélevé (cloche)
    ctrl_pts = [
        [[0.0, 0.0, 0.0], [50.0, 0.0, 0.0], [100.0, 0.0, 0.0]],
        [[0.0, 50.0, 0.0], [50.0, 50.0, 40.0], [100.0, 50.0, 0.0]],  # Sommet central surélevé à Z=40
        [[0.0, 100.0, 0.0], [50.0, 100.0, 0.0], [100.0, 100.0, 0.0]]
    ]
    surf = NexusNURBSSurface(
        surface_id="bell_nurbs",
        degree_u=2,
        degree_v=2,
        knots_u=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        knots_v=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        control_points=ctrl_pts
    )

    verts, tris = surf.adaptive_tessellate(linear_deflection=0.5, angular_deflection_deg=15.0, max_depth=4)
    assert len(tris) >= 8
    assert len(verts) >= 9

    # Vérifie que la flèche centrale Z atteint bien 10.0 mm (0.25 * 40.0 pour une B-Spline degré 2)
    z_max = float(np.max(verts[:, 2]))
    assert pytest.approx(z_max, 1e-2) == 10.0
