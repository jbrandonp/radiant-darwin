"""
Tests unitaires pour la sérialisation et la persistance de projet CAO (.cadproj).
"""

import os
import tempfile
import pytest

from src.core.document import CADDocument
from src.core.feature import BoxFeature, CylinderFeature
from src.core.types import BooleanOperation
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
