"""
Tests unitaires pour les fonctionnalités avancées inspirées de FreeCAD :
- ExtrudeFeature (Pad symétrique, angle de dépouille / draft, torsion hélicoïdale)
- HelixFeature (Hélice additive pour ressorts et soustractive pour filets / vis)
- RibFeature (Nervures et goussets de renfort structurel)
- TechDraw LeaderLine (Lignes de repère ISO 128 avec flèches et paliers d'annotation)
- Sérialisation et reconstruction géométrique complète
"""

import os
import tempfile
import pytest
import numpy as np

from src.core.types import Point2D, PlaneType, BooleanOperation, FeatureStatus
from src.core.geometry import Solid, make_box, make_cylinder, extrude_polygon
from src.core.sketch import Sketch2D
from src.core.feature import ExtrudeFeature, CylinderFeature, BoxFeature
from src.core.operations_advanced import HelixFeature, RibFeature
from src.core.document import CADDocument
from src.core.serializer import ProjectSerializer
from src.drawing.drawing_generator import (
    TechnicalDrawingGenerator, TechnicalSheet, LeaderLine, DrawingLine2D
)
from src.drawing.svg_exporter import SVGDrawingExporter


class TestFreeCADPadEnhancements:
    """Tests pour l'extrusion avancée FreeCAD Pad (symétrie, dépouille, torsion)."""

    def test_extrude_symmetric(self) -> None:
        """Vérifie l'extrusion symétrique de part et d'autre du plan d'esquisse."""
        pts = [Point2D(0.0, 0.0), Point2D(20.0, 0.0), Point2D(20.0, 10.0), Point2D(0.0, 10.0)]
        solid = extrude_polygon(pts, 40.0, plane=PlaneType.XY, symmetric=True)
        bbox = solid.bounding_box()
        assert bbox[0].x == pytest.approx(0.0, abs=1e-2)
        assert bbox[0].y == pytest.approx(0.0, abs=1e-2)
        assert bbox[0].z == pytest.approx(-20.0, abs=1e-2)
        assert bbox[1].x == pytest.approx(20.0, abs=1e-2)
        assert bbox[1].y == pytest.approx(10.0, abs=1e-2)
        assert bbox[1].z == pytest.approx(20.0, abs=1e-2)
        assert solid.volume() == pytest.approx(20.0 * 10.0 * 40.0, rel=1e-2)

    def test_extrude_taper_draft(self) -> None:
        """Vérifie l'extrusion avec angle de dépouille (draft / cône)."""
        pts = [Point2D(-10.0, -10.0), Point2D(10.0, -10.0), Point2D(10.0, 10.0), Point2D(-10.0, 10.0)]
        # Dépouille négative (rétrécit vers le haut)
        solid_tapered = extrude_polygon(pts, 30.0, plane=PlaneType.XY, taper_angle=-5.0)
        solid_straight = extrude_polygon(pts, 30.0, plane=PlaneType.XY, taper_angle=0.0)
        assert solid_tapered.volume() < solid_straight.volume()
        assert solid_tapered.is_manifold()

    def test_extrude_feature_parametric(self) -> None:
        """Vérifie le recalcul de ExtrudeFeature avec les options symétrique et dépouille."""
        doc = CADDocument("TestDoc")
        sk = Sketch2D("sk_base", "BaseSketch", plane=PlaneType.XY)
        sk.add_polygon([Point2D(-15.0, -15.0), Point2D(15.0, -15.0), Point2D(15.0, 15.0), Point2D(-15.0, 15.0)])
        doc.add_sketch(sk)

        pad = ExtrudeFeature(
            "feat_pad", "PadSymmetric", sketch_id="sk_base",
            distance=50.0, symmetric=True, taper_angle=-3.0, twist_degrees=15.0
        )
        doc.add_feature(pad)
        doc.rebuild()

        assert "body_feat_pad" in doc.bodies
        pad_solid = doc.bodies["body_feat_pad"]
        assert pad_solid.is_manifold()
        assert pad_solid.volume() > 0.0


class TestFreeCADHelixFeature:
    """Tests pour l'hélice paramétrique 3D (ressorts hélicoïdaux et taraudages/filets)."""

    def test_additive_helix_spring(self) -> None:
        """Vérifie la génération d'un ressort hélicoïdal volumique étanche."""
        helix = HelixFeature(
            feature_id="spring_1",
            name="Spring",
            pitch=8.0,
            height=32.0,
            radius=12.0,
            wire_radius=1.5,
            axis="Z",
            is_subtractive=False
        )
        bodies = helix.evaluate({}, {})
        assert "body_spring_1" in bodies
        solid = bodies["body_spring_1"]
        assert solid.is_manifold()
        assert solid.volume() > 1000.0

    def test_subtractive_helix_thread(self) -> None:
        """Vérifie l'usinage soustractif d'une rainure hélicoïdale (filet de vis)."""
        doc = CADDocument("ScrewDoc")
        cyl = CylinderFeature("cyl_rod", "Rod", radius=10.0, height=40.0)
        doc.add_feature(cyl)

        # Hélice soustractive coupant le cylindre
        helix_cut = HelixFeature(
            feature_id="thread_cut",
            name="Thread",
            pitch=6.0,
            height=30.0,
            radius=9.0,
            wire_radius=1.5,
            is_subtractive=True,
            target_body_id="body_cyl_rod"
        )
        doc.add_feature(helix_cut)
        doc.rebuild()

        assert "body_cyl_rod" in doc.bodies
        cut_rod = doc.bodies["body_cyl_rod"]
        raw_rod_vol = np.pi * (10.0 ** 2) * 40.0
        assert cut_rod.volume() < raw_rod_vol
        assert cut_rod.is_manifold()

    def test_conical_and_left_handed_helix(self) -> None:
        """Vérifie une hélice conique et à pas gauche."""
        helix = HelixFeature(
            feature_id="cone_helix",
            pitch=10.0,
            height=30.0,
            radius=15.0,
            wire_radius=1.2,
            cone_angle=10.0,
            is_left_handed=True,
            axis="Y"
        )
        bodies = helix.evaluate({}, {})
        assert "body_cone_helix" in bodies
        solid = bodies["body_cone_helix"]
        assert solid.is_manifold()
        assert solid.volume() > 500.0


class TestFreeCADRibFeature:
    """Tests pour la nervure de renfort structurel (PartDesign Rib / Gusset)."""

    def test_rib_reinforcement(self) -> None:
        """Vérifie l'extrusion symétrique et la fusion d'un gousset de renfort."""
        doc = CADDocument("BracketDoc")
        # Base plate
        base = BoxFeature("base_feat", "Base", width=60.0, height=60.0, depth=10.0)
        doc.add_feature(base)

        # Esquisse du profil triangulaire de nervure
        sk = Sketch2D("sk_rib", "RibSketch", plane=PlaneType.XZ, offset_distance=30.0)
        sk.add_polygon([Point2D(10.0, 10.0), Point2D(40.0, 10.0), Point2D(10.0, 40.0)])
        doc.add_sketch(sk)

        rib = RibFeature(
            feature_id="rib_1",
            name="GussetRib",
            sketch_id="sk_rib",
            thickness=4.0,
            symmetric=True,
            draft_angle=1.0,
            target_body_id="body_base_feat"
        )
        doc.add_feature(rib)
        doc.rebuild()

        assert "body_base_feat" in doc.bodies
        reinforced = doc.bodies["body_base_feat"]
        assert reinforced.volume() > (60.0 * 60.0 * 10.0)
        assert reinforced.is_manifold()


class TestTechDrawLeaderAnnotations:
    """Tests pour les annotations et lignes de repère ISO 128 (TechDraw LeaderLine)."""

    def test_leader_annotation_generation(self) -> None:
        """Vérifie la création d'une ligne de repère avec flèche et palier."""
        gen = TechnicalDrawingGenerator()
        sheet = TechnicalSheet(width_mm=420.0, height_mm=297.0)

        leader = gen.add_leader_annotation(
            x_target=100.0,
            y_target=150.0,
            x_text=140.0,
            y_text=180.0,
            text="Ø8.5 H7 Perçage + Taraudage M10",
            arrow_size=3.0,
            landing_length=10.0,
            sheet=sheet
        )

        assert isinstance(leader, LeaderLine)
        assert leader.text == "Ø8.5 H7 Perçage + Taraudage M10"
        assert len(sheet.leaders) == 1
        assert len(sheet.lines) >= 4  # Oblique + palier + 2 branches de flèche
        assert len(sheet.dimensions) == 1
        assert sheet.dimensions[0].text == "Ø8.5 H7 Perçage + Taraudage M10"

    def test_svg_export_with_leaders_and_styles(self) -> None:
        """Vérifie l'export SVG intégrant les lignes de repère, traits d'axe et hachures."""
        gen = TechnicalDrawingGenerator()
        sheet = TechnicalSheet()
        gen.add_centerline_cross(100.0, 100.0, radius=20.0, sheet=sheet)
        gen.add_leader_annotation(100.0, 120.0, 130.0, 140.0, "Ø40 H7", sheet=sheet)

        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = os.path.join(tmpdir, "test_plan.svg")
            svg_content = SVGDrawingExporter.export_svg(sheet, svg_path)
            assert os.path.exists(svg_path)
            assert "Ø40 H7" in svg_content
            assert "center-line" in svg_content
            assert "dim-line" in svg_content


class TestPersistenceOfNewFeatures:
    """Tests de sérialisation et restauration du document complet."""

    def test_save_and_load_helix_rib_pad(self) -> None:
        """Vérifie que les nouvelles features sont persistées et rechargées à l'identique."""
        doc = CADDocument("FullProject")
        sk = Sketch2D("sk_profile", "ProfileSketch", plane=PlaneType.XY)
        sk.add_polygon([Point2D(0.0, 0.0), Point2D(30.0, 0.0), Point2D(30.0, 20.0), Point2D(0.0, 20.0)])
        doc.add_sketch(sk)

        pad = ExtrudeFeature(
            "pad_1", "PadBase", sketch_id="sk_profile",
            distance=25.0, symmetric=True, taper_angle=-2.0, twist_degrees=5.0
        )
        doc.add_feature(pad)

        helix = HelixFeature(
            "helix_1", "ScrewSpring",
            pitch=10.0, height=30.0, radius=12.0, wire_radius=1.5
        )
        doc.add_feature(helix)

        sk_rib = Sketch2D("sk_rib", "RibSketch", plane=PlaneType.XZ)
        sk_rib.add_polygon([Point2D(5.0, 5.0), Point2D(25.0, 5.0), Point2D(5.0, 20.0)])
        doc.add_sketch(sk_rib)
        rib = RibFeature("rib_1", "Reinforcement", sketch_id="sk_rib", thickness=3.0, target_body_id="body_pad_1")
        doc.add_feature(rib)

        doc.rebuild()
        assert len(doc.bodies) >= 2

        with tempfile.TemporaryDirectory() as tmpdir:
            proj_path = os.path.join(tmpdir, "test_project.cadproj")
            saved = ProjectSerializer.save_project(doc, proj_path)
            assert saved is True
            assert os.path.exists(proj_path)

            loaded_doc = ProjectSerializer.load_project(proj_path)
            assert loaded_doc is not None
            assert len(loaded_doc.features) == 3
            assert len(loaded_doc.sketches) == 2
            assert len(loaded_doc.bodies) >= 2

            # Vérifier les paramètres du pad rechargé
            loaded_pad = loaded_doc.features[0]
            assert isinstance(loaded_pad, ExtrudeFeature)
            assert loaded_pad.symmetric is True
            assert loaded_pad.taper_angle == pytest.approx(-2.0)
            assert loaded_pad.twist_degrees == pytest.approx(5.0)

            # Vérifier l'hélice rechargée
            loaded_helix = loaded_doc.features[1]
            assert isinstance(loaded_helix, HelixFeature)
            assert loaded_helix.pitch == pytest.approx(10.0)
            assert loaded_helix.wire_radius == pytest.approx(1.5)

            # Vérifier la nervure rechargée
            loaded_rib = loaded_doc.features[2]
            assert isinstance(loaded_rib, RibFeature)
            assert loaded_rib.thickness == pytest.approx(3.0)
            assert loaded_rib.symmetric is True
