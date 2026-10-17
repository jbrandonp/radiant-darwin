"""
Tests unitaires pour la sérialisation et la persistance de projet CAO (.cadproj).
"""

import os
import tempfile
import pytest

from src.core.document import CADDocument
from src.core.feature import BoxFeature, CylinderFeature
from src.core.operations_advanced import CircularPatternFeature, MirrorFeature
from src.core.types import BooleanOperation, PlaneType
from src.core.serializer import ProjectSerializer


def test_save_and_load_project() -> None:
    """Vérifie la sauvegarde réversible complète et le recalcul automatique après chargement."""
    doc = CADDocument("Projet Test Persistance")

    box = BoxFeature("f1", "Boîte Base", width=30.0, height=20.0, depth=10.0)
    doc.add_feature(box)

    cyl = CylinderFeature(
        "f2", "Cylindre Bossage", radius=6.0, height=15.0,
        operation=BooleanOperation.JOIN, target_body_id=box.body_id
    )
    doc.add_feature(cyl)

    original_vol = doc.bodies[box.body_id].volume()

    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_path = os.path.join(tmp_dir, "my_part.cadproj")
        assert ProjectSerializer.save_project(doc, proj_path)
        assert os.path.exists(proj_path)

        # Recharger dans un nouveau document
        reloaded_doc = ProjectSerializer.load_project(proj_path)
        assert reloaded_doc is not None
        assert reloaded_doc.name == "Projet Test Persistance"
        assert len(reloaded_doc.features) == 2
        assert len(reloaded_doc.bodies) == 1
        assert pytest.approx(reloaded_doc.bodies[box.body_id].volume(), 0.1) == original_vol


def test_save_and_load_patterns_and_mirror() -> None:
    """Vérifie la persistance des répétitions circulaires et symétries miroir."""
    doc = CADDocument("Test Pattern Mirror")
    box = BoxFeature("f1", "Boite Source", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box)

    circ = CircularPatternFeature(
        "f2", "Repetition Circulaire",
        source_body_id=box.body_id,
        count=3,
        total_angle_deg=180.0,
        join_bodies=False,
    )
    doc.add_feature(circ)

    mirror = MirrorFeature(
        "f3", "Symetrie Miroir",
        source_body_id=box.body_id,
        mirror_plane=PlaneType.XZ,
        join_with_source=False,
    )
    doc.add_feature(mirror)

    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_path = os.path.join(tmp_dir, "pattern_mirror.cadproj")
        assert ProjectSerializer.save_project(doc, proj_path)

        reloaded_doc = ProjectSerializer.load_project(proj_path)
        assert reloaded_doc is not None
        assert len(reloaded_doc.features) == 3

        reloaded_circ = reloaded_doc.features[1]
        assert isinstance(reloaded_circ, CircularPatternFeature)
        assert reloaded_circ.parameters["count"] == 3.0
        assert pytest.approx(reloaded_circ.parameters["total_angle"]) == 180.0
        assert reloaded_circ.join_bodies is False

        reloaded_mirror = reloaded_doc.features[2]
        assert isinstance(reloaded_mirror, MirrorFeature)
        assert reloaded_mirror.mirror_plane == PlaneType.XZ
        assert reloaded_mirror.join_with_source is False


def test_atomic_save_and_schema_versioning() -> None:
    """Vérifie l'écriture atomique (.tmp -> rename) et la présence du versioning de schéma."""
    import json
    doc = CADDocument("Atomic Schema Test")
    box = BoxFeature("b1", "Base", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box)

    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_path = os.path.join(tmp_dir, "atomic_test.cadproj")
        assert ProjectSerializer.save_project(doc, proj_path)

        # Vérifier que le fichier temporaire n'existe plus
        assert not os.path.exists(f"{proj_path}.tmp")
        assert os.path.exists(proj_path)

        # Vérifier le schéma JSON
        with open(proj_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("schema_version") == "2.4"
        assert data.get("format_version") == "1.0"
        assert "CAD Studio" in data.get("generator", "")


def test_save_and_load_body_materials() -> None:
    """Vérifie la persistance des matériaux physiques et le recalcul exact de la masse."""
    doc = CADDocument("Material Persistence Test")
    box = BoxFeature("b1", "Bloc Titane", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box)

    # 10x10x10 mm = 1000 mm3 = 1 cm3
    # Titane Grade 5 (Ti-6Al-4V) : densité = 4.43 g/cm3 -> masse = 4.43 g
    mat_key = "Titane Grade 5 (Ti-6Al-4V)"
    doc.set_body_material(box.body_id, mat_key)
    assert doc.bodies[box.body_id].material_name == mat_key
    assert pytest.approx(doc.bodies[box.body_id].calculate_mass_grams(), rel=1e-2) == 4.43

    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_path = os.path.join(tmp_dir, "material_test.cadproj")
        assert ProjectSerializer.save_project(doc, proj_path)

        reloaded = ProjectSerializer.load_project(proj_path)
        assert reloaded is not None
        assert box.body_id in reloaded.bodies
        reloaded_body = reloaded.bodies[box.body_id]
        assert reloaded_body.material_name == mat_key
        assert pytest.approx(reloaded_body.calculate_mass_grams(), rel=1e-2) == 4.43

