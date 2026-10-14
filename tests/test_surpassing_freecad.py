"""
Tests unitaires pour les fonctionnalités avancées surpassant FreeCAD :
- Découpe et partitionnement par plan 3D (Solid.split_by_plane, SplitFeature)
- Lissage et Balayage soustractifs (SubtractiveLoftFeature, SubtractiveSweepFeature)
- Métrologie & Tenseur d'inertie 3D exact avec axes principaux
- TechDraw ISO 1101 (GD&T Control Frame), ISO 1302 (État de surface) et Vues de détail 2:1
- Sérialisation et persistance complète .cadproj
"""

import os
import tempfile
import pytest
import numpy as np

from src.core.types import Point2D, PlaneType, BooleanOperation
from src.core.geometry import Solid, make_box, make_cylinder
from src.core.sketch import Sketch2D
from src.core.feature import BoxFeature, CylinderFeature
from src.core.operations_advanced import (
    SplitFeature, SubtractiveLoftFeature, SubtractiveSweepFeature
)
from src.core.document import CADDocument
from src.core.serializer import ProjectSerializer
from src.core.inspector import (
    compute_inertia_tensor, generate_inspection_report, InertiaTensor
)
from src.drawing.drawing_generator import (
    TechnicalDrawingGenerator, TechnicalSheet, GDTFrame, SurfaceFinishSymbol, DrawingLine2D
)


class Test3DSplitAndTrim:
    """Tests pour le découpage 3D instantané et étanche (FreeCAD Part Slice/Split)."""

    def test_solid_split_by_plane(self) -> None:
        """Vérifie la partition d'un cube en deux demi-espaces étanches."""
        box = make_box(20.0, 20.0, 20.0, center=True, name="Cube")
        pos_solid, neg_solid = box.split_by_plane(normal=(0.0, 0.0, 1.0), origin_offset=0.0)

        assert pos_solid.is_manifold()
        assert neg_solid.is_manifold()
        assert pos_solid.volume() == pytest.approx(4000.0, rel=1e-2)
        assert neg_solid.volume() == pytest.approx(4000.0, rel=1e-2)
        assert pos_solid.volume() + neg_solid.volume() == pytest.approx(box.volume(), rel=1e-3)

    def test_solid_trim_by_plane(self) -> None:
        """Vérifie le rognage d'un solide par un plan quelconque."""
        cyl = make_cylinder(radius=10.0, height=30.0, name="Cyl")
        # Couper à mi-hauteur Z = 15.0
        trimmed = cyl.trim_by_plane(normal=(0.0, 0.0, 1.0), origin_offset=15.0)
        assert trimmed.is_manifold()
        assert trimmed.volume() == pytest.approx(cyl.volume() * 0.5, rel=1e-2)

    def test_split_feature_parametric(self) -> None:
        """Vérifie l'évaluation de SplitFeature dans l'arbre d'historique."""
        doc = CADDocument("SplitDoc")
        box_feat = BoxFeature("b1", "BaseBox", width=40.0, height=40.0, depth=40.0, center=True)
        doc.add_feature(box_feat)

        split_feat = SplitFeature(
            "split_1", "CutPlane",
            target_body_id="body_b1",
            plane=PlaneType.XY,
            plane_offset=5.0,
            keep_side="both"
        )
        doc.add_feature(split_feat)
        doc.rebuild()

        assert "body_b1" in doc.bodies
        assert "body_b1_split_2" in doc.bodies
        assert doc.bodies["body_b1"].is_manifold()
        assert doc.bodies["body_b1_split_2"].is_manifold()


class TestSubtractiveLoftAndSweep:
    """Tests pour le lissage et le balayage soustractifs (FreeCAD SubtractiveLoft & Pipe)."""

    def test_subtractive_loft_carving(self) -> None:
        """Vérifie l'évidement d'une cavité lissée à l'intérieur d'un bloc."""
        doc = CADDocument("LoftDoc")
        doc.add_feature(BoxFeature("base_block", "Block", width=60.0, height=60.0, depth=60.0))

        # Esquisse basse
        sk1 = Sketch2D("sk1", "Bottom", plane=PlaneType.XY)
        sk1.add_polygon([Point2D(15.0, 15.0), Point2D(45.0, 15.0), Point2D(45.0, 45.0), Point2D(15.0, 45.0)])
        doc.add_sketch(sk1)

        # Esquisse haute
        sk2 = Sketch2D("sk2", "Top", plane=PlaneType.XY)
        sk2.add_polygon([Point2D(20.0, 20.0), Point2D(40.0, 20.0), Point2D(40.0, 40.0), Point2D(20.0, 40.0)])
        doc.add_sketch(sk2)

        sub_loft = SubtractiveLoftFeature(
            feature_id="sub_loft_1",
            name="CavityLoft",
            start_sketch_id="sk1",
            end_sketch_id="sk2",
            height_offset=50.0,
            target_body_id="body_base_block"
        )
        doc.add_feature(sub_loft)
        doc.rebuild()

        assert "body_base_block" in doc.bodies
        carved = doc.bodies["body_base_block"]
        raw_vol = 60.0 ** 3
        assert carved.volume() < raw_vol
        assert carved.is_manifold()

    def test_subtractive_sweep_tunnel(self) -> None:
        """Vérifie le creusement d'un conduit courbe soustractif."""
        doc = CADDocument("SweepDoc")
        doc.add_feature(BoxFeature("box_block", "Block", width=80.0, height=80.0, depth=80.0))

        sk_prof = Sketch2D("sk_prof", "Profile", plane=PlaneType.XY)
        sk_prof.add_polygon([Point2D(-5.0, -5.0), Point2D(5.0, -5.0), Point2D(5.0, 5.0), Point2D(-5.0, 5.0)])
        doc.add_sketch(sk_prof)

        sub_sweep = SubtractiveSweepFeature(
            feature_id="sub_swp_1",
            name="CurvedTunnel",
            profile_sketch_id="sk_prof",
            trajectory_type="arc",
            radius=35.0,
            height=40.0,
            target_body_id="body_box_block"
        )
        doc.add_feature(sub_sweep)
        doc.rebuild()

        assert "body_box_block" in doc.bodies
        tunnel_solid = doc.bodies["body_box_block"]
        assert tunnel_solid.volume() < (80.0 ** 3)
        assert tunnel_solid.is_manifold()


class TestMetrologyAndInertiaTensor:
    """Tests pour le calcul rigoureux du tenseur d'inertie 3x3 et axes principaux."""

    def test_box_inertia_tensor_exactness(self) -> None:
        """Vérifie le tenseur d'inertie pour un parallélépipède 20x40x60 centré."""
        # Dim: dx=20, dy=40, dz=60, density=1.0 g/cm3 = 1e-3 g/mm3
        box = make_box(20.0, 40.0, 60.0, center=True, name="TestBox")
        V = 20.0 * 40.0 * 60.0  # 48000 mm3
        density_g_cm3 = 2.0
        M = V * (density_g_cm3 * 1e-3)  # 96 grammes

        tensor = compute_inertia_tensor(box, density_g_cm3=density_g_cm3)
        assert isinstance(tensor, InertiaTensor)

        # Ixx théorique = M * (dy^2 + dz^2) / 12 = 96 * (1600 + 3600) / 12 = 41600 g.mm2
        exp_ixx = M * (40.0**2 + 60.0**2) / 12.0
        exp_iyy = M * (20.0**2 + 60.0**2) / 12.0
        exp_izz = M * (20.0**2 + 40.0**2) / 12.0

        assert tensor.ixx == pytest.approx(exp_ixx, rel=1e-2)
        assert tensor.iyy == pytest.approx(exp_iyy, rel=1e-2)
        assert tensor.izz == pytest.approx(exp_izz, rel=1e-2)
        assert tensor.ixy == pytest.approx(0.0, abs=1e-2)

        # Moments principaux d'inertie
        assert len(tensor.principal_moments) == 3
        assert tensor.principal_moments[0] <= tensor.principal_moments[1] <= tensor.principal_moments[2]

        # Rayons de giration
        assert tensor.radius_of_gyration[0] == pytest.approx(np.sqrt(exp_ixx / M), rel=1e-2)

    def test_inspection_report_with_inertia(self) -> None:
        """Vérifie que le rapport métrologique complet inclut le tenseur d'inertie."""
        cyl = make_cylinder(radius=15.0, height=50.0)
        report = generate_inspection_report(cyl, material_name="Acier C45", density_g_cm3=7.85)

        assert "inertia" in report
        inertia = report["inertia"]
        assert isinstance(inertia, InertiaTensor)
        assert inertia.izz > 0.0


class TestTechDrawAdvancedFeatures:
    """Tests pour GD&T, symboles de rugosité et vues de détail 2:1."""

    def test_gdt_frame_generation(self) -> None:
        """Vérifie la création d'un cadre de tolérance géométrique ISO 1101."""
        gen = TechnicalDrawingGenerator()
        sheet = TechnicalSheet()

        frame = gen.add_gdt_frame(
            x=50.0, y=80.0,
            characteristic="⏥",
            tolerance_value="0.02",
            datum_primary="A",
            datum_secondary="B",
            sheet=sheet
        )

        assert isinstance(frame, GDTFrame)
        assert len(sheet.gdt_frames) == 1
        assert frame.characteristic == "⏥"
        assert frame.tolerance_value == "0.02"
        assert len(sheet.lines) >= 6  # Cadre + cloisons verticales
        assert len(sheet.dimensions) >= 4  # Symboles et valeurs

    def test_surface_finish_symbol(self) -> None:
        """Vérifie la création d'un symbole de rugosité ISO 1302."""
        gen = TechnicalDrawingGenerator()
        sheet = TechnicalSheet()

        symbol = gen.add_surface_finish_symbol(
            x=100.0, y=100.0,
            roughness="Ra 0.8",
            machining_required=True,
            sheet=sheet
        )

        assert isinstance(symbol, SurfaceFinishSymbol)
        assert len(sheet.surface_symbols) == 1
        assert symbol.roughness == "Ra 0.8"
        assert sum(1 for d in sheet.dimensions if d.text == "Ra 0.8") > 0

    def test_detail_view_zoom_2_1(self) -> None:
        """Vérifie l'agrandissement x2 d'une zone circulaire en vue de détail."""
        gen = TechnicalDrawingGenerator()
        sheet = TechnicalSheet()

        # Ajouter des lignes dans la zone source (100, 100)
        l1 = DrawingLine2D(95.0, 95.0, 105.0, 105.0)
        sheet.lines.append(l1)

        detail_lines = gen.add_detail_view(
            source_center_x=100.0,
            source_center_y=100.0,
            radius=15.0,
            dest_center_x=250.0,
            dest_center_y=150.0,
            scale_factor=2.0,
            label="Détail C",
            sheet=sheet
        )

        assert len(detail_lines) >= 1
        # La longueur de l'élément extrait et zoomé doit être doublée
        orig_len = np.hypot(l1.x2 - l1.x1, l1.y2 - l1.y1)
        det_len = np.hypot(detail_lines[0].x2 - detail_lines[0].x1, detail_lines[0].y2 - detail_lines[0].y1)
        assert det_len == pytest.approx(orig_len * 2.0, rel=1e-2)


class TestPersistenceOfAdvancedSplitAndLoft:
    """Tests de sérialisation et restauration de Split, SubtractiveLoft et SubtractiveSweep."""

    def test_persistence_split_and_subtractive(self) -> None:
        """Vérifie la sauvegarde et le rechargement transparent de SplitFeature."""
        doc = CADDocument("ProjectAdvanced")
        doc.add_feature(BoxFeature("base_box", "Base", width=50.0, height=50.0, depth=50.0))

        split = SplitFeature(
            "split_1", "SplitCut",
            target_body_id="body_base_box",
            plane=PlaneType.XY,
            plane_offset=25.0,
            keep_side="positive"
        )
        doc.add_feature(split)
        doc.rebuild()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "advanced.cadproj")
            saved = ProjectSerializer.save_project(doc, file_path)
            assert saved is True

            loaded = ProjectSerializer.load_project(file_path)
            assert loaded is not None
            assert len(loaded.features) == 2
            assert isinstance(loaded.features[1], SplitFeature)
            assert loaded.features[1].keep_side == "positive"
            assert "body_base_box" in loaded.bodies
            assert loaded.bodies["body_base_box"].is_manifold()
