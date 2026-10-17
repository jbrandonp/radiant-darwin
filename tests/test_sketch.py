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


def test_sketch_arbitrary_tilted_plane() -> None:
    """Vérifie le positionnement d'une esquisse sur un plan arbitraire 3D (ex: face inclinée)."""
    import numpy as np

    orig = Vector3D(10.0, 20.0, 30.0)
    norm = Vector3D(0.0, 1.0, 1.0).normalized()
    u_ax = Vector3D(1.0, 0.0, 0.0)

    sketch = Sketch2D(
        sketch_id="s_tilt",
        name="TiltedFace",
        plane=PlaneType.CUSTOM,
        origin=orig,
        normal=norm,
        u_axis=u_ax
    )

    pt2d = Point2D(5.0, 10.0)
    pt3d = sketch.to_3d_coordinates(pt2d)

    # Vérifier l'aller-retour 2D -> 3D -> 2D
    pt2d_back = sketch.to_2d_coordinates(pt3d)
    assert pt2d_back.u == pytest.approx(5.0, abs=1e-4)
    assert pt2d_back.v == pytest.approx(10.0, abs=1e-4)


def test_sketch_line_chaining_and_hole_extrusion() -> None:
    """Vérifie l'assemblage automatique de 4 SketchLine en contour fermé et l'extrusion avec trou."""
    from src.core.geometry import extrude_polygon

    sketch = Sketch2D("s_chain", "ChainedLines", PlaneType.XY)
    # Ajouter 4 segments de ligne individuels
    sketch.add_line(Point2D(0.0, 0.0), Point2D(40.0, 0.0))
    sketch.add_line(Point2D(40.0, 0.0), Point2D(40.0, 40.0))
    sketch.add_line(Point2D(40.0, 40.0), Point2D(0.0, 40.0))
    sketch.add_line(Point2D(0.0, 40.0), Point2D(0.0, 0.0))

    # Ajouter un perçage carré intérieur
    sketch.add_rectangle(Point2D(10.0, 10.0), 20.0, 20.0)

    # L'algorithme doit chaîner les 4 lignes en un contour et identifier le perçage
    outer, holes = sketch.get_profile_with_holes()
    assert outer is not None
    assert len(outer) == 4
    assert len(holes) == 1
    assert len(holes[0]) == 4

    # Extruder la pièce ajourée
    solid = extrude_polygon(outer, height=10.0, holes=holes)
    assert solid.is_watertight() is True
    # Volume attendu : (40*40 - 20*20) * 10 = (1600 - 400) * 10 = 12000 mm³
    assert solid.volume() == pytest.approx(12000.0, rel=1e-3)

