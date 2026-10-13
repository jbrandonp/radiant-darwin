"""
Tests unitaires pour le moteur géométrique volumique (Solid, CSG, Primitives, Extrusion).
"""

import pytest
import numpy as np

from src.core.geometry import (
    make_box, make_cylinder, make_sphere, make_cone,
    extrude_polygon, Solid
)
from src.core.types import Vector3D, Point2D, PlaneType


def test_vector3d_math() -> None:
    """Vérifie toutes les opérations de base de Vector3D."""
    v1 = Vector3D(1.0, 2.0, 3.0)
    v2 = Vector3D(4.0, 5.0, 6.0)

    assert v1.add(v2) == Vector3D(5.0, 7.0, 9.0)
    assert v2.subtract(v1) == Vector3D(3.0, 3.0, 3.0)
    assert v1.scale(2.0) == Vector3D(2.0, 4.0, 6.0)
    assert pytest.approx(v1.length(), 0.01) == 3.7416
    assert pytest.approx(v1.normalized().length(), 0.01) == 1.0
    assert pytest.approx(v1.dot(v2), 0.01) == 32.0
    cross = v1.cross(v2)
    assert cross == Vector3D(-3.0, 6.0, -3.0)
    arr = v1.to_array()
    assert len(arr) == 3


def test_make_box_volume_and_bounds() -> None:
    """Vérifie le volume et les dimensions d'une boîte paramétrique."""
    box = make_box(10.0, 20.0, 30.0, center=False)
    assert not box.is_empty()
    assert pytest.approx(box.volume(), 0.1) == 6000.0

    min_pt, max_pt = box.bounding_box()
    assert pytest.approx(min_pt.x, 0.01) == 0.0
    assert pytest.approx(min_pt.y, 0.01) == 0.0
    assert pytest.approx(min_pt.z, 0.01) == 0.0
    assert pytest.approx(max_pt.x, 0.01) == 10.0
    assert pytest.approx(max_pt.y, 0.01) == 20.0
    assert pytest.approx(max_pt.z, 0.01) == 30.0


def test_make_cylinder_volume() -> None:
    """Vérifie le volume d'un cylindre : Pi * r^2 * h."""
    radius = 5.0
    height = 20.0
    cylinder = make_cylinder(radius, height, segments=64)
    expected_vol = np.pi * (radius ** 2) * height
    assert pytest.approx(cylinder.volume(), rel=0.05) == expected_vol


def test_make_sphere_volume() -> None:
    """Vérifie le volume d'une sphère : 4/3 * Pi * r^3."""
    radius = 10.0
    sphere = make_sphere(radius, segments=64)
    expected_vol = (4.0 / 3.0) * np.pi * (radius ** 3)
    assert pytest.approx(sphere.volume(), rel=0.05) == expected_vol


def test_boolean_operations() -> None:
    """Vérifie les opérations booléennes d'union, soustraction et intersection."""
    b1 = make_box(10.0, 10.0, 10.0, center=False)  # Vol = 1000
    b2 = make_box(10.0, 10.0, 10.0, center=False).translate(Vector3D(5.0, 0.0, 0.0))  # Chevauchement de 5x10x10 = 500

    # Union
    union_solid = b1.union(b2)
    assert pytest.approx(union_solid.volume(), 0.1) == 1500.0

    # Différence
    diff_solid = b1.difference(b2)
    assert pytest.approx(diff_solid.volume(), 0.1) == 500.0

    # Intersection
    inter_solid = b1.intersection(b2)
    assert pytest.approx(inter_solid.volume(), 0.1) == 500.0


def test_extrude_polygon() -> None:
    """Vérifie l'extrusion d'un polygone 2D fermé."""
    pts = [
        Point2D(0.0, 0.0),
        Point2D(10.0, 0.0),
        Point2D(10.0, 10.0),
        Point2D(0.0, 10.0)
    ]
    solid = extrude_polygon(pts, height=15.0, plane=PlaneType.XY)
    assert pytest.approx(solid.volume(), 0.1) == 1500.0


def test_mesh_buffer_generation() -> None:
    """Vérifie la génération de sommets, faces, normales et arêtes vives pour OpenGL."""
    box = make_box(10.0, 10.0, 10.0)
    buffer = box.to_mesh_buffer()

    assert not buffer.is_empty()
    assert len(buffer.vertices) > 0
    assert len(buffer.faces) == 12  # 6 faces rectangulaires = 12 triangles
    assert len(buffer.normals) == len(buffer.vertices)
    assert len(buffer.edges) >= 12  # Arêtes du cube


def test_sharp_edges_coplanar_filtering() -> None:
    """Vérifie que les arêtes de triangulation internes coplanaires d'une face perforée ne sont pas tracées."""
    box = make_box(60.0, 80.0, 20.0, center=True)
    cyl = make_cylinder(8.0, 30.0, segments=36, center=True)
    drilled_plate = box.difference(cyl)
    buf = drilled_plate.to_mesh_buffer()

    mesh = drilled_plate._manifold.to_mesh()
    positions = np.array(mesh.vert_properties)[:, :3]

    # Sommets sur la face supérieure (Z = 10.0)
    top_verts = np.where(np.abs(positions[:, 2] - 10.0) < 1e-3)[0]
    top_sharp_edges = [e for e in buf.edges if e[0] in top_verts and e[1] in top_verts]

    # Doit contenir exactement 40 arêtes (4 côtés du rectangle + 36 facettes du cercle percé)
    # et ZERO arête parasite traversant la face plane entre le cercle et les coins du rectangle
    assert len(top_sharp_edges) == 40
