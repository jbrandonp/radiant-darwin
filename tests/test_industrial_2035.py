"""
Tests unitaires pour les Modules Industriels et Fabrication Additive 2035.
Valide l'analyse de dépouille/contre-dépouilles, l'épaisseur de paroi,
le certificat d'étanchéité, et la génération de structures alvéolaires TPMS Gyroïde & Octet-Truss.
"""

import pytest
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import make_box, make_cylinder, make_sphere, Solid
from src.core.industrial_analyzer import (
    compute_draft_angles, compute_wall_thickness, heal_and_validate_mesh,
    DraftAngleResult, WallThicknessResult, MeshHealingReport
)
from src.core.generative_lattices import (
    LatticeType, make_octet_cell, make_tpms_gyroid_cell,
    generate_lattice_volume, create_lightweight_infilled_part
)


def test_draft_angle_analysis_cube() -> None:
    """Vérifie le calcul analytique des angles de dépouille et la détection de contre-dépouilles."""
    # Pavé droit aligné sur Z
    box = make_box(20.0, 20.0, 20.0)
    # Tirage vertical selon +Z
    res = compute_draft_angles(box, pull_direction=Vector3D(0.0, 0.0, 1.0), min_draft_deg=2.0)

    assert isinstance(res, DraftAngleResult)
    assert len(res.face_angles_deg) > 0
    # La face supérieure a un angle de dépouille de 90 deg (démoulable)
    assert np.count_nonzero(res.face_angles_deg >= 89.0) > 0
    # La face inférieure orientée vers -Z est en contre-dépouille par rapport à +Z
    assert np.count_nonzero(res.face_angles_deg <= -89.0) > 0
    assert res.undercut_count > 0
    assert not res.is_fully_demoldable


def test_draft_angle_empty_solid() -> None:
    """Vérifie la robustesse face à un solide vide."""
    empty = Solid(solid_name="Empty")
    res = compute_draft_angles(empty)
    assert res.demoldable_ratio == 0.0
    assert res.undercut_count == 0


def test_wall_thickness_evaluation() -> None:
    """Vérifie la détection des épaisseurs minimales et zones critiques."""
    box = make_box(10.0, 10.0, 10.0)
    res = compute_wall_thickness(box, min_nominal_mm=2.0)

    assert isinstance(res, WallThicknessResult)
    assert res.min_thickness_mm > 0.0
    assert res.max_thickness_mm <= 10.0
    assert res.mean_thickness_mm > 0.0
    assert len(res.thickness_values) > 0


def test_mesh_healing_and_quality_certificate() -> None:
    """Vérifie l'audit topologique et la certification d'étanchéité industrielle."""
    cyl = make_cylinder(10.0, 25.0)
    healed, report = heal_and_validate_mesh(cyl)

    assert isinstance(report, MeshHealingReport)
    assert report.is_watertight
    assert report.is_valid_manifold
    assert report.num_vertices > 0
    assert report.num_faces > 0
    assert report.volume_mm3 > 0.0
    assert report.surface_area_mm2 > 0.0
    assert sum(1 for action in report.healing_actions if "Manifold3D" in action) > 0


def test_octet_truss_lattice_unit_cell() -> None:
    """Vérifie la génération géométrique d'une cellule Octet-Truss étanche."""
    cell = make_octet_cell(cell_size=10.0, strut_radius=1.0)
    assert not cell.is_empty()
    assert cell.volume() > 0.0
    assert cell.surface_area() > 0.0
    assert cell.genus() > 0  # Contient des ouvertures traversantes (poreuse)


def test_tpms_gyroid_unit_cell() -> None:
    """Vérifie la génération de la surface minimale Gyroïde étanche."""
    gyroid = make_tpms_gyroid_cell(cell_size=12.0, wall_thickness=1.2)
    assert not gyroid.is_empty()
    assert gyroid.volume() > 0.0
    b_min, b_max = gyroid.bounding_box()
    # Reste confiné dans sa boîte englobante
    assert b_max.x <= 12.05
    assert b_max.y <= 12.05
    assert b_max.z <= 12.05


def test_generate_lattice_volume() -> None:
    """Vérifie la répétition spatiale d'un réseau réticulaire dans un volume borné."""
    b_min = Vector3D(0.0, 0.0, 0.0)
    b_max = Vector3D(20.0, 20.0, 20.0)
    lattice = generate_lattice_volume(b_min, b_max, cell_size_mm=10.0, strut_or_wall_mm=1.0, lattice_type=LatticeType.OCTET_TRUSS)

    assert not lattice.is_empty()
    assert lattice.volume() > 0.0
    l_min, l_max = lattice.bounding_box()
    assert l_max.x >= 20.0
    assert l_max.y >= 20.0
    assert l_max.z >= 20.0


def test_lightweight_infilled_aerospace_part() -> None:
    """Vérifie l'allègement topologique d'une pièce avec peau externe étanche et cœur alvéolaire."""
    block = make_box(25.0, 25.0, 25.0)
    orig_vol = block.volume()

    lightened, mass_saving = create_lightweight_infilled_part(
        block,
        lattice_type=LatticeType.OCTET_TRUSS,
        cell_size_mm=12.0,
        strut_thickness_mm=1.0,
        shell_thickness_mm=1.5
    )

    assert not lightened.is_empty()
    # Doit avoir une réduction de masse mesurable (> 10%)
    assert mass_saving > 10.0
    assert lightened.volume() < orig_vol
    # La pièce finale reste 100% étanche
    healed, report = heal_and_validate_mesh(lightened)
    assert report.is_watertight
