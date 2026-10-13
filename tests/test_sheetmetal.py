"""
Tests unitaires pour le moteur de tôlerie industrielle (Sheet Metal) et l'export DXF.
Vérifie la théorie du pliage (Facteur K, Bend Allowance, Bend Deduction),
la génération du solide plié 3D, du flan 2D déplié et de l'export laser.
"""

import os
import tempfile
import pytest

from src.core.document import CADDocument
from src.core.serializer import ProjectSerializer
from src.sheetmetal.sheet_metal import (
    SheetMetalRule, BendInfo, FlatPattern, SheetMetalPart, SheetMetalFeature
)
from src.sheetmetal.dxf_exporter import DXFExporter


def test_sheet_metal_rule_and_calculations() -> None:
    """Vérifie les calculs normalisés du développement de pli et déduction au pli."""
    rule = SheetMetalRule(thickness_mm=2.0, bend_radius_mm=2.0, k_factor=0.44)
    part = SheetMetalPart(base_width=50.0, base_length=100.0, rule=rule)

    # Pour un pli à 90 degrés :
    # BA = (pi / 180) * 90 * (R + K * t) = (pi / 2) * (2.0 + 0.44 * 2.0) = 1.570796 * 2.88 ≈ 4.5239 mm
    ba = part.calculate_bend_allowance(90.0)
    assert ba == pytest.approx(4.52389, rel=1e-3)

    # Setback = (R + t) * tan(45°) = 4.0 mm
    # BD = 2 * Setback - BA = 8.0 - 4.52389 ≈ 3.4761 mm
    bd = part.calculate_bend_deduction(90.0)
    assert bd == pytest.approx(3.4761, rel=1e-3)


def test_sheet_metal_flange_and_folded_solid() -> None:
    """Vérifie l'ajout de rebord plié et la génération du solide 3D plié."""
    part = SheetMetalPart(base_width=60.0, base_length=80.0)
    bend = part.add_flange(length_mm=25.0, angle_deg=90.0)

    assert len(part.bends) == 1
    assert bend.flange_length_mm == pytest.approx(25.0)
    assert bend.bend_allowance_mm > 0.0
    assert bend.bend_deduction_mm > 0.0

    solid = part.generate_folded_solid()
    assert solid.volume() > 0.0
    mesh = solid.to_mesh_buffer()
    assert not mesh.is_empty()
    assert len(mesh.vertices) > 0


def test_sheet_metal_flat_pattern() -> None:
    """Vérifie le calcul exact du flan déplié à plat pour découpe laser."""
    part = SheetMetalPart(base_width=60.0, base_length=80.0)
    part.add_flange(length_mm=30.0, angle_deg=90.0)

    pattern = part.generate_flat_pattern()
    assert pattern.total_width_mm == pytest.approx(60.0)
    assert pattern.thickness_mm == pytest.approx(2.0)

    # Longueur développée = 80 + (30 - BD)
    expected_len = 80.0 + (30.0 - part.bends[0].bend_deduction_mm)
    assert pattern.total_length_mm == pytest.approx(expected_len, rel=1e-3)
    assert len(pattern.outline_points) == 4
    assert len(pattern.bend_centerlines) == 1


def test_sheet_metal_feature_in_document() -> None:
    """Vérifie l'intégration de SheetMetalFeature dans le cycle de vie du document."""
    doc = CADDocument("Projet Tôlerie Test")
    feat = SheetMetalFeature(
        feature_id="sm_1",
        name="Tôle Pliée 1",
        base_width=50.0,
        base_length=70.0,
        thickness=1.5,
        bend_radius=1.5,
        flange_length=20.0,
        k_factor=0.44
    )
    doc.add_feature(feat)

    assert "body_sm_1" in doc.bodies
    body = doc.bodies["body_sm_1"]
    assert body.volume() > 0.0

    # Test sérialisation et rechargement
    with tempfile.TemporaryDirectory() as tmpdir:
        proj_path = os.path.join(tmpdir, "test_sm.cadproj")
        assert ProjectSerializer.save_project(doc, proj_path)

        loaded_doc = ProjectSerializer.load_project(proj_path)
        assert loaded_doc is not None
        assert len(loaded_doc.features) == 1
        assert "body_sm_1" in loaded_doc.bodies
        assert loaded_doc.bodies["body_sm_1"].volume() == pytest.approx(body.volume(), rel=1e-3)


def test_dxf_laser_exporter() -> None:
    """Vérifie la génération conforme du fichier AutoCAD DXF R12."""
    part = SheetMetalPart(base_width=40.0, base_length=60.0)
    part.add_flange(20.0, 90.0)
    flat_pattern = part.generate_flat_pattern()

    with tempfile.TemporaryDirectory() as tmpdir:
        dxf_path = os.path.join(tmpdir, "flan_laser.dxf")
        content = DXFExporter.export_flat_pattern_dxf(flat_pattern, dxf_path)

        assert os.path.exists(dxf_path)
        assert "AC1009" in content
        assert "CUT" in content
        assert "BEND" in content
        assert "EOF" in content
        assert os.path.getsize(dxf_path) > 100
