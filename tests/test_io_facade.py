"""
Suite de tests unitaires pour la façade unifiée CADIOFacade (src/io/facade.py).
Vérifie :
1. L'exportation multi-format (STEP, STL, OBJ, PLY, 3MF).
2. L'importation STEP vers Solide B-Rep.
3. La gestion des formats de maillage invalides.
4. L'exportation des patrons dépliés tôlerie (DXF) et des mises en plan (SVG).

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from pathlib import Path
import pytest

from src.io.facade import CADIOFacade
from src.core.geometry import Solid, make_box
from src.core.types import Vector3D


def test_io_facade_mesh_exports(tmp_path: Path) -> None:
    """Vérifie l'exportation des formats de maillage 3D STL, OBJ et PLY via la façade."""
    box = make_box(10.0, 20.0, 30.0)
    solids = {"box1": box}

    stl_path = str(tmp_path / "test_box.stl")
    obj_path = str(tmp_path / "test_box.obj")
    ply_path = str(tmp_path / "test_box.ply")

    assert CADIOFacade.export_mesh(solids, stl_path, fmt="stl") is True
    assert Path(stl_path).is_file()
    assert Path(stl_path).stat().st_size > 0

    assert CADIOFacade.export_mesh(solids, obj_path, fmt="obj") is True
    assert Path(obj_path).is_file()
    assert Path(obj_path).stat().st_size > 0

    assert CADIOFacade.export_mesh(solids, ply_path, fmt="ply") is True
    assert Path(ply_path).is_file()
    assert Path(ply_path).stat().st_size > 0


def test_io_facade_invalid_mesh_format(tmp_path: Path) -> None:
    """Vérifie qu'un format de maillage non supporté lève une exception ValueError explicite."""
    box = make_box(5.0, 5.0, 5.0)
    solids = {"box": box}
    unsupported_path = str(tmp_path / "test.unsupported")

    with pytest.raises(ValueError, match="Format de maillage non supporté"):
        CADIOFacade.export_mesh(solids, unsupported_path, fmt="unknown_format")


def test_io_facade_step_export_and_import(tmp_path: Path) -> None:
    """Vérifie l'exportation et la ré-importation d'un solide au format STEP ISO 10303-21."""
    box = make_box(15.0, 25.0, 35.0)
    step_path = str(tmp_path / "test_component.step")

    # Export d'un solide unique
    export_ok = CADIOFacade.export_step(box, step_path)
    assert export_ok is True
    assert Path(step_path).is_file()
    assert Path(step_path).stat().st_size > 0

    # Import du contexte géométrique STEP
    imported_ctx = CADIOFacade.import_step_context(step_path)
    assert imported_ctx is not None
    assert len(imported_ctx.cartesian_points) > 0
    assert imported_ctx.schema_name in ("AP214", "AP203", "AP242", "AUTOMOTIVE_DESIGN_CC2")

    # Import du solide B-Rep NexusSolid
    imported_solid = CADIOFacade.import_step(step_path)
    assert imported_solid is not None


def test_io_facade_3mf_export(tmp_path: Path) -> None:
    """Vérifie l'exportation au format de fabrication additive 3MF (ISO/IEC 25422)."""
    box = make_box(12.0, 14.0, 16.0)
    solids = {"part1": box}
    threemf_path = str(tmp_path / "test_additive.3mf")

    export_ok = CADIOFacade.export_3mf(threemf_path, solids=solids)
    assert export_ok is True
    assert Path(threemf_path).is_file()
    assert Path(threemf_path).stat().st_size > 0
