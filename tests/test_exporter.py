"""
Tests unitaires pour l'exportation multi-format (STL, OBJ, PLY).
"""

import os
import tempfile
import pytest

from src.core.geometry import make_box
from src.core.exporter import CADExporter


def test_export_stl_obj_ply() -> None:
    """Vérifie la génération valide des fichiers STL, OBJ et PLY sur le disque."""
    box = make_box(15.0, 15.0, 15.0)
    bodies = {"body_1": box}

    with tempfile.TemporaryDirectory() as tmp_dir:
        stl_path = os.path.join(tmp_dir, "test_part.stl")
        obj_path = os.path.join(tmp_dir, "test_part.obj")
        ply_path = os.path.join(tmp_dir, "test_part.ply")

        # Export STL
        assert CADExporter.export_stl(bodies, stl_path, binary=True)
        assert os.path.exists(stl_path)
        assert os.path.getsize(stl_path) > 0

        # Export OBJ
        assert CADExporter.export_obj(bodies, obj_path)
        assert os.path.exists(obj_path)
        assert os.path.getsize(obj_path) > 0

        # Export PLY
        assert CADExporter.export_ply(bodies, ply_path)
        assert os.path.exists(ply_path)
        assert os.path.getsize(ply_path) > 0
