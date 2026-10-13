"""
Tests unitaires pour le moteur d'esquisse 2D (Sketcher).
"""

import pytest
from src.core.sketch import Sketch2D, SketchRectangle, SketchCircle
from src.core.types import Point2D, PlaneType, Vector3D


def test_sketch_rectangle() -> None:
    """Vérifie la création d'un rectangle 2D dans une esquisse."""
    sketch = Sketch2D("s1", "Sketch 1", PlaneType.XY)
    rect = sketch.add_rectangle(Point2D(0.0, 0.0), 20.0, 10.0)

    points = rect.get_points()
    assert len(points) == 4
    assert points[0] == Point2D(0.0, 0.0)
    assert points[1] == Point2D(20.0, 0.0)
    assert points[2] == Point2D(20.0, 10.0)
    assert points[3] == Point2D(0.0, 10.0)

    profile = sketch.get_primary_profile()
    assert profile is not None
    assert len(profile) == 4


def test_sketch_circle() -> None:
    """Vérifie la discrétisation polygonale d'un cercle 2D."""
    sketch = Sketch2D("s2", "Sketch 2", PlaneType.XY)
    circle = sketch.add_circle(Point2D(5.0, 5.0), radius=10.0, segments=24)

    pts = circle.get_points()
    assert len(pts) == 24
    for pt in pts:
        dist = pt.distance_to(Point2D(5.0, 5.0))
        assert pytest.approx(dist, 0.01) == 10.0


def test_sketch_projection_planes() -> None:
    """Vérifie la projection des coordonnées 2D vers les plans 3D (XY, XZ, YZ)."""
    pt = Point2D(10.0, 20.0)

    s_xy = Sketch2D("s_xy", "XY", PlaneType.XY)
    assert s_xy.to_3d_coordinates(pt) == Vector3D(10.0, 20.0, 0.0)

    s_xz = Sketch2D("s_xz", "XZ", PlaneType.XZ)
    assert s_xz.to_3d_coordinates(pt) == Vector3D(10.0, 0.0, 20.0)

    s_yz = Sketch2D("s_yz", "YZ", PlaneType.YZ)
    assert s_yz.to_3d_coordinates(pt) == Vector3D(0.0, 10.0, 20.0)
