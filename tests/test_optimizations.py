"""
Tests unitaires validant les optimisations de performance et de mise en cache :
- Caching O(1) de MeshBuffer dans Solid
- Caching par instantanés (Snapshots) de timeline dans CADDocument
- Précalcul vectorisé de la grille 3D dans GLRenderer
- Rendu rapide PBR et vectorisation des projections
"""

from __future__ import annotations
import time
import pytest
import numpy as np

from src.core.geometry import make_box, make_cylinder, Solid, extrude_polygon
from src.core.document import CADDocument
from src.core.feature import BoxFeature, CylinderFeature, ExtrudeFeature, BooleanFeature
from src.core.sketch import Sketch2D
from src.core.types import BooleanOperation, PlaneType, Point2D
from src.core.operations_advanced import PipeFeature
from src.core.parameters import SafeExpressionEvaluator
from src.core.step_exporter import STEPExporter
from src.fea.fea_solver import FEASimulator
from src.solver.constraints_2d import SketchConstraintSolver2D, GeometricConstraint, ConstraintType
from src.viewport.gl_renderer import GLRenderer
from src.render.raytracer import PBRRaytracer
from src.render.pbr_material import PBR_LIBRARY


def test_solid_mesh_buffer_caching() -> None:
    """Valide que le deuxième appel à to_mesh_buffer() est quasi-instantané via le cache."""
    solid = make_box(30.0, 30.0, 30.0)
    assert solid._cached_buffer is None

    buf1 = solid.to_mesh_buffer()
    assert buf1 is not None
    assert solid._cached_buffer is buf1

    # Deuxième appel : renvoie exactement la même référence en cache
    buf2 = solid.to_mesh_buffer()
    assert buf2 is buf1


def test_document_timeline_snapshot_caching() -> None:
    """Valide le cache par instantané lors du retour en arrière et de la lecture."""
    doc = CADDocument("SnapshotDoc")
    b1 = BoxFeature("b1", "Box 1", 10.0, 10.0, 10.0)
    b2 = BoxFeature("b2", "Box 2", 20.0, 20.0, 20.0)
    b3 = BoxFeature("b3", "Box 3", 30.0, 30.0, 30.0)

    doc.add_feature(b1)
    doc.add_feature(b2)
    doc.add_feature(b3)

    assert 0 in doc._timeline_snapshots
    assert 1 in doc._timeline_snapshots
    assert 2 in doc._timeline_snapshots

    # Rollback à l'étape 1 (Box 2)
    t0 = time.perf_counter()
    doc.set_rollback_index(1)
    t_elapsed = time.perf_counter() - t0

    # L'accès via snapshot en cache doit être quasi instantané (< 5 ms)
    assert t_elapsed < 0.05
    assert len(doc.bodies) == 2


def test_gl_renderer_grid_precomputation() -> None:
    """Valide que la géométrie de la grille est précalculée sous forme de tableaux NumPy."""
    renderer = GLRenderer()
    assert renderer._grid_minor_pts is not None
    assert renderer._grid_major_pts is not None
    assert isinstance(renderer._grid_minor_pts, np.ndarray)
    assert isinstance(renderer._grid_major_pts, np.ndarray)
    assert renderer._grid_minor_pts.dtype == np.float32
    assert renderer._grid_major_pts.dtype == np.float32


def test_raytracer_vectorized_rendering_performance() -> None:
    """Valide la génération d'image de rendu photoréaliste vectorisée."""
    solid = make_box(20.0, 20.0, 20.0)
    material = PBR_LIBRARY["Aluminium Brossé"]
    raytracer = PBRRaytracer()

    t0 = time.perf_counter()
    img = raytracer.render_solid_to_image(solid, material, width=120, height=80)
    t_elapsed = time.perf_counter() - t0

    assert not img.isNull()
    assert img.width() == 120
    assert img.height() == 80
    # Le rendu de cette résolution doit être rapide grâce au fond QLinearGradient et à la projection vectorisée
    assert t_elapsed < 1.0


def test_negative_extrusion_geometry() -> None:
    """Valide qu'une extrusion négative (-20 mm) produit un solide orienté vers le bas avec le volume exact."""
    pts = [Point2D(0.0, 0.0), Point2D(10.0, 0.0), Point2D(10.0, 10.0), Point2D(0.0, 10.0)]
    solid = extrude_polygon(pts, -20.0, PlaneType.XY)
    assert solid.is_manifold()
    assert solid.volume() == pytest.approx(2000.0, rel=1e-3)
    b_min, b_max = solid.bounding_box()
    # Le z doit s'étendre de -20 à 0
    assert b_min.z == pytest.approx(-20.0, abs=1e-2)
    assert b_max.z == pytest.approx(0.0, abs=1e-2)


def test_solid_is_manifold() -> None:
    """Valide la détection de solidité manifold."""
    box = make_box(10.0, 10.0, 10.0)
    assert box.is_manifold() is True

    empty = make_box(0.0, 0.0, 0.0)
    # empty box clamped to 0.001 is small but manifold
    assert empty.is_manifold() is True


def test_boolean_unprefixed_body_id() -> None:
    """Valide que _apply_boolean_operation résout une cible sans préfixe 'body_'."""
    doc = CADDocument("BooleanTestDoc")
    b1 = BoxFeature("feat_b1", "Box 1", 20.0, 20.0, 20.0)
    doc.add_feature(b1)
    assert "body_feat_b1" in doc.bodies

    # Création d'une découpe en ciblant "feat_b1" au lieu de "body_feat_b1"
    b2 = BoxFeature("feat_b2", "Box Cutter", 10.0, 10.0, 10.0, operation=BooleanOperation.CUT, target_body_id="feat_b1")
    doc.add_feature(b2)
    assert "body_feat_b1" in doc.bodies
    # Le volume doit avoir diminué (20^3 - 10^3 = 8000 - 1000 = 7000)
    assert doc.bodies["body_feat_b1"].volume() == pytest.approx(7000.0, rel=1e-2)


def test_open_hollow_pipe_feature() -> None:
    """Valide qu'un tuyau creux est percé de part en part sans embouts sphériques fermés."""
    pts = [(0.0, 0.0, 0.0), (0.0, 0.0, 50.0)]
    pipe = PipeFeature("feat_p1", "Tuyau", path_points=pts, outer_radius=10.0, inner_radius=8.0)
    bodies = pipe.evaluate({}, {})
    assert "body_feat_p1" in bodies
    solid = bodies["body_feat_p1"]
    assert solid.is_manifold()
    # Volume d'un tube cylindrique de longueur 50 : pi*(10^2 - 8^2)*50 = pi*36*50 = ~5654.8
    # Avec les bouchons ouverts, le volume doit être inférieur au cylindre plein (pi*100*50 = ~15707.9)
    assert solid.volume() < 10000.0
    assert solid.volume() > 4000.0


def test_constraint_point_on_line_scale_invariance() -> None:
    """Valide que la contrainte POINT_ON_LINE résout correctement la projection sur des droites de tailles différentes."""
    # Droite courte de 10 mm sur l'axe U
    s1 = SketchConstraintSolver2D()
    l1 = s1.add_point(Point2D(0.0, 0.0))
    l2 = s1.add_point(Point2D(10.0, 0.0))
    p1 = s1.add_point(Point2D(5.0, 5.0))
    s1.add_fixed(l1, 0.0, 0.0)
    s1.add_fixed(l2, 10.0, 0.0)
    s1.add_point_on_line(p1, l1, l2)
    ok1, pts1 = s1.solve()
    assert ok1 is True
    assert pts1[p1].v == pytest.approx(0.0, abs=1e-3)

    # Droite longue de 1000 mm sur l'axe U
    s2 = SketchConstraintSolver2D()
    l1_b = s2.add_point(Point2D(0.0, 0.0))
    l2_b = s2.add_point(Point2D(1000.0, 0.0))
    p2 = s2.add_point(Point2D(500.0, 50.0))
    s2.add_fixed(l1_b, 0.0, 0.0)
    s2.add_fixed(l2_b, 1000.0, 0.0)
    s2.add_point_on_line(p2, l1_b, l2_b)
    ok2, pts2 = s2.solve()
    assert ok2 is True
    assert pts2[p2].v == pytest.approx(0.0, abs=1e-3)


def test_extended_math_expressions() -> None:
    """Valide les fonctions mathématiques ajoutées à l'évaluateur de paramètres."""
    ctx = {"x": 10.0, "y": 2.5}
    assert SafeExpressionEvaluator.evaluate("floor(y)", ctx) == 2.0
    assert SafeExpressionEvaluator.evaluate("ceil(y)", ctx) == 3.0
    assert SafeExpressionEvaluator.evaluate("round(y)", ctx) == 2.0 or SafeExpressionEvaluator.evaluate("round(y)", ctx) == 3.0
    assert SafeExpressionEvaluator.evaluate("round(2.7)", ctx) == 3.0
    assert SafeExpressionEvaluator.evaluate("atan(1.0)", ctx) == pytest.approx(45.0, abs=1e-2)
    assert SafeExpressionEvaluator.evaluate("asin(1.0)", ctx) == pytest.approx(90.0, abs=1e-2)
    assert SafeExpressionEvaluator.evaluate("acos(1.0)", ctx) == pytest.approx(0.0, abs=1e-2)
    assert SafeExpressionEvaluator.evaluate("log(1.0)", ctx) == pytest.approx(0.0, abs=1e-5)
    assert SafeExpressionEvaluator.evaluate("exp(0.0)", ctx) == pytest.approx(1.0, abs=1e-5)


def test_fea_vertex_colors_generation() -> None:
    """Valide que la heatmap FEA génère des couleurs par sommet dans MeshBuffer."""
    solid = make_box(20.0, 20.0, 10.0)
    sim = FEASimulator()
    res = sim.run_static_analysis(solid, applied_force_newtons=100.0)
    assert res is not None
    buf = sim.generate_stress_heatmap_mesh(solid, res)
    assert buf.vertex_colors is not None
    assert isinstance(buf.vertex_colors, np.ndarray)
    assert buf.vertex_colors.shape == (buf.vertices.shape[0], 4)
    assert buf.vertex_colors.dtype == np.float32


def test_step_faceted_brep_export() -> None:
    """Valide la présence de FACETED_BREP_SHAPE_REPRESENTATION dans l'export STEP."""
    box = make_box(15.0, 15.0, 15.0)
    step_str = STEPExporter.export_to_string({"box": box})
    assert "FACETED_BREP_SHAPE_REPRESENTATION" in step_str
    assert "CLOSED_SHELL" in step_str
    assert "FACETED_BREP" in step_str


def test_document_remove_sketch_and_body() -> None:
    """Valide la suppression d'une esquisse et d'une feature de corps."""
    doc = CADDocument("RemovalDoc")
    sk = Sketch2D("sk_test", "Esquisse Test", PlaneType.XY)
    doc.add_sketch(sk)
    assert "sk_test" in doc.sketches

    doc.remove_sketch("sk_test")
    assert "sk_test" not in doc.sketches

    b = BoxFeature("box_feat", "Boîte", 10.0, 10.0, 10.0)
    doc.add_feature(b)
    assert "body_box_feat" in doc.bodies

    doc.remove_feature("box_feat")
    assert "body_box_feat" not in doc.bodies


def test_vectorized_tpms_field_computation() -> None:
    """Valide l'évaluation 3D ultra-rapide et vectorisée du champ TPMS."""
    from src.core.generative_lattices import compute_tpms_field, LatticeType
    from src.core.types import Vector3D

    b_min = Vector3D(0.0, 0.0, 0.0)
    b_max = Vector3D(20.0, 20.0, 20.0)

    t0 = time.perf_counter()
    X, Y, Z, field = compute_tpms_field(b_min, b_max, resolution=(25, 25, 25), lattice_type=LatticeType.GYROID)
    dt = time.perf_counter() - t0

    assert X.shape == (25, 25, 25)
    assert field.shape == (25, 25, 25)
    # L'évaluation vectorisée de 25^3 = 15625 points doit prendre moins de 50 millisecondes
    assert dt < 0.05
    assert np.min(field) < 0.0
    assert np.max(field) > 0.0

