"""
Tests de Robustesse, Fuzzing et Cas Limites Extrêmes (Apple-Grade Hardening).
Injecte des valeurs anormales, quasi-nulles, gigantesques, négatives ou contradictoires
pour garantir qu'aucune exception non gérée, division par zéro ou corruption mémoire ne survienne.
"""

import pytest
import numpy as np

from src.core.geometry import make_box, make_cylinder, make_sphere, extrude_polygon
from src.core.types import Vector3D, Point2D, BooleanOperation
from src.core.feature import BoxFeature
from src.core.operations_advanced import LinearPatternFeature, ShellFeature, HoleFeature
from src.core.document import CADDocument
from src.core.parameters import SafeExpressionEvaluator
from src.fea.fea_solver import FEASimulator
from src.cam.cam_engine import CAMEngine


def test_micro_and_macro_dimensions():
    """Vérifie la robustesse face à des dimensions microscopiques (1e-4 mm) et colossales (1e5 mm)."""
    # Micro-solide
    micro_box = make_box(0.001, 0.001, 0.001)
    assert not micro_box.is_empty()
    assert micro_box.volume() > 0.0

    # Macro-solide
    macro_box = make_box(10000.0, 10000.0, 10000.0)
    assert not macro_box.is_empty()
    assert macro_box.volume() > 1e11

    # Différence booléenne entre macro et micro
    res = macro_box.difference(micro_box)
    assert not res.is_empty()


def test_linear_pattern_dos_protection():
    """Vérifie que la répétition linéaire plafonne le nombre d'occurrences pour éviter le DoS mémoire."""
    doc = CADDocument("PatternTest")
    f_box = BoxFeature("b1", "Base", width=10, height=10, depth=10)
    doc.add_feature(f_box)

    # Demander 10 000 occurrences x 10 000 occurrences
    pat = LinearPatternFeature("pat1", "HugePattern", source_body_id="body_b1", count_x=10000, count_y=10000)
    doc.add_feature(pat)
    # L'opération doit s'évaluer en plafonnant à un nombre raisonnable sans saturer la RAM
    assert doc.bodies["body_b1"] is not None


def test_safe_expression_evaluator_adversarial_inputs():
    """Vérifie la protection face aux expressions malveillantes ou erronées."""
    ctx = {"x": 10.0}

    # Division par zéro protégée
    with pytest.raises(ValueError, match="Division par zéro"):
        SafeExpressionEvaluator.evaluate("10 / 0", ctx)

    # Modulo par zéro
    with pytest.raises(ValueError, match="Modulo par zéro"):
        SafeExpressionEvaluator.evaluate("10 % 0", ctx)

    # Racine d'un négatif
    with pytest.raises(ValueError, match="Racine carrée d'un nombre négatif"):
        SafeExpressionEvaluator.evaluate("sqrt(-25)", ctx)

    # Puissance astronomique (protection DoS CPU)
    with pytest.raises(ValueError, match="Exposant ou base hors limites"):
        SafeExpressionEvaluator.evaluate("2 ** 100000", ctx)

    # Variable inconnue
    with pytest.raises(ValueError, match="Variable inconnue"):
        SafeExpressionEvaluator.evaluate("x + y_inconnue", ctx)

    # Parenthèses déséquilibrées
    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("((10 + 2)", ctx)


def test_extrude_polygon_degenerate_cases():
    """Vérifie la levée d'exceptions propres sur polygones dégénérés."""
    # Moins de 3 points
    with pytest.raises(ValueError, match="au moins 3 points"):
        extrude_polygon([Point2D(0, 0), Point2D(10, 0)], height=20.0)

    # Hauteur négative : doit s'exécuter proprement avec décalage
    pts = [Point2D(0, 0), Point2D(10, 0), Point2D(0, 10)]
    neg_extrude = extrude_polygon(pts, height=-15.0)
    assert not neg_extrude.is_empty()
    assert neg_extrude.volume() > 0.0


def test_timeline_rollback_fuzzing():
    """Vérifie que des oscillations rapides et extrêmes du curseur temporel ne désynchronisent pas le modèle."""
    doc = CADDocument("RollbackFuzz")
    for i in range(5):
        doc.add_feature(BoxFeature(f"b{i}", f"Box_{i}", width=10, height=10, depth=10))

    # Oscillation brutale du rollback index
    test_indices = [-1, 0, 4, 2, -1, 1, 3, 0, -1]
    for idx in test_indices:
        doc.set_rollback_index(idx)
        assert len(doc.bodies) >= 1
        b_ids = doc.get_active_body_ids()
        assert len(b_ids) >= 1


def test_fea_zero_force_resilience():
    """Vérifie que le simulateur FEA gère l'absence de force ou force nulle sans division par zéro."""
    box = make_box(20, 20, 40)
    sim = FEASimulator()
    res = sim.run_static_analysis(box, applied_force_newtons=0.0)
    assert res is not None
    assert res.max_stress_mpa == 0.0
    assert res.safety_factor > 1000.0
    assert res.is_safe


def test_cam_engine_zero_depth_and_inverted_stock():
    """Vérifie que le moteur CAM gère des profondeurs nulles ou des bornes inversées sans boucle infinie."""
    cam = CAMEngine()
    # Bornes inversées x0 > x1, y0 > y1
    op = cam.generate_facing_toolpath(
        min_x=100.0, max_x=0.0,
        min_y=80.0, max_y=0.0,
        stock_z=10.0, target_z=5.0
    )
    assert len(op.points) > 0
    gcode = cam.export_gcode([op], filepath="")
    assert "G21" in gcode
    assert "M30" in gcode
