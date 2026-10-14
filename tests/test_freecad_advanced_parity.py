"""
Tests unitaires pour la parité FreeCAD avancée (v2) :
- Courbes B-Spline paramétriques (Sketcher B-Spline via De Boor)
- Courbes de Bézier (Sketcher Bézier via De Casteljau)
- Opération de gorge soustractive par révolution (PartDesign Groove)
- Chaînage multi-transformations (PartDesign MultiTransform)
- Traits d'axe normalisés ISO 128 et cercles primitifs (TechDraw CenterLines)
- Persistance et restauration de projet (.cadproj)
"""

import os
import tempfile
import pytest
import numpy as np

from src.core.types import Point2D, PlaneType
from src.core.sketch import Sketch2D, SketchBSpline, SketchBezier
from src.core.geometry import make_cylinder, Solid
from src.core.document import CADDocument
from src.core.feature import CylinderFeature, BoxFeature
from src.core.operations_advanced import (
    GrooveFeature, MultiTransformFeature, MultiTransformStep
)
from src.drawing.drawing_generator import TechnicalDrawingGenerator, TechnicalSheet
from src.core.serializer import ProjectSerializer


def test_sketcher_bspline_and_bezier_curves() -> None:
    """Vérifie la génération et l'évaluation de courbes B-Spline et Bézier dans l'esquisseur."""
    sk = Sketch2D("sk_curves", "CurvesSketch")

    # 1. B-Spline ouverte cubique (degré 3) avec 5 points de contrôle
    ctrl_pts = [
        Point2D(0.0, 0.0),
        Point2D(10.0, 20.0),
        Point2D(30.0, -10.0),
        Point2D(50.0, 25.0),
        Point2D(60.0, 0.0)
    ]
    bspline = sk.add_bspline(ctrl_pts, degree=3, closed=False, segments=30)
    assert bspline.degree == 3
    assert bspline.closed is False
    pts_bspline = bspline.get_points()
    assert len(pts_bspline) == 30
    # Une spline clamped démarre exactement au 1er point et finit au dernier point
    assert abs(pts_bspline[0].u - ctrl_pts[0].u) < 1e-3
    assert abs(pts_bspline[0].v - ctrl_pts[0].v) < 1e-3
    assert abs(pts_bspline[-1].u - ctrl_pts[-1].u) < 1e-3
    assert abs(pts_bspline[-1].v - ctrl_pts[-1].v) < 1e-3

    # 2. B-Spline fermée
    closed_ctrl = [
        Point2D(10.0, 10.0),
        Point2D(40.0, 15.0),
        Point2D(35.0, 40.0),
        Point2D(15.0, 35.0)
    ]
    closed_bspline = sk.add_bspline(closed_ctrl, degree=3, closed=True, segments=20)
    pts_closed = closed_bspline.get_points()
    assert len(pts_closed) > 15
    # Le premier et dernier point d'un contour fermé coïncident
    assert abs(pts_closed[0].u - pts_closed[-1].u) < 1e-3
    assert abs(pts_closed[0].v - pts_closed[-1].v) < 1e-3

    # 3. Courbe de Bézier
    bezier = sk.add_bezier(ctrl_pts, closed=False, segments=25)
    pts_bezier = bezier.get_points()
    assert len(pts_bezier) == 25
    assert abs(pts_bezier[0].u - ctrl_pts[0].u) < 1e-3
    assert abs(pts_bezier[-1].u - ctrl_pts[-1].u) < 1e-3


def test_partdesign_groove_feature() -> None:
    """Vérifie l'usinage d'une gorge soustractive par révolution (FreeCAD PartDesign Groove)."""
    doc = CADDocument(name="GrooveDoc")

    # Cylindre initial : rayon 30 mm, hauteur 40 mm
    cyl_feat = CylinderFeature("cyl1", "Shaft", radius=30.0, height=40.0)
    doc.add_feature(cyl_feat)
    assert len(doc.bodies) == 1
    initial_volume = doc.bodies["body_cyl1"].volume()

    # Esquisse pour la gorge : rectangle 5x5 situé à rayon U in [20, 25] et Z in [15, 20]
    sk_groove = Sketch2D("sk_groove", "GrooveProfile", plane=PlaneType.XY)
    sk_groove.add_rectangle(Point2D(20.0, 15.0), width=5.0, height=5.0)
    doc.sketches["sk_groove"] = sk_groove

    # Fonction Groove (révolution de 360°)
    groove_feat = GrooveFeature("groove1", "RetainingGroove", sketch_id="sk_groove", angle_deg=360.0, target_body_id="body_cyl1")
    doc.add_feature(groove_feat)

    vol_after_groove = doc.bodies["body_cyl1"].volume()
    assert vol_after_groove < initial_volume
    # Le volume de la gorge circulaire usinée est environ 2 * pi * R_moyen * Section
    # Section = 25 mm², R_moyen = 22.5 mm => V_groove ~ 2 * pi * 22.5 * 25 ~ 3534 mm³
    diff_volume = initial_volume - vol_after_groove
    assert 3000.0 < diff_volume < 4000.0


def test_partdesign_multitransform_feature() -> None:
    """Vérifie l'enchaînement de transformations multiples (FreeCAD MultiTransform)."""
    doc = CADDocument(name="MultiTransformDoc")

    # Corps source : Petit pavé 10x10x10
    box_feat = BoxFeature("box1", "Cube", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box_feat)
    assert "body_box1" in doc.bodies
    cube_vol = doc.bodies["body_box1"].volume()

    # MultiTransform : Répétition linéaire selon X (3 occurrences espacées de 30) + selon Y (2 occurrences espacées de 40)
    mt_feat = MultiTransformFeature("mt1", "MatrixTransform", source_body_id="body_box1", join_bodies=True)
    mt_feat.add_linear_step(count=3, spacing=30.0, axis="X")
    mt_feat.add_linear_step(count=2, spacing=40.0, axis="Y")
    doc.add_feature(mt_feat)

    assert "body_mt1" in doc.bodies
    combined_vol = doc.bodies["body_mt1"].volume()
    # 3 * 2 = 6 cubes disjoints
    expected_vol = 6.0 * cube_vol
    assert abs(combined_vol - expected_vol) < 50.0

    # MultiTransform circulaire
    mt_circ = MultiTransformFeature("mt_circ", "PolarMulti", source_body_id="body_box1", join_bodies=False)
    mt_circ.add_circular_step(count=4, total_angle=360.0, axis="Z")
    res_bodies = mt_circ.evaluate(doc.bodies, doc.sketches)
    assert len([k for k in res_bodies if k.startswith("body_mt_circ_")]) == 4


def test_techdraw_iso_centerlines() -> None:
    """Vérifie le tracé des traits d'axe et cercles primitifs (TechDraw CenterLines ISO 128)."""
    gen = TechnicalDrawingGenerator()
    sheet = TechnicalSheet()

    # Croix d'axe individuelle
    cross_lines = gen.add_centerline_cross(100.0, 100.0, radius=15.0, extension=3.0, sheet=sheet)
    assert len(cross_lines) == 2
    assert all(l.is_centerline for l in cross_lines)
    assert cross_lines[0].x1 == 100.0 - 18.0
    assert cross_lines[0].x2 == 100.0 + 18.0

    # Cercle primitif de perçage (Bolt Circle PCD) à 6 trous
    bolt_lines = gen.add_bolt_circle_centerline(200.0, 150.0, pitch_circle_radius=50.0, num_holes=6, hole_radius=4.0, sheet=sheet)
    assert len(bolt_lines) > 20
    assert all(l.is_centerline for l in bolt_lines)
    assert len(sheet.lines) == len(cross_lines) + len(bolt_lines)


def test_serializer_with_advanced_freecad_features() -> None:
    """Vérifie la persistance intégrale de GrooveFeature, MultiTransformFeature et B-Splines."""
    doc = CADDocument(name="AdvancedParityDoc")

    # Esquisse avec B-Spline
    sk = Sketch2D("sk_bspline", "SplineSketch", plane=PlaneType.XY)
    ctrl = [Point2D(0.0, 0.0), Point2D(20.0, 30.0), Point2D(40.0, 0.0)]
    sk.add_bspline(ctrl, degree=2, closed=False)
    doc.sketches[sk.sketch_id] = sk

    # Cylindre
    cyl = CylinderFeature("cyl1", "BaseCyl", radius=40.0, height=50.0)
    doc.add_feature(cyl)

    # Groove
    sk_cut = Sketch2D("sk_cut", "GrooveCut")
    sk_cut.add_rectangle(Point2D(30.0, 20.0), 5.0, 5.0)
    doc.sketches[sk_cut.sketch_id] = sk_cut
    groove = GrooveFeature("groove1", "CutGroove", sketch_id="sk_cut", target_body_id="body_cyl1")
    doc.add_feature(groove)

    # MultiTransform
    mt = MultiTransformFeature("mt1", "TransformedPillar", source_body_id="body_cyl1")
    mt.add_linear_step(count=2, spacing=100.0, axis="X")
    mt.add_mirror_step(mirror_plane=PlaneType.YZ)
    doc.add_feature(mt)

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "advanced_freecad_parity.cadproj")
        save_ok = ProjectSerializer.save_project(doc, path)
        assert save_ok is True
        assert os.path.exists(path)

        loaded = ProjectSerializer.load_project(path)
        assert loaded is not None
        assert "sk_bspline" in loaded.sketches
        loaded_ent = loaded.sketches["sk_bspline"].entities[0]
        assert loaded_ent.entity_type.value == "bspline"

        feat_names = [f.__class__.__name__ for f in loaded.features]
        assert "CylinderFeature" in feat_names
        assert "GrooveFeature" in feat_names
        assert "MultiTransformFeature" in feat_names
