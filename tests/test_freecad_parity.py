"""
Tests unitaires pour la parité FreeCAD approfondie :
- Géométrie de construction d'esquisse (Sketcher Construction Geometry)
- Diagnostic des degrés de liberté du solveur (Degrees of Freedom - DoF)
- Fonctionnalité de cavité / poche (PartDesign Pocket)
- Plans de référence paramétriques (PartDesign Datum Plane)
- Vue en coupe avec hachures ISO 128 (TechDraw Section Hatching)
- Sérialisation et restauration complète du projet (.cadproj)
"""

import os
import tempfile
import pytest
import numpy as np

from src.core.types import Point2D, PlaneType, BooleanOperation
from src.core.sketch import Sketch2D, SketchLine, SketchRectangle, SketchCircle
from src.solver.constraints_2d import ConstraintSolver2D
from src.core.geometry import make_box, extrude_polygon
from src.core.document import CADDocument
from src.core.feature import BoxFeature, ExtrudeFeature
from src.core.operations_advanced import PocketFeature, DatumPlaneFeature
from src.drawing.drawing_generator import TechnicalDrawingGenerator, DrawingLine2D
from src.core.serializer import ProjectSerializer


def test_sketch_construction_geometry() -> None:
    """Vérifie que la géométrie de construction est correctement identifiée et exclue des profils 3D."""
    sketch = Sketch2D("sk1", "SketchWithConstruction", plane=PlaneType.XY, offset_distance=15.0)

    # Ligne de construction (axe de symétrie / référence)
    axis_line = sketch.add_line(Point2D(0.0, -50.0), Point2D(0.0, 50.0), is_construction=True)
    assert axis_line.is_construction is True

    # Cercle de construction (cercle primitif de perçage style FreeCAD)
    bolt_circle = sketch.add_circle(Point2D(0.0, 0.0), radius=25.0, is_construction=True)
    assert bolt_circle.is_construction is True

    # Rectangle solide réel
    rect = sketch.add_rectangle(Point2D(-20.0, -20.0), width=40.0, height=40.0, is_construction=False)
    assert rect.is_construction is False

    solids = sketch.get_solid_entities()
    constructions = sketch.get_construction_entities()

    assert len(solids) == 1
    assert solids[0].entity_id == rect.entity_id
    assert len(constructions) == 2

    # Le profil primaire ne doit pas prendre l'axe ni le cercle de construction
    profile = sketch.get_primary_profile()
    assert profile is not None
    assert len(profile) == 4  # Le rectangle solide à 4 sommets

    # Vérification de la projection 3D avec décalage de plan
    pt_3d = sketch.to_3d_coordinates(Point2D(10.0, 20.0))
    assert pt_3d.x == 10.0
    assert pt_3d.y == 20.0
    assert pt_3d.z == 15.0


def test_solver_degrees_of_freedom() -> None:
    """Vérifie le calcul diagnostique des degrés de liberté (DoF) du solveur."""
    solver = ConstraintSolver2D()

    # 1. Esquisse vide
    dof, msg = solver.calculate_degrees_of_freedom()
    assert dof == 0

    # 2. 2 points libres (4 variables, 0 contraintes => 4 DoF)
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))
    dof, msg = solver.calculate_degrees_of_freedom()
    assert dof == 4
    assert "4 degrés de liberté" in msg

    # 3. Ancrer p0 à (0, 0) => supprime 2 DoF (reste 2 DoF)
    solver.add_fixed(p0, 0.0, 0.0)
    dof, msg = solver.calculate_degrees_of_freedom()
    assert dof == 2

    # 4. Rendre le segment horizontal => supprime 1 DoF (reste 1 DoF)
    solver.add_horizontal(p0, p1)
    dof, msg = solver.calculate_degrees_of_freedom()
    assert dof == 1

    # 5. Fixer la distance à 50.0 => système entièrement contraint (0 DoF)
    solver.add_distance(p0, p1, 50.0)
    dof, msg = solver.calculate_degrees_of_freedom()
    assert dof == 0
    assert "Entièrement contrainte" in msg


def test_partdesign_pocket_feature() -> None:
    """Vérifie le fonctionnement de PocketFeature (creusement fini et traversant)."""
    doc = CADDocument(name="PocketDoc")

    # Corps de base : Bloc 60x60x40
    base_box = BoxFeature("box1", "BaseBox", width=60.0, height=60.0, depth=40.0)
    doc.add_feature(base_box)
    assert len(doc.bodies) == 1
    initial_volume = doc.bodies["body_box1"].volume()

    # Esquisse pour la poche sur le dessus du bloc (Z = 40.0)
    pocket_sk = Sketch2D("sk_pocket", "PocketSketch", plane=PlaneType.XY, offset_distance=40.0)
    pocket_sk.add_rectangle(Point2D(10.0, 10.0), width=20.0, height=20.0)
    doc.sketches["sk_pocket"] = pocket_sk

    # Poche avec profondeur de 15 mm
    pocket_feat = PocketFeature(
        "pocket1",
        name="Pocket15mm",
        sketch_id="sk_pocket",
        depth=15.0,
        through_all=False,
        target_body_id="body_box1"
    )
    doc.add_feature(pocket_feat)

    vol_after_pocket = doc.bodies["body_box1"].volume()
    expected_cavity = 20.0 * 20.0 * 15.0
    assert vol_after_pocket < initial_volume
    assert abs((initial_volume - vol_after_pocket) - expected_cavity) < 50.0  # Tolérance maillage

    # Poche traversante (through_all)
    pocket_through = PocketFeature(
        "pocket_thru",
        name="PocketThrough",
        sketch_id="sk_pocket",
        through_all=True,
        target_body_id="body_box1"
    )
    # Recalcul avec traversant
    updated_bodies = pocket_through.evaluate(doc.bodies, doc.sketches)
    vol_through = updated_bodies["body_box1"].volume()
    assert vol_through < vol_after_pocket


def test_datum_plane_and_elevated_sketch() -> None:
    """Vérifie les plans de référence (DatumPlaneFeature) et l'extrusion d'esquisse surélevée."""
    datum = DatumPlaneFeature("dp1", "OffsetPlaneXY", base_plane=PlaneType.XY, offset_distance=50.0)
    assert datum.parameters["offset_distance"] == 50.0

    sketch = Sketch2D("sk_elevated", "ElevatedSketch")
    datum.attach_to_sketch(sketch)
    assert sketch.plane == PlaneType.XY
    assert sketch.offset_distance == 50.0

    # Profil carré 20x20
    rect = sketch.add_rectangle(Point2D(0.0, 0.0), 20.0, 20.0)
    profile = sketch.get_primary_profile()
    assert profile is not None

    # Extrusion avec décalage de plan
    solid = extrude_polygon(profile, height=10.0, plane=sketch.plane, plane_offset=sketch.offset_distance)
    min_b, max_b = solid.bounding_box()
    # Le solide doit démarrer à Z = 50 et finir à Z = 60
    assert abs(min_b.z - 50.0) < 1e-3
    assert abs(max_b.z - 60.0) < 1e-3


def test_techdraw_iso_section_hatching() -> None:
    """Vérifie la génération de plan de coupe avec hachures ISO 128 à 45°."""
    # Bloc 40x40x40
    solid = make_box(40.0, 40.0, 40.0)
    gen = TechnicalDrawingGenerator()
    sheet = gen.generate_section_view(solid, cut_height=20.0, hatch_spacing=4.0)

    assert len(sheet.lines) > 0
    # Vérifier la présence de lignes de hachure
    hatch_lines = [l for l in sheet.lines if l.is_hatch]
    assert len(hatch_lines) > 5

    # Vérifier l'inclinaison des hachures (pente proche de +1 ou -1 pour 45°)
    for hl in hatch_lines:
        dx = hl.x2 - hl.x1
        dy = hl.y2 - hl.y1
        if abs(dx) > 1e-4:
            slope = dy / dx
            assert abs(slope - 1.0) < 1e-2  # Pente exacte à 45 deg (dy = dx)


def test_serializer_with_freecad_parity() -> None:
    """Vérifie la sauvegarde et restauration d'un projet incluant les features FreeCAD."""
    doc = CADDocument(name="FreeCADParityDoc")

    # Esquisse avec géométrie de construction et offset
    sk = Sketch2D("sk1", "BaseSketch", plane=PlaneType.XY, offset_distance=12.5)
    sk.add_line(Point2D(0.0, 0.0), Point2D(50.0, 0.0), is_construction=True)
    sk.add_rectangle(Point2D(-25.0, -25.0), width=50.0, height=50.0, is_construction=False)
    doc.sketches[sk.sketch_id] = sk

    # Base Box
    box_feat = BoxFeature("box1", "BaseSolid", width=80.0, height=80.0, depth=30.0)
    doc.add_feature(box_feat)

    # Pocket Feature
    pocket = PocketFeature(
        "pocket1",
        "Cavity",
        sketch_id="sk1",
        depth=10.0,
        through_all=False,
        target_body_id="body_box1"
    )
    doc.add_feature(pocket)

    # Datum Plane Feature
    datum = DatumPlaneFeature("datum1", "TopRefPlane", base_plane=PlaneType.XY, offset_distance=30.0)
    doc.add_feature(datum)

    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = os.path.join(tmp_dir, "freecad_parity_test.cadproj")
        save_ok = ProjectSerializer.save_project(doc, file_path)
        assert save_ok is True
        assert os.path.exists(file_path)

        loaded_doc = ProjectSerializer.load_project(file_path)
        assert loaded_doc is not None
        assert "sk1" in loaded_doc.sketches
        loaded_sk = loaded_doc.sketches["sk1"]
        assert loaded_sk.offset_distance == 12.5
        assert len(loaded_sk.entities) == 2

        # Vérifier types de features restaurées
        feature_classes = [f.__class__.__name__ for f in loaded_doc.features]
        assert "BoxFeature" in feature_classes
        assert "PocketFeature" in feature_classes
        assert "DatumPlaneFeature" in feature_classes


def test_sketch_entities_and_projections_coverage() -> None:
    """Couvre les entités d'esquisse et les projections multi-plans avec offset."""
    sk_xz = Sketch2D("sk_xz", "SketchXZ", plane=PlaneType.XZ, offset_distance=25.0)
    pt3d_xz = sk_xz.to_3d_coordinates(Point2D(10.0, 30.0))
    assert pt3d_xz.x == 10.0
    assert pt3d_xz.y == 25.0
    assert pt3d_xz.z == 30.0

    sk_yz = Sketch2D("sk_yz", "SketchYZ", plane=PlaneType.YZ, offset_distance=-10.0)
    pt3d_yz = sk_yz.to_3d_coordinates(Point2D(5.0, 15.0))
    assert pt3d_yz.x == -10.0
    assert pt3d_yz.y == 5.0
    assert pt3d_yz.z == 15.0

    # Test Slot, Regular Polygon et Ellipse
    slot = sk_xz.add_slot(Point2D(0.0, 0.0), Point2D(20.0, 0.0), radius=5.0, is_construction=True)
    assert slot.is_construction is True
    assert len(slot.to_profile_points(12)) > 10

    reg_poly = sk_xz.add_regular_polygon(Point2D(0.0, 0.0), radius=15.0, sides=6, is_construction=False)
    assert reg_poly.is_construction is False
    assert len(reg_poly.to_profile_points()) == 6

    ellipse = sk_xz.add_ellipse(Point2D(0.0, 0.0), radius_u=20.0, radius_v=10.0, is_construction=False)
    assert ellipse.is_construction is False
    assert len(ellipse.to_profile_points(24)) == 24

    # Profil primaire doit être le premier solide valide
    prof = sk_xz.get_primary_profile()
    assert prof is not None
    assert len(prof) == 6  # reg_poly


def test_pocket_feature_error_branches() -> None:
    """Vérifie la robustesse de PocketFeature face aux erreurs de configuration."""
    from src.core.types import FeatureStatus

    doc = CADDocument(name="PocketErrorDoc")
    pocket_bad_sk = PocketFeature("p_err1", "BadSketchPocket", sketch_id="non_existent")
    pocket_bad_sk.evaluate(doc.bodies, doc.sketches)
    assert pocket_bad_sk.status == FeatureStatus.ERROR

    # Esquisse sans profil valide
    empty_sk = Sketch2D("sk_empty", "EmptySketch")
    doc.sketches["sk_empty"] = empty_sk
    pocket_empty = PocketFeature("p_err2", "EmptyPocket", sketch_id="sk_empty")
    pocket_empty.evaluate(doc.bodies, doc.sketches)
    assert pocket_empty.status == FeatureStatus.ERROR

    # Corps cible introuvable
    sk_with_rect = Sketch2D("sk_rect", "RectSketch")
    sk_with_rect.add_rectangle(Point2D(0.0, 0.0), 10.0, 10.0)
    doc.sketches["sk_rect"] = sk_with_rect
    pocket_no_target = PocketFeature("p_err3", "NoTargetPocket", sketch_id="sk_rect", target_body_id="phantom_body")
    pocket_no_target.evaluate(doc.bodies, doc.sketches)
    assert pocket_no_target.status == FeatureStatus.ERROR

