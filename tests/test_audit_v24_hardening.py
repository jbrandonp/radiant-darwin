"""
Tests unitaires complets pour la validation de l'audit architectural et du durcissement v24.
Vérifie la robustesse de l'évaluateur d'expressions, des liaisons d'assemblage,
du solveur 2D, de la caméra, du maillage FEA vectorisé et de l'invalidation d'historique.
"""

import math
import numpy as np
import pytest

from src.core.types import Vector3D, Point2D, PlaneType, BooleanOperation
from src.core.geometry import make_box, make_cylinder, Solid
from src.core.feature import BoxFeature
from src.core.document import CADDocument
from src.core.parameters import SafeExpressionEvaluator, ParameterTable
from src.core.inspector import compute_inertia_tensor, compute_center_of_mass
from src.viewport.camera import CADCamera
from src.assembly.assembly_manager import AssemblyManager, JointType
from src.solver.constraints_2d import SketchConstraintSolver2D
from src.fea.fea_solver import FEASimulator, _vectorized_colormap_jet


def test_expression_units_and_constants() -> None:
    """Vérifie l'évaluation des unités d'ingénierie et des constantes mathématiques."""
    ctx = {"length": 50.0}
    # Unités transparentes
    assert pytest.approx(SafeExpressionEvaluator.evaluate("25mm", ctx), rel=1e-5) == 25.0
    assert pytest.approx(SafeExpressionEvaluator.evaluate("2cm", ctx), rel=1e-5) == 20.0
    assert pytest.approx(SafeExpressionEvaluator.evaluate("1m", ctx), rel=1e-5) == 1000.0
    assert pytest.approx(SafeExpressionEvaluator.evaluate("2inch", ctx), rel=1e-5) == 50.8
    assert pytest.approx(SafeExpressionEvaluator.evaluate("10mm + 2cm", ctx), rel=1e-5) == 30.0

    # Constantes mathématiques e et pi
    assert pytest.approx(SafeExpressionEvaluator.evaluate("e", ctx), rel=1e-5) == math.e
    assert pytest.approx(SafeExpressionEvaluator.evaluate("2 * pi", ctx), rel=1e-5) == 2.0 * math.pi
    assert pytest.approx(SafeExpressionEvaluator.evaluate("sin(90deg)", ctx), rel=1e-5) == 1.0


def test_camera_pan_in_zenith_view() -> None:
    """Vérifie que la caméra effectue un panoramique fluide même en vue de dessus / TOP."""
    cam = CADCamera()
    cam.set_preset_view("TOP")
    initial_target = cam.target
    # Doit fonctionner sans erreur ni NaN
    cam.pan(10.0, 5.0, viewport_height=600)
    assert not math.isnan(cam.target.x)
    assert not math.isnan(cam.target.y)
    assert not math.isnan(cam.target.z)
    assert cam.target != initial_target


def test_fea_vectorized_colormap() -> None:
    """Vérifie le dégradé cartographique vectorisé sur des tableaux NumPy."""
    vals = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0], dtype=np.float32)
    rgba = _vectorized_colormap_jet(vals)
    assert rgba.shape == (6, 4)
    # Bleu pur au début [0, 0, 1, 1]
    assert rgba[0, 0] == 0.0 and rgba[0, 2] == 1.0
    # Rouge pur à la fin [1, 0, 0, 1]
    assert rgba[5, 0] == 1.0 and rgba[5, 1] == 0.0 and rgba[5, 2] == 0.0

    # Test FEASimulator avec maillage déformé
    box = make_box(20.0, 20.0, 60.0)
    sim = FEASimulator()
    res = sim.run_static_analysis(box, applied_force_newtons=1500.0)
    assert res is not None
    heatmap = sim.generate_stress_heatmap_mesh(box, res)
    assert heatmap.vertex_colors is not None
    assert len(heatmap.vertex_colors) == len(heatmap.vertices)


def test_assembly_joint_limits_and_cylindrical() -> None:
    """Vérifie le bridage des butées de course (min/max) et les liaisons pivot-glissant."""
    mgr = AssemblyManager()
    b1 = make_box(20, 20, 20)
    b2 = make_box(10, 10, 10)
    bodies = {"body_1": b1, "body_2": b2}

    # Liaison pivot avec butée [-45, +45]
    joint = mgr.add_joint(
        "j1", "Pivot", JointType.REVOLUTE, "body_1", "body_2",
        axis=Vector3D(0.0, 0.0, 1.0)
    )
    joint.min_limit = -45.0
    joint.max_limit = 45.0

    # Tentative de déplacement hors limite (+90 deg -> bridé à +45 deg)
    res = mgr.animate_joint("j1", bodies, 90.0)
    assert joint.current_value == 45.0
    assert "body_2" in res

    # Liaison cylindrique
    j_cyl = mgr.add_joint(
        "j2", "Cyl", JointType.CYLINDRICAL, "body_1", "body_2",
        axis=Vector3D(1.0, 0.0, 0.0)
    )
    res2 = mgr.animate_joint("j2", bodies, 30.0)
    assert j_cyl.current_value == 30.0


def test_document_feature_suppression_invalidation() -> None:
    """Vérifie que la désactivation d'une feature invalide le cache et reconstruit le modèle."""
    doc = CADDocument("TestDoc")
    f1 = BoxFeature("f1", "Box 1", width=20.0, height=20.0, depth=20.0)
    f2 = BoxFeature("f2", "Box 2", width=10.0, height=10.0, depth=10.0, operation=BooleanOperation.NEW_BODY)
    doc.add_feature(f1)
    doc.add_feature(f2)
    assert len(doc.bodies) == 2

    # Désactiver f2
    doc.set_feature_suppressed("f2", True)
    assert len(doc.bodies) == 1
    assert "body_f1" in doc.bodies

    # Réactiver f2
    doc.set_feature_suppressed("f2", False)
    assert len(doc.bodies) == 2


def test_solver_2d_diagnostics() -> None:
    """Vérifie le calcul des degrés de liberté et la détection des sur-contraintes."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))
    # 2 points = 4 DoF initialement
    dof, msg = solver.calculate_degrees_of_freedom()
    assert dof == 4

    # Ajouter contrainte fixe sur p0 (2 DoF retirés)
    solver.add_fixed(p0, 0.0, 0.0)
    dof2, _ = solver.calculate_degrees_of_freedom()
    assert dof2 == 2

    # Ajouter horizontalité et distance (2 DoF retirés -> 0 DoF, entièrement contrainte)
    solver.add_horizontal(p0, p1)
    solver.add_distance(p0, p1, 25.0)
    dof3, msg3 = solver.calculate_degrees_of_freedom()
    assert dof3 == 0
    assert "Entièrement contrainte" in msg3


def test_inertia_tensor_robustness() -> None:
    """Vérifie que le tenseur d'inertie gère les maillages et fournit des moments positifs."""
    box = make_box(20.0, 30.0, 40.0)
    inertia = compute_inertia_tensor(box, density_g_cm3=2.7)
    assert inertia.ixx > 0.0
    assert inertia.iyy > 0.0
    assert inertia.izz > 0.0
    assert all(p > 0.0 for p in inertia.principal_moments)
    assert all(rg > 0.0 for rg in inertia.radius_of_gyration)
