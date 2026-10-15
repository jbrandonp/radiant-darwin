"""
Suite de tests de régression sur fichiers CAO réels (Fixtures physiques).
Valide le chargement, l'analyse topologique, la watertightness et la fidélité
géométrique des formats standards : STEP (AP214/AP242), DXF, IGES 5.3 et STL.
"""

from __future__ import annotations
import os
import struct
from pathlib import Path
from typing import List, Tuple
import pytest
import numpy as np
import trimesh

from src.core.step_importer import STEPImporter, STEPGeometricContext, STEPModel
from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.core.geometry import Solid


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def get_fixture_path(relative_subpath: str) -> str:
    """Retourne le chemin absolu normalisé vers un fichier de fixture CAO."""
    p = FIXTURES_DIR / relative_subpath
    assert p.is_file(), f"Le fichier de fixture '{relative_subpath}' est introuvable à {p}"
    return str(p.resolve())


# ==============================================================================
# 1. TESTS STEP AP214 & AP242 SUR FICHIERS RÉELS
# ==============================================================================

def test_step_ap214_real_bracket_fixture() -> None:
    """Vérifie le parsing complet du fichier STEP AP214 réel d'équerre mécanique."""
    fpath = get_fixture_path("step/mechanical_bracket_ap214.step")
    importer = STEPImporter()
    context: STEPGeometricContext = importer.import_step(fpath)

    assert "214" in context.schema_name or "AUTOMOTIVE_DESIGN" in context.schema_name
    assert len(context.cartesian_points) >= 8
    assert len(context.faces) >= 6
    assert "MechanicalBracket" in context.solids

    # Reconstitution en NexusSolid volumique
    nexus_solid: NexusSolid = importer.import_to_nexus_solid(fpath)
    assert nexus_solid.name == "MechanicalBracket"
    assert nexus_solid.is_watertight() is True
    assert nexus_solid.volume() == pytest.approx(22500.0, rel=1e-2)

    # Reconstitution en Solid CAO éditable
    cad_solid = importer.import_to_cad_solid(fpath)
    assert cad_solid is not None
    assert cad_solid.volume() == pytest.approx(22500.0, rel=1e-2)
    b_min, b_max = cad_solid.bounding_box()
    assert b_max.x >= 50.0
    assert b_max.y >= 30.0
    assert b_max.z >= 15.0


def test_step_ap242_real_flange_pmi_fixture() -> None:
    """Vérifie l'extraction PMI et la géométrie du fichier réel STEP AP242."""
    fpath = get_fixture_path("step/precision_flange_ap242_pmi.step")
    importer = STEPImporter()
    model: STEPModel = importer.import_model(fpath)

    assert "AP242" in model.schema_version
    assert model.solid.is_watertight() is True
    assert model.solid.volume() == pytest.approx(32000.0, rel=1e-2)

    # Validation des tolérances et datums PMI
    pmi_list: List[str] = model.pmi_annotations
    assert len(pmi_list) >= 4
    has_datum_a = any("DATUM_A" in item for item in pmi_list)
    has_datum_b = any("DATUM_B" in item for item in pmi_list)
    has_flatness = any("FLATNESS_TOL" in item for item in pmi_list)
    has_perpendicularity = any("PERPENDICULARITY_TOL" in item for item in pmi_list)

    assert has_datum_a is True
    assert has_datum_b is True
    assert has_flatness is True
    assert has_perpendicularity is True


# ==============================================================================
# 2. TESTS DXF SUR FICHIERS RÉELS
# ==============================================================================

def test_dxf_r12_flat_pattern_fixture() -> None:
    """Vérifie le contenu, les calques et la structure du fichier DXF R12 réel."""
    fpath = get_fixture_path("dxf/bracket_flat_pattern_r12.dxf")
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    assert "AC1009" in content
    assert "CUT" in content
    assert "BEND" in content
    assert "CONTINUOUS" in content
    assert "DASHED" in content
    assert "EOF" in content

    # Chargement géométrique vectoriel
    path_2d = trimesh.load(fpath, file_type="dxf")
    assert isinstance(path_2d, trimesh.path.path.Path2D)
    assert len(path_2d.entities) >= 5
    bounds = path_2d.bounds
    assert bounds is not None
    dx = float(bounds[1][0] - bounds[0][0])
    dy = float(bounds[1][1] - bounds[0][1])
    assert dx == pytest.approx(60.0, rel=1e-3)
    assert dy == pytest.approx(123.7124, rel=1e-3)


def test_dxf_laser_gasket_2d_fixture() -> None:
    """Vérifie l'analyse géométrique du joint 2D DXF avec contour et alésages."""
    fpath = get_fixture_path("dxf/laser_cut_gasket_2d.dxf")
    path_2d = trimesh.load(fpath, file_type="dxf")

    assert isinstance(path_2d, trimesh.path.path.Path2D)
    assert len(path_2d.entities) == 6  # 4 lignes de contour + 2 cercles de perçage
    bounds = path_2d.bounds
    assert bounds is not None
    assert bounds[1][0] >= 100.0
    assert bounds[1][1] >= 50.0


# ==============================================================================
# 3. TESTS IGES 5.3 SUR FICHIER RÉEL
# ==============================================================================

def test_iges_53_real_bracket_structure_and_cards() -> None:
    """Vérifie la conformité rigoureuse 80 colonnes de l'archive IGES 5.3."""
    fpath = get_fixture_path("iges/benchmark_bracket_53.igs")
    with open(fpath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    assert len(lines) > 20
    # Règle absolue IGES : chaque carte doit comporter exactement 80 caractères
    for idx, line in enumerate(lines):
        assert len(line) == 80, f"Erreur ligne {idx + 1} : longueur {len(line)} != 80"

    # Vérification des sections S, G, D, P, T
    sections_found = {line[72] for line in lines}
    assert sections_found == {"S", "G", "D", "P", "T"}

    # Carte de terminaison T
    term_line = [l for l in lines if l[72] == "T"][0]
    assert "S      1" in term_line
    assert "T      1" in term_line


# ==============================================================================
# 4. TESTS STL SUR FICHIERS RÉELS (ASCII & BINAIRE)
# ==============================================================================

def test_stl_ascii_calibration_cube_fixture() -> None:
    """Vérifie le chargement et le diagnostic du cube de calibration STL ASCII."""
    fpath = get_fixture_path("stl/calibration_cube_ascii.stl")
    mesh = trimesh.load(fpath, file_type="stl_ascii", force="mesh")

    assert mesh.is_watertight is True
    assert len(mesh.faces) == 12
    assert len(mesh.vertices) == 8
    assert mesh.volume == pytest.approx(8000.0, rel=1e-3)
    assert mesh.area == pytest.approx(2400.0, rel=1e-3)


def test_stl_binary_benchmark_wedge_fixture() -> None:
    """Vérifie l'intégrité de l'en-tête, du décompte et du volume du STL binaire."""
    fpath = get_fixture_path("stl/benchmark_wedge_binary.stl")
    file_size = os.path.getsize(fpath)

    with open(fpath, "rb") as f:
        header = f.read(80)
        tri_count_bytes = f.read(4)
        tri_count = struct.unpack("<I", tri_count_bytes)[0]

    assert b"CAD Studio Benchmark" in header
    assert tri_count == 12
    expected_size = 84 + tri_count * 50
    assert file_size == expected_size

    # Chargement via trimesh et conversion en Solid CAO étanche
    mesh = trimesh.load(fpath, file_type="stl", force="mesh")
    assert mesh.is_watertight is True
    assert mesh.volume == pytest.approx(6000.0, rel=1e-3)
