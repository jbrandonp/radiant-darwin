"""
Suite de tests de stabilité, de robustesse extrême et de cas limites (Stress Testing).
Vérifie la résilience du moteur face aux valeurs négatives, divisions par zéro,
dépendances orphelines, contraintes contradictoires et fichiers corrompus.
"""

import os
import tempfile
import pytest
import numpy as np
import manifold3d as m

from src.core.geometry import make_box, make_cylinder, make_sphere, make_cone, make_torus, make_wedge, Solid
from src.core.types import PlaneType, BooleanOperation, Point2D, Vector3D, FeatureStatus
from src.core.document import CADDocument
from src.core.feature import BoxFeature, ExtrudeFeature, BooleanFeature
from src.core.operations_advanced import HoleFeature, ShellFeature, LinearPatternFeature, DraftFeature, FilletFeature, ChamferFeature
from src.core.fasteners import FastenerFeature
from src.core.section_tools import slice_solid_contours, create_sketch_from_cross_section
from src.core.parameters import SafeExpressionEvaluator, ParameterTable
from src.core.serializer import ProjectSerializer
from src.solver.constraints_2d import SketchConstraintSolver2D
from src.sheetmetal.sheet_metal import SheetMetalPart, SheetMetalRule
from src.cam.cam_engine import CAMEngine
from src.assembly.assembly_manager import AssemblyManager
from src.drawing.drawing_generator import TechnicalDrawingGenerator
from src.fea.fea_solver import FEASimulator
from src.render.raytracer import PBRRaytracer
from src.render.pbr_material import PBR_LIBRARY


def test_geometry_negative_and_zero_dimensions() -> None:
    """Vérifie que les dimensions nulles ou négatives sont clampées sans crash."""
    b = make_box(-10.0, 0.0, -5.0)
    assert b.volume() > 0.0

    c = make_cylinder(radius=-2.0, height=0.0)
    assert c.volume() > 0.0

    s = make_sphere(radius=-5.0)
    assert s.volume() > 0.0

    cone = make_cone(radius_bottom=-1.0, radius_top=-1.0, height=0.0)
    assert cone.volume() >= 0.0


def test_shell_edge_cases_and_thick_walls() -> None:
    """Vérifie la gestion des parois trop épaisses ou d'épaisseurs négatives."""
    box_solid = make_box(20.0, 20.0, 20.0)
    bodies = {"body_1": box_solid}

    # 1. Épaisseur supérieure à la demi-dimension de la pièce
    shell_too_thick = ShellFeature("feat_shell_1", "Shell Trop Épais", target_body_id="body_1", wall_thickness=15.0)
    res_thick = shell_too_thick.evaluate(bodies, {})
    assert shell_too_thick.status == FeatureStatus.ERROR
    assert res_thick["body_1"].volume() == box_solid.volume()

    # 2. Épaisseur négative
    shell_negative = ShellFeature("feat_shell_2", "Shell Négatif", target_body_id="body_1", wall_thickness=-2.0)
    res_neg = shell_negative.evaluate(bodies, {})
    assert shell_negative.status == FeatureStatus.ERROR

    # 3. Épaisseur nulle
    shell_zero = ShellFeature("feat_shell_3", "Shell Zéro", target_body_id="body_1", wall_thickness=0.0)
    res_zero = shell_zero.evaluate(bodies, {})
    assert shell_zero.status == FeatureStatus.ERROR


def test_document_dag_broken_dependencies() -> None:
    """Vérifie la résilience du DAG lors de la suppression de corps cibles."""
    doc = CADDocument("Test DAG Résilience")
    b_feat = BoxFeature("b1", "Boîte Base", width=40.0, height=40.0, depth=20.0)
    doc.add_feature(b_feat)

    h_feat = HoleFeature("h1", "Perçage", target_body_id=b_feat.body_id, pos_x=0.0, pos_y=0.0, diameter=10.0)
    doc.add_feature(h_feat)
    assert len(doc.bodies) == 1

    # Suppression du corps parent (b1) : l'opération dépendante (h1) doit passer en erreur sans crash
    doc.remove_feature("b1")
    assert len(doc.bodies) == 0
    assert h_feat.status == FeatureStatus.ERROR

    # Rollback indices extrêmes hors limites
    doc.set_rollback_index(-999)
    assert doc.rollback_index == -1
    doc.set_rollback_index(99999)
    assert doc.rollback_index == len(doc.features) - 1


def test_parameters_evaluator_stress() -> None:
    """Vérifie le comportement de l'évaluateur AST face aux erreurs mathématiques."""
    # 1. Division par zéro
    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("10 / 0", {})

    # 2. Chaîne vide et espaces
    assert SafeExpressionEvaluator.evaluate("", {}) == 0.0
    assert SafeExpressionEvaluator.evaluate("   ", {}) == 0.0

    # 3. Boucles de dépendances circulaires
    table = ParameterTable()
    table.set_parameter("param_a", "param_b + 1")
    table.set_parameter("param_b", "param_a + 1")
    # Ne doit pas entrer en boucle infinie
    table.evaluate_all()
    assert table.get_value("param_a") == 0.0
    assert table.get_value("param_b") == 0.0


def test_solver_2d_contradictory_constraints() -> None:
    """Vérifie que le solveur 2D rejette les systèmes sur-contraints contradictoires."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))

    solver.add_fixed(p0, 0.0, 0.0)
    # Contradiction flagrante : distance = 10 ET distance = 50 entre p0 et p1
    solver.add_distance(p0, p1, 10.0)
    solver.add_distance(p0, p1, 50.0)

    success, _ = solver.solve()
    assert success is False, "Le solveur aurait dû échouer face à des contraintes contradictoires"


def test_cam_engine_stress() -> None:
    """Vérifie la robustesse du moteur CAM avec bornes inversées et liste vide."""
    cam = CAMEngine()

    # 1. Bornes inversées (min_x > max_x)
    op = cam.generate_facing_toolpath(min_x=50.0, max_x=-20.0, min_y=30.0, max_y=-10.0, stock_z=2.0, target_z=0.0)
    assert len(op.points) > 0

    # 2. Export G-Code sans opérations
    with tempfile.TemporaryDirectory() as tmpdir:
        gcode_path = os.path.join(tmpdir, "empty_cam.gcode")
        content = cam.export_gcode([], gcode_path)
        assert "M30" in content
        assert os.path.exists(gcode_path)


def test_sheet_metal_extreme_angles() -> None:
    """Vérifie la stabilité numérique du facteur K et des pliages aux angles extrêmes."""
    part = SheetMetalPart(base_width=50.0, base_length=50.0)

    # 1. Angle à 0°
    ba_zero = part.calculate_bend_allowance(0.0)
    bd_zero = part.calculate_bend_deduction(0.0)
    assert not np.isnan(ba_zero) and not np.isinf(ba_zero)
    assert not np.isnan(bd_zero) and not np.isinf(bd_zero)

    # 2. Angle à 180° (plis écrasés / ourlets)
    ba_180 = part.calculate_bend_allowance(180.0)
    bd_180 = part.calculate_bend_deduction(180.0)
    assert not np.isnan(ba_180) and not np.isinf(ba_180)
    assert not np.isnan(bd_180) and not np.isinf(bd_180)


def test_serializer_corrupt_file_handling() -> None:
    """Vérifie que la lecture de fichiers corrompus ou invalides retourne None sans planter."""
    # Fichier inexistant
    assert ProjectSerializer.load_project("chemin/inexistant_9999.cadproj") is None

    with tempfile.TemporaryDirectory() as tmpdir:
        # Fichier avec syntaxe JSON cassée
        broken_path = os.path.join(tmpdir, "broken.cadproj")
        with open(broken_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json content ...")
        assert ProjectSerializer.load_project(broken_path) is None

        # Fichier avec tableau au lieu d'un objet dictionnaire
        array_path = os.path.join(tmpdir, "array.cadproj")
        with open(array_path, "w", encoding="utf-8") as f:
            f.write("[1, 2, 3]")
        assert ProjectSerializer.load_project(array_path) is None


def test_render_empty_solid() -> None:
    """Vérifie que le raytracer PBR gère un solide vide ou une petite résolution sans crash."""
    empty_solid = Solid(m.Manifold() if hasattr(m, "Manifold") else make_box(0.001, 0.001, 0.001)._manifold, "Vide")
    raytracer = PBRRaytracer()
    mat = PBR_LIBRARY["Chrome Miroir"]

    img = raytracer.render_solid_to_image(empty_solid, mat, width=10, height=10)
    assert img.width() == 10
    assert img.height() == 10


def test_fea_zero_and_negative_loads() -> None:
    """Vérifie la stabilité de la simulation FEA face à une charge nulle ou négative."""
    solid = make_box(30.0, 30.0, 10.0)
    sim = FEASimulator()

    # Charge nulle (0 N)
    res_zero = sim.run_static_analysis(solid, applied_force_newtons=0.0)
    assert res_zero is not None
    assert res_zero.max_stress_mpa == pytest.approx(0.0)
    assert res_zero.is_safe is True

    # Charge négative (-500 N)
    res_neg = sim.run_static_analysis(solid, applied_force_newtons=-500.0)
    assert res_neg is not None
    assert res_neg.max_stress_mpa >= 0.0


def test_extreme_primitives_geometry() -> None:
    """Vérifie la robustesse face à des primitives avec rayons nuls ou inversés."""
    c = make_cone(radius_bottom=0.0, radius_top=0.0, height=10.0)
    assert c is not None and c.is_manifold()

    t = make_torus(major_radius=5.0, minor_radius=10.0)
    assert t is not None and t.is_manifold()

    w = make_wedge(dx=-10.0, dy=0.0, dz=-5.0)
    assert w is not None and w.is_manifold()


def test_section_cut_edge_cases() -> None:
    """Vérifie les coupes de section hors limites et sur contours vides."""
    box = make_box(10.0, 10.0, 10.0)
    contours = slice_solid_contours(box, axis="Z", coordinate=500.0)
    assert contours == []

    sk = create_sketch_from_cross_section([], "Z", "sk_empty")
    assert sk is None


def test_fastener_unknown_metric_size() -> None:
    """Vérifie le repli sécurisé sur M6 lorsqu'une taille métrique inconnue est demandée."""
    feat = FastenerFeature("f_unk", "Vis Inconnue", fastener_type="hex_bolt", standard_size="M999_INVALIDE")
    bodies = feat.evaluate({}, {})
    assert "body_f_unk" in bodies
    assert bodies["body_f_unk"].is_manifold()


def test_draft_feature_multi_axes_and_extreme_angles() -> None:
    """Vérifie la dépouille avec angle extrême (90°) et axes X, Y, Z."""
    box = make_box(20.0, 20.0, 20.0)
    # Angle extrême clampé sans explosion tangente
    feat90 = DraftFeature("d90", "Draft 90", target_body_id="b1", draft_angle_deg=90.0, pull_axis="Z")
    res90 = feat90.evaluate({"b1": box}, {})
    assert "b1" in res90
    assert res90["b1"].is_manifold()

    # Axes X et Y
    feat_x = DraftFeature("dx", "Draft X", target_body_id="b1", draft_angle_deg=5.0, pull_axis="X")
    res_x = feat_x.evaluate({"b1": box}, {})
    assert "b1" in res_x

    feat_y = DraftFeature("dy", "Draft Y", target_body_id="b1", draft_angle_deg=-5.0, pull_axis="Y")
    res_y = feat_y.evaluate({"b1": box}, {})
    assert "b1" in res_y


def test_solid_translate_polymorphism() -> None:
    """Vérifie que translate accepte indifféremment Vector3D, liste ou 3 flottants."""
    b = make_box(10.0, 10.0, 10.0)
    t1 = b.translate(Vector3D(5.0, 0.0, 0.0))
    t2 = b.translate([5.0, 0.0, 0.0])
    t3 = b.translate(5.0, 0.0, 0.0)

    assert t1.bounding_box()[0].x == pytest.approx(5.0)
    assert t2.bounding_box()[0].x == pytest.approx(5.0)
    assert t3.bounding_box()[0].x == pytest.approx(5.0)


def test_cam_clearance_and_contour_depth_robustness() -> None:
    """Vérifie que le moteur CAM positionne le dégagement au-dessus de la pièce."""
    solid = make_box(30.0, 20.0, 15.0).translate(0.0, 0.0, 25.0)
    cam = CAMEngine()
    op = cam.generate_contour_toolpath(solid, depth_mm=5.0)
    assert op is not None
    # Le Z initial doit être au-dessus du sommet de la pièce (25 + 15 + safe_z = 45 mm)
    assert op.points[0].pos.z >= 45.0


def test_drawing_generator_classmethod_and_empty_solid() -> None:
    """Vérifie la génération de plan via classmethod sur solide vide."""
    empty_solid = Solid(make_box(0.001, 0.001, 0.001)._manifold, "Vide")
    sheet = TechnicalDrawingGenerator.generate_views(empty_solid)
    assert sheet is not None
    assert len(sheet.lines) >= 4  # Cadre extérieur présent


def test_parameters_round_min_max_multi_args() -> None:
    """Vérifie la robustesse des fonctions round, min, max dans l'évaluateur."""
    ctx = {"val": 3.14159}
    assert SafeExpressionEvaluator.evaluate("round(val, 2)", ctx) == 3.14
    assert SafeExpressionEvaluator.evaluate("round(val)", ctx) == 3.0
    assert SafeExpressionEvaluator.evaluate("min(10, 5, 20)", ctx) == 5.0
    assert SafeExpressionEvaluator.evaluate("max(10, 5, 20)", ctx) == 20.0
