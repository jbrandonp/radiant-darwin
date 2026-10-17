"""
Tests unitaires pour le solveur d'intersection surface-surface (SSI)
et la génération d'arêtes B-Rep étanches maîtresses.
"""

import numpy as np
import pytest

from src.core.nexus_kernel.trimmed_brep_watertight import (
    SurfaceSurfaceIntersectionSolver, WatertightTrimmedEdge
)


def test_intersect_planes_orthogonal() -> None:
    """Vérifie l'intersection exacte de deux plans orthogonaux (XY et XZ)."""
    p1 = np.array([0.0, 0.0, 0.0])
    n1 = np.array([0.0, 0.0, 1.0])  # Plan XY

    p2 = np.array([0.0, 0.0, 0.0])
    n2 = np.array([0.0, 1.0, 0.0])  # Plan XZ

    res = SurfaceSurfaceIntersectionSolver.intersect_planes(p1, n1, p2, n2)
    assert res is not None
    p0, direction = res

    # La direction d'intersection doit être colinéaire à l'axe X [1, 0, 0]
    assert pytest.approx(abs(direction[0]), 1e-5) == 1.0
    assert pytest.approx(direction[1], abs=1e-5) == 0.0
    assert pytest.approx(direction[2], abs=1e-5) == 0.0

    # Le point p0 doit appartenir aux deux plans
    assert pytest.approx(float(np.dot(p0 - p1, n1)), abs=1e-6) == 0.0
    assert pytest.approx(float(np.dot(p0 - p2, n2)), abs=1e-6) == 0.0


def test_intersect_planes_parallel() -> None:
    """Vérifie que deux plans parallèles retournent None."""
    p1 = np.array([0.0, 0.0, 0.0])
    n1 = np.array([0.0, 0.0, 1.0])

    p2 = np.array([0.0, 0.0, 10.0])
    n2 = np.array([0.0, 0.0, 1.0])

    res = SurfaceSurfaceIntersectionSolver.intersect_planes(p1, n1, p2, n2)
    assert res is None


def test_intersect_plane_cylinder_orthogonal_circle() -> None:
    """Vérifie la coupe d'un cylindre d'axe Z par un plan Z=15 (cercle exact)."""
    center = np.array([0.0, 0.0, 0.0])
    axis = np.array([0.0, 0.0, 1.0])
    radius = 8.0

    p_plane = np.array([0.0, 0.0, 15.0])
    n_plane = np.array([0.0, 0.0, 1.0])

    circle_func = SurfaceSurfaceIntersectionSolver.intersect_plane_cylinder(
        center, axis, radius, p_plane, n_plane
    )
    assert circle_func is not None

    for t in [0.0, np.pi * 0.5, np.pi, np.pi * 1.5]:
        pt = circle_func(t)
        # Z doit être exactement 15.0
        assert pytest.approx(pt[2], abs=1e-5) == 15.0
        # Distance à l'axe Z (rayon) doit être exactement 8.0
        r_eval = np.sqrt(pt[0]**2 + pt[1]**2)
        assert pytest.approx(r_eval, abs=1e-5) == 8.0


def test_intersect_plane_cylinder_oblique_ellipse() -> None:
    """Vérifie la coupe oblique à 45° d'un cylindre (ellipse 3D exacte)."""
    center = np.array([0.0, 0.0, 0.0])
    axis = np.array([0.0, 0.0, 1.0])
    radius = 5.0

    p_plane = np.array([0.0, 0.0, 0.0])
    # Normale inclinée à 45° dans le plan YZ
    n_plane = np.array([0.0, 1.0, 1.0]) / np.sqrt(2.0)

    ellipse_func = SurfaceSurfaceIntersectionSolver.intersect_plane_cylinder(
        center, axis, radius, p_plane, n_plane
    )
    assert ellipse_func is not None

    for t in np.linspace(0.0, 2.0 * np.pi, 12):
        pt = ellipse_func(float(t))
        # Doit être sur le cylindre x^2 + y^2 = 5^2
        r_eval = np.sqrt(pt[0]**2 + pt[1]**2)
        assert pytest.approx(r_eval, abs=1e-5) == 5.0
        # Doit appartenir au plan (pt . n = 0)
        assert pytest.approx(float(np.dot(pt - p_plane, n_plane)), abs=1e-5) == 0.0


def test_create_trimmed_edges_factory() -> None:
    """Vérifie la construction d'une arête B-Rep étanche maîtresse via les méthodes factory."""
    p1 = np.array([0.0, 0.0, 0.0])
    n1 = np.array([0.0, 0.0, 1.0])
    p2 = np.array([0.0, 0.0, 0.0])
    n2 = np.array([1.0, 0.0, 0.0])

    edge = SurfaceSurfaceIntersectionSolver.create_trimmed_edge_from_plane_plane(
        "edge_xy_yz", p1, n1, p2, n2, t_range=(-10.0, 10.0)
    )
    assert edge is not None
    assert isinstance(edge, WatertightTrimmedEdge)
    samples = edge.sample_master_vertices(num_samples=10)
    assert len(samples) == 10
    for s in samples:
        assert pytest.approx(float(np.dot(s - p1, n1)), abs=1e-5) == 0.0
        assert pytest.approx(float(np.dot(s - p2, n2)), abs=1e-5) == 0.0
