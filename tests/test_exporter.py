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


def test_step_nexus_advanced_brep_export() -> None:
    """Valide l'exportation d'un NexusSolid en STEP AP242 avec entités ADVANCED_FACE et MANIFOLD_SOLID_BREP."""
    from src.core.nexus_kernel.hybrid_solid import NexusSolid
    from src.core.step_exporter import STEPExporter

    box = NexusSolid.make_box(20.0, 30.0, 40.0, name="PrecisionCube")
    step_str = STEPExporter.export_nexus_brep_to_string(box)

    assert "ISO-10303-21;" in step_str
    assert "ADVANCED_BREP_SHAPE_REPRESENTATION" in step_str
    assert "MANIFOLD_SOLID_BREP" in step_str
    assert "ADVANCED_FACE" in step_str
    assert "EDGE_CURVE" in step_str
    assert "ORIENTED_EDGE" in step_str
    assert "END-ISO-10303-21;" in step_str

    with tempfile.TemporaryDirectory() as tmp_dir:
        step_path = os.path.join(tmp_dir, "nexus_box.step")
        assert STEPExporter.export_nexus_solid(box, step_path) is True
        assert os.path.exists(step_path)
        assert os.path.getsize(step_path) > 500

