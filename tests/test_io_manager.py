"""
Tests unitaires pour la façade universelle IOManager (src/io/io_manager.py).
Validation du typage strict, de la détection de format, de l'exportation et de l'importation.
"""

from __future__ import annotations
import os
import tempfile
import pytest

from src.io.io_manager import IOManager, FileFormat, ImportResult, ExportResult
from src.core.geometry import Solid, make_box
from src.core.types import PlaneType


def test_supported_formats() -> None:
    """Vérifie que les formats majeurs sont tous déclarés et disponibles."""
    import_fmts = IOManager.get_supported_import_formats()
    export_fmts = IOManager.get_supported_export_formats()

    assert ".step" in import_fmts
    assert ".dxf" in import_fmts
    assert ".svg" in import_fmts
    assert ".stl" in import_fmts
    assert ".obj" in import_fmts

    assert ".step" in export_fmts
    assert ".3mf" in export_fmts
    assert ".stl" in export_fmts
    assert ".gltf" in export_fmts


def test_detect_format() -> None:
    """Vérifie la détection exacte du format selon l'extension."""
    assert IOManager.detect_format("part.step") == FileFormat.STEP
    assert IOManager.detect_format("part.STP") == FileFormat.STEP
    assert IOManager.detect_format("drawing.dxf") == FileFormat.DXF
    assert IOManager.detect_format("logo.svg") == FileFormat.SVG
    assert IOManager.detect_format("print.3mf") == FileFormat.THREEMF
    assert IOManager.detect_format("mesh.stl") == FileFormat.STL
    assert IOManager.detect_format("model.obj") == FileFormat.OBJ
    assert IOManager.detect_format("unknown.xyz123") == FileFormat.UNKNOWN


def test_export_and_import_stl() -> None:
    """Vérifie le cycle complet d'exportation puis importation d'un maillage STL via IOManager."""
    box = make_box(10.0, 20.0, 30.0, name="TestBox")
    bodies = {"TestBox": box}

    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = os.path.join(tmpdir, "box.stl")
        export_res = IOManager.save(bodies, stl_path)

        assert export_res.success is True
        assert export_res.format == FileFormat.STL
        assert export_res.bytes_written > 0
        assert os.path.exists(stl_path)

        import_res = IOManager.load(stl_path)
        assert import_res.success is True
        assert import_res.format == FileFormat.STL
        assert len(import_res.solids) == 1
        imported_solid = next(iter(import_res.solids.values()))
        assert abs(imported_solid.volume() - 6000.0) < 50.0


def test_export_and_import_obj() -> None:
    """Vérifie l'exportation et la relecture d'un fichier Wavefront OBJ."""
    box = make_box(10.0, 10.0, 10.0, name="Cube")
    bodies = {"Cube": box}

    with tempfile.TemporaryDirectory() as tmpdir:
        obj_path = os.path.join(tmpdir, "cube.obj")
        export_res = IOManager.save(bodies, obj_path)

        assert export_res.success is True
        assert export_res.format == FileFormat.OBJ
        assert os.path.exists(obj_path)

        import_res = IOManager.load(obj_path)
        assert import_res.success is True
        assert import_res.format == FileFormat.OBJ
        assert len(import_res.solids) == 1


def test_export_step() -> None:
    """Vérifie l'exportation STEP ISO 10303-21."""
    box = make_box(15.0, 15.0, 15.0, name="StepCube")
    bodies = {"StepCube": box}

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = os.path.join(tmpdir, "cube.step")
        export_res = IOManager.save(bodies, step_path)

        assert export_res.success is True
        assert export_res.format == FileFormat.STEP
        assert export_res.bytes_written > 0
        assert os.path.exists(step_path)


def test_export_threemf() -> None:
    """Vérifie l'exportation 3MF."""
    box = make_box(10.0, 10.0, 10.0, name="Part3MF")
    bodies = {"Part3MF": box}

    with tempfile.TemporaryDirectory() as tmpdir:
        threemf_path = os.path.join(tmpdir, "part.3mf")
        export_res = IOManager.save(bodies, threemf_path)

        assert export_res.success is True
        assert export_res.format == FileFormat.THREEMF
        assert export_res.bytes_written > 0


def test_load_unsupported_format() -> None:
    """Vérifie qu'un format non supporté retourne une erreur propre sans crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = os.path.join(tmpdir, "test.xyz")
        with open(fake_path, "w", encoding="utf-8") as f:
            f.write("unknown format data")

        res = IOManager.load(fake_path)
        assert res.success is False
        assert res.format == FileFormat.UNKNOWN
        assert res.error_message is not None
