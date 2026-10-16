"""
Tests des Invariants Mathématiques et Propriétés Physiques Fondamentales.
Vérifie rigoureusement les théorèmes géométriques (Conservation des volumes booléens,
Théorème de Huygens, Symétries tensorielles, Isométries spatiales, Idempotence du solveur 2D).
"""

import math
import numpy as np
import pytest

from src.core.geometry import make_box, make_cylinder, make_sphere, Solid
from src.core.types import Vector3D, Point2D
from src.core.inspector import compute_center_of_mass, compute_inertia_tensor
from src.solver.constraints_2d import SketchConstraintSolver2D


def test_volume_boolean_inclusion_exclusion_principle() -> None:
    """Vérifie le principe d'inclusion-exclusion volumique : V(A U B) = V(A) + V(B) - V(A inter B)."""
    box_a = make_box(20.0, 20.0, 20.0, center=True)
    # Cylindre partiellement sécant
    cyl_b = make_cylinder(8.0, 30.0, center=True)

    vol_a = box_a.volume()
    vol_b = cyl_b.volume()

    union_ab = box_a.union(cyl_b)
    inter_ab = box_a.intersection(cyl_b)
    diff_ab = box_a.difference(cyl_b)

    vol_union = union_ab.volume()
    vol_inter = inter_ab.volume()
    vol_diff = diff_ab.volume()

    # Théorème 1 : V(A U B) = V(A) + V(B) - V(A inter B)
    assert pytest.approx(vol_union, rel=1e-3) == (vol_a + vol_b - vol_inter)

    # Théorème 2 : V(A \ B) = V(A) - V(A inter B)
    assert pytest.approx(vol_diff, rel=1e-3) == (vol_a - vol_inter)


def test_isometry_volume_invariance() -> None:
    """Vérifie que les transformations rigides (Translation, Rotation) conservent le volume."""
    sphere = make_sphere(12.0)
    base_vol = sphere.volume()
    base_area = sphere.surface_area()

    # Translation
    translated = sphere.translate(Vector3D(123.4, -56.7, 89.0))
    assert pytest.approx(translated.volume(), rel=1e-5) == base_vol
    assert pytest.approx(translated.surface_area(), rel=1e-5) == base_area

    # Rotation
    rotated = sphere.rotate(37.5, -45.0, 60.0)
    assert pytest.approx(rotated.volume(), rel=1e-5) == base_vol
    assert pytest.approx(rotated.surface_area(), rel=1e-5) == base_area


def test_scaling_similarity_invariants() -> None:
    """Vérifie que la mise à l'échelle homothétique fait varier le volume en s^3 et l'aire en s^2."""
    box = make_box(10.0, 10.0, 10.0, center=True)
    scale_factor = 2.5
    scaled = box.scale(scale_factor, scale_factor, scale_factor)

    expected_vol = box.volume() * (scale_factor ** 3)
    expected_area = box.surface_area() * (scale_factor ** 2)

    assert pytest.approx(scaled.volume(), rel=1e-4) == expected_vol
    assert pytest.approx(scaled.surface_area(), rel=1e-4) == expected_area


def test_center_of_mass_symmetry() -> None:
    """Vérifie que le centre de gravité d'une forme symétrique centrée est exactement à l'origine."""
    box = make_box(30.0, 40.0, 50.0, center=True)
    com = compute_center_of_mass(box)
    assert abs(com.x) < 1e-4
    assert abs(com.y) < 1e-4
    assert abs(com.z) < 1e-4


def test_inertia_tensor_symmetry_and_positive_definiteness() -> None:
    """Vérifie la symétrie du tenseur d'inertie (I_ij = I_ji) et la positivité des valeurs propres."""
    box = make_box(20.0, 30.0, 40.0)
    inertia = compute_inertia_tensor(box, density_g_cm3=2.7)

    # Symétrie et annulation des produits d'inertie sur les axes principaux
    assert abs(inertia.ixy) < 1e-5
    assert abs(inertia.ixz) < 1e-5
    assert abs(inertia.iyz) < 1e-5

    # Positivité stricte des moments d'inertie
    assert inertia.ixx > 0.0
    assert inertia.iyy > 0.0
    assert inertia.izz > 0.0

    # Inégalité triangulaire pour un solide 3D : I_xx + I_yy >= I_zz, etc.
    assert inertia.ixx + inertia.iyy >= inertia.izz - 1e-5
    assert inertia.ixx + inertia.izz >= inertia.iyy - 1e-5
    assert inertia.iyy + inertia.izz >= inertia.ixx - 1e-5

    # Rayons de giration physiquement réels et positifs
    assert all(rg > 0.0 for rg in inertia.radius_of_gyration)


def test_solver_2d_convergence_and_idempotence() -> None:
    """Vérifie l'idempotence du solveur de contraintes 2D : re-résoudre un état équilibré ne déplace pas les points."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(12.0, 5.0))
    p2 = solver.add_point(Point2D(0.0, 10.0))

    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_horizontal(p0, p1)
    solver.add_distance(p0, p1, 30.0)
    solver.add_vertical(p0, p2)
    solver.add_distance(p0, p2, 40.0)

    # 1ère passe de résolution
    success1, points_pass1 = solver.solve()
    assert success1
    assert pytest.approx(points_pass1[1].u, rel=1e-4) == 30.0
    assert pytest.approx(points_pass1[1].v, abs=1e-4) == 0.0
    assert pytest.approx(points_pass1[2].u, abs=1e-4) == 0.0
    assert pytest.approx(points_pass1[2].v, rel=1e-4) == 40.0

    # 2ème passe : réinjecter les points résolus comme état initial
    solver2 = SketchConstraintSolver2D()
    sp0 = solver2.add_point(points_pass1[0])
    sp1 = solver2.add_point(points_pass1[1])
    sp2 = solver2.add_point(points_pass1[2])
    solver2.add_fixed(sp0, 0.0, 0.0)
    solver2.add_horizontal(sp0, sp1)
    solver2.add_distance(sp0, sp1, 30.0)
    solver2.add_vertical(sp0, sp2)
    solver2.add_distance(sp0, sp2, 40.0)

    success2, points_pass2 = solver2.solve()
    assert success2
    # Invariant d'idempotence : distance entre passe 1 et passe 2 < 1e-4 mm
    for pt1, pt2 in zip(points_pass1, points_pass2):
        assert pt1.distance_to(pt2) < 1e-4
