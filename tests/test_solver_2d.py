"""
Tests unitaires pour le solveur de contraintes géométriques 2D.
"""

import pytest
import numpy as np

from src.core.types import Point2D
from src.solver.constraints_2d import SketchConstraintSolver2D


def test_solve_horizontal_and_vertical() -> None:
    """Vérifie la résolution simultanée de contraintes horizontale et verticale."""
    solver = SketchConstraintSolver2D()
    # 3 points formant un triangle rectangle
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 1.0))
    p2 = solver.add_point(Point2D(10.0, 15.0))

    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_horizontal(p0, p1)
    solver.add_vertical(p1, p2)
    solver.add_distance(p0, p1, 20.0)
    solver.add_distance(p1, p2, 10.0)

    success, pts = solver.solve()
    assert success
    assert pytest.approx(pts[0].u, abs=1e-3) == 0.0
    assert pytest.approx(pts[0].v, abs=1e-3) == 0.0

    # p1 doit être à v = 0 et u = 20
    assert pytest.approx(pts[1].u, abs=1e-3) == 20.0
    assert pytest.approx(pts[1].v, abs=1e-3) == 0.0

    # p2 doit être à u = 20 et v = 10
    assert pytest.approx(pts[2].u, abs=1e-3) == 20.0
    assert pytest.approx(pts[2].v, abs=1e-3) == 10.0


def test_solve_coincident() -> None:
    """Vérifie la contrainte de coïncidence de deux points."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(5.0, 5.0))
    p1 = solver.add_point(Point2D(12.0, 8.0))

    solver.add_fixed(p0, 5.0, 5.0)
    solver.add_coincident(p0, p1)

    success, pts = solver.solve()
    assert success
    assert pytest.approx(pts[1].u, 1e-4) == pts[0].u
    assert pytest.approx(pts[1].v, 1e-4) == pts[0].v


def test_solve_parallel() -> None:
    """Vérifie la contrainte de parallélisme entre deux segments 2D."""
    solver = SketchConstraintSolver2D()
    # Segment 1 : horizontal sur l'axe U
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_fixed(p1, 10.0, 0.0)

    # Segment 2 : p2 fixé à (0, 5), p3 initialement incliné à (10, 8)
    p2 = solver.add_point(Point2D(0.0, 5.0))
    p3 = solver.add_point(Point2D(10.0, 8.0))
    solver.add_fixed(p2, 0.0, 5.0)
    solver.add_distance(p2, p3, 10.0)
    solver.add_parallel(p0, p1, p2, p3)

    success, pts = solver.solve()
    assert success
    # Segment 2 doit être horizontal (v(p3) == v(p2) == 5.0, u(p3) == 10.0)
    assert pytest.approx(pts[3].v, abs=1e-3) == 5.0
    assert pytest.approx(pts[3].u, abs=1e-3) == 10.0


def test_solve_perpendicular() -> None:
    """Vérifie la contrainte de perpendicularité entre deux segments 2D."""
    solver = SketchConstraintSolver2D()
    # Segment 1 : horizontal
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_fixed(p1, 10.0, 0.0)

    # Segment 2 : p2 fixé à (5, 5), p3 fixé à v=15 mais libre en u
    p2 = solver.add_point(Point2D(5.0, 5.0))
    p3 = solver.add_point(Point2D(8.0, 15.0))
    solver.add_fixed(p2, 5.0, 5.0)
    solver.add_distance(p2, p3, 10.0)
    solver.add_perpendicular(p0, p1, p2, p3)

    success, pts = solver.solve()
    assert success
    # Segment 2 perpendiculaire à l'horizontale => vertical => u(p3) == 5.0
    assert pytest.approx(pts[3].u, abs=1e-3) == 5.0
    assert pytest.approx(pts[3].v, abs=1e-3) == 15.0
