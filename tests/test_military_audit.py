"""
Suite de tests de niveau militaire (Military-Grade Hardening & Fuzzing).
Vérifie la résistance absolue du logiciel face aux cas extrêmes, attaques DoS,
données corrompues, singularités géométriques et conditions aux limites.
"""

from __future__ import annotations
import os
import tempfile
import pytest

from src.core.types import Vector3D, Point2D, BooleanOperation, FeatureStatus
from src.core.parameters import SafeExpressionEvaluator, ParameterTable
from src.core.serializer import ProjectSerializer
from src.core.document import CADDocument
from src.core.feature import BoxFeature, BooleanFeature
from src.core.operations_advanced import LinearPatternFeature, CircularPatternFeature, ShellFeature
from src.core.geometry import make_box, make_cylinder, make_sphere, make_cone, extrude_polygon
from src.solver.constraints_2d import SketchConstraintSolver2D
from src.cam.cam_engine import CAMEngine
from src.sheetmetal.sheet_metal import SheetMetalPart, SheetMetalRule
from src.fea.fea_solver import FEASimulator
from src.materials.material_db import PhysicalMaterial, MATERIAL_LIBRARY
from src.render.raytracer import PBRRaytracer
from src.render.pbr_material import PBR_LIBRARY


def test_military_ast_dos_protection() -> None:
    """Valide la protection contre les attaques par déni de service CPU via exposants géants."""
    # Exposant excessif
    with pytest.raises(ValueError, match="sécurité"):
        SafeExpressionEvaluator.evaluate("2 ** 500", {})

    # Base excessive
    with pytest.raises(ValueError, match="sécurité"):
        SafeExpressionEvaluator.evaluate("(10 ** 25) ** 2", {})


def test_military_ast_recursion_limit() -> None:
    """Valide la protection contre l'épuisement de pile par imbrication d'arbres syntaxiques."""
    nested_expr = "- " * 35 + "5"
    with pytest.raises(ValueError, match="récursion"):
        SafeExpressionEvaluator.evaluate(nested_expr, {})


def test_military_ast_string_length_limit() -> None:
    """Valide le rejet des expressions anormalement longues."""
    huge_expr = "1 + " * 300 + "1"
    with pytest.raises(ValueError, match="trop longue"):
        SafeExpressionEvaluator.evaluate(huge_expr, {})


def test_military_ast_arithmetic_guards() -> None:
    """Valide la protection contre divisions par zéro, modulos par zéro et racines négatives."""
    with pytest.raises(ValueError, match="Division par zéro"):
        SafeExpressionEvaluator.evaluate("100 / 0", {})

    with pytest.raises(ValueError, match="Modulo par zéro"):
        SafeExpressionEvaluator.evaluate("100 % 0", {})

    with pytest.raises(ValueError, match="Racine carrée d'un nombre négatif"):
        SafeExpressionEvaluator.evaluate("sqrt(-25)", {})


def test_military_ast_injection_prevention() -> None:
    """Valide l'interdiction stricte de toute injection de code ou fonction non autorisée."""
    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("__import__('os').system('dir')", {})

    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("open('secret.txt')", {})

    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("eval('1+1')", {})


def test_military_serializer_fuzzing_garbage() -> None:
    """Valide la résilience face à des fichiers de projet totalement corrompus."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_json = os.path.join(tmp_dir, "corrupt.cadproj")

        # 1. Données binaires aléatoires
        with open(bad_json, "wb") as f:
            f.write(b"\x00\xff\xfe\x01\x88NOT_JSON")
        assert ProjectSerializer.load_project(bad_json) is None

        # 2. JSON valide mais type racine incorrect (liste au lieu de dict)
        with open(bad_json, "w", encoding="utf-8") as f:
            f.write("[1, 2, 3, 4, 5]")
        assert ProjectSerializer.load_project(bad_json) is None

        # 3. JSON tronqué
        with open(bad_json, "w", encoding="utf-8") as f:
            f.write('{"name": "Incomplet", "sketches": [{"id": ')
        assert ProjectSerializer.load_project(bad_json) is None


def test_military_serializer_fuzzing_malformed_fields() -> None:
    """Valide la résistance face à des structures JSON contenant des types aberrants."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_json = os.path.join(tmp_dir, "malformed.cadproj")
        payload = (
            '{"name": "Fuzzed Project", '
            '"sketches": ["string_instead_of_dict", 42, null, {"id": "sk1", "entities": [{"points": "bad"}]}], '
            '"features": [null, 999, "bad_feat", {"class": "BoxFeature", "parameters": "not_a_dict"}], '
            '"rollback_index": "not_an_int"}'
        )
        with open(bad_json, "w", encoding="utf-8") as f:
            f.write(payload)

        # Doit charger gracieusement le document sans crash
        doc = ProjectSerializer.load_project(bad_json)
        assert doc is not None
        assert doc.name == "Fuzzed Project"
        assert len(doc.features) == 1  # BoxFeature avec paramètres par défaut


def test_military_boolean_self_operation() -> None:
    """Valide qu'une opération booléenne sur le même corps ne supprime pas la géométrie."""
    doc = CADDocument("Test Boolean Self")
    b1 = BoxFeature("b1", "Box 1", 20.0, 20.0, 20.0)
    doc.add_feature(b1)
    assert len(doc.bodies) == 1

    # Tenter un CUT du corps avec lui-même
    b_cut = BooleanFeature("b_self", "Self Cut", b1.body_id, b1.body_id, BooleanOperation.CUT)
    doc.add_feature(b_cut)
    assert b_cut.status == FeatureStatus.ERROR
    # Le corps d'origine ne doit pas être détruit
    assert b1.body_id in doc.bodies


def test_military_patterns_memory_bounds() -> None:
    """Valide que des compteurs de répétitions extrêmes ne provoquent pas de dépassement mémoire."""
    box = make_box(10.0, 10.0, 10.0)
    bodies = {"body_1": box}

    # Répétition linéaire avec 100 000 occurrences demandées
    pat_lin = LinearPatternFeature("pat1", "Lin Huge", "body_1", count_x=10000, count_y=10000)
    res_lin = pat_lin.evaluate(bodies, {})
    assert pat_lin.status == FeatureStatus.OK
    # Le nombre d'instances est plafonné en interne pour éviter un crash OOM
    assert "body_1" in res_lin

    # Répétition circulaire avec 1 000 000 occurrences demandées
    pat_circ = CircularPatternFeature("pat2", "Circ Huge", "body_1", count=1000000)
    res_circ = pat_circ.evaluate(bodies, {})
    assert pat_circ.status == FeatureStatus.OK
    assert "body_1" in res_circ


def test_military_cam_engine_robustness() -> None:
    """Valide le moteur CAM sous des profondeurs négatives et dossiers imbriqués."""
    engine = CAMEngine()
    box = make_box(50.0, 50.0, 10.0)

    # Profondeur négative passée par erreur
    op = engine.generate_contour_toolpath(box, depth_mm=-15.0)
    assert len(op.points) > 0
    # Les coordonnées Z usinées doivent descendre dans la matière et non monter
    z_coords = [pt.pos.z for pt in op.points if not pt.is_rapid]
    assert min(z_coords) <= -14.0

    # Export vers un chemin imbriqué inexistant
    with tempfile.TemporaryDirectory() as tmp_dir:
        nested_path = os.path.join(tmp_dir, "deep", "nested", "folder", "test.gcode")
        gcode = engine.export_gcode([op], nested_path)
        assert os.path.exists(nested_path)
        assert len(gcode) > 0


def test_military_sheet_metal_parameter_clamps() -> None:
    """Valide le clamping des paramètres de tôlerie aberrants ou négatifs."""
    rule = SheetMetalRule("Règle Extrême", thickness_mm=-5.0, bend_radius_mm=-2.0, k_factor=3.5)
    part = SheetMetalPart(base_width=-50.0, base_length=-100.0, rule=rule)

    # Les dimensions doivent être ramenées à des valeurs physiques valides
    assert part.base_width >= 1.0
    assert part.base_length >= 1.0

    # Le calcul de perte au pli ne doit pas produire de NaN ni d'infini
    ba = part.calculate_bend_allowance(90.0)
    bd = part.calculate_bend_deduction(90.0)
    assert not (ba != ba)  # Pas de NaN
    assert not (bd != bd)  # Pas de NaN
    assert ba > 0.0

    # Dépliage à plat
    part.add_flange(20.0, 90.0)
    flat = part.generate_flat_pattern()
    assert flat.total_length_mm > 0.0


def test_military_fea_stress_guards() -> None:
    """Valide le comportement du solveur FEA avec forces négatives et propriétés limites."""
    box = make_box(20.0, 20.0, 50.0)

    # Matériau avec Young modulus minimal
    mat_soft = PhysicalMaterial(
        name="Ultra Souple",
        category="Polymères",
        density_g_cm3=1.0,
        young_modulus_gpa=0.0001,
        poisson_ratio=0.45,
        yield_strength_mpa=5.0,
        ultimate_strength_mpa=10.0,
        thermal_conductivity=0.1,
        color=MATERIAL_LIBRARY["Acier Carbone C45"].color
    )
    sim = FEASimulator(mat_soft)

    # Force négative
    res = sim.run_static_analysis(box, applied_force_newtons=-2500.0)
    assert res is not None
    assert res.max_stress_mpa > 0.0
    assert res.safety_factor > 0.0
    assert not (res.max_displacement_mm != res.max_displacement_mm)


def test_military_raytracer_dimensions_bounds() -> None:
    """Valide le raytracer PBR face à des résolutions nulles ou négatives et matériaux extrêmes."""
    tracer = PBRRaytracer()
    box = make_box(20.0, 20.0, 20.0)
    mat = PBR_LIBRARY["Aluminium Brossé"]

    # Résolution négative ou nulle
    img = tracer.render_solid_to_image(box, mat, width=-100, height=0)
    assert not img.isNull()
    assert img.width() >= 1
    assert img.height() >= 1


def test_military_solver_index_out_of_bounds() -> None:
    """Valide la tolérance du solveur d'esquisse 2D face à des index de contraintes invalides."""
    solver = SketchConstraintSolver2D()
    solver.add_point(Point2D(0.0, 0.0))
    solver.add_point(Point2D(10.0, 0.0))

    # Ajouter une contrainte référençant un index inexistant (999)
    solver.add_distance(0, 999, -50.0)  # Index hors limites + distance négative
    success, points = solver.solve()
    # Le solveur ne doit pas lever d'IndexError
    assert isinstance(points, list)
    assert len(points) == 2
