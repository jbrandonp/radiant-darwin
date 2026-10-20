"""
Tests unitaires pour les surfaces minimales TPMS (Gyroïde, Schwarz Diamond),
la synchronisation continue B-Rep / Mesh dans NexusSolid (sans bridage à 256 faces),
et l'algorithme spatial Sweep-and-Prune de détection d'interférences O(N log N).
"""

from __future__ import annotations
import math
import pytest
import numpy as np
import manifold3d as m

from src.core.types import Vector3D
from src.core.geometry import make_box, make_cylinder, Solid
from src.core.generative_lattices import (
    LatticeType,
    make_tpms_gyroid_cell,
    make_tpms_schwarz_diamond_cell,
    generate_lattice_volume,
)
from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.ai.cad_validator import CADValidator, InterferenceReport


def test_real_tpms_gyroid_and_diamond_minimal_surfaces() -> None:
    """Vérifie la génération exacte des surfaces minimales TPMS Gyroïde et Schwarz Diamond."""
    # 1. Cellule unitaire Gyroïde de Schoen
    gyroid_cell = make_tpms_gyroid_cell(cell_size=10.0, wall_thickness=1.0)
    assert not gyroid_cell.is_empty()
    assert gyroid_cell.volume() > 0.0
    # Le Gyroïde authentique forme un réseau continu à ouvertures traversantes (genus > 0)
    assert gyroid_cell.genus() > 0

    b_min, b_max = gyroid_cell.bounding_box()
    assert b_min.x >= -0.01 and b_max.x <= 10.01
    assert b_min.y >= -0.01 and b_max.y <= 10.01
    assert b_min.z >= -0.01 and b_max.z <= 10.01

    # 2. Cellule unitaire Schwarz Diamond
    diamond_cell = make_tpms_schwarz_diamond_cell(cell_size=10.0, wall_thickness=1.0)
    assert not diamond_cell.is_empty()
    assert diamond_cell.volume() > 0.0
    assert diamond_cell.genus() > 0

    # 3. Volume périodique TPMS continu multi-cellulaire
    vol_min = Vector3D(0.0, 0.0, 0.0)
    vol_max = Vector3D(20.0, 20.0, 20.0)
    tpms_vol = generate_lattice_volume(
        vol_min, vol_max, cell_size_mm=10.0, strut_or_wall_mm=1.0, lattice_type=LatticeType.GYROID
    )
    assert not tpms_vol.is_empty()
    assert tpms_vol.volume() > 0.0
    l_min, l_max = tpms_vol.bounding_box()
    assert l_max.x >= 19.9 and l_max.y >= 19.9 and l_max.z >= 19.9


def test_hybrid_solid_brep_sync_after_booleans_and_no_256_cap() -> None:
    """Vérifie l'absence de bridage à 256 faces et la synchronisation du B-Rep après booléen."""
    # 1. Création d'une sphère haute résolution avec plus de 300 facettes
    m_sphere = m.Manifold.sphere(10.0, circular_segments=36)
    tri_count = m_sphere.num_tri()
    assert tri_count > 256, f"La sphère devrait comporter plus de 256 triangles, trouvé: {tri_count}"

    sphere_solid = NexusSolid(name="HighResSphere", internal_manifold=m_sphere)
    # Vérifier que le B-Rep contient TOUTES les faces du maillage (aucune troncature à 256)
    assert len(sphere_solid.brep.faces) == tri_count
    assert len(sphere_solid.brep.vertices) == m_sphere.num_vert()

    # 2. Synchronisation du B-Rep après opération booléenne
    box = NexusSolid.make_box(20.0, 20.0, 20.0, "Box")
    cyl = NexusSolid.make_cylinder(5.0, 30.0, "Cyl")
    assert len(box.brep.faces) == 6

    # Percer la boîte avec le cylindre
    drilled = box.difference(cyl, "DrilledBox")
    assert not drilled.is_empty()
    assert drilled.volume() < box.volume()

    # Le B-Rep régénéré doit refléter la nouvelle géométrie trouée (plus de 6 faces!)
    assert len(drilled.brep.faces) > 6
    assert len(drilled.brep.vertices) > 8


def test_sweep_and_prune_interference_detection() -> None:
    """Vérifie la détection d'interférences Broadphase Sweep-and-Prune O(N log N)."""
    # 1. Trois solides strictement séparés le long de l'axe X
    box1 = make_box(10.0, 10.0, 10.0).translate(Vector3D(0.0, 0.0, 0.0))
    box2 = make_box(10.0, 10.0, 10.0).translate(Vector3D(50.0, 0.0, 0.0))
    box3 = make_box(10.0, 10.0, 10.0).translate(Vector3D(100.0, 0.0, 0.0))

    bodies = {"b1": box1, "b2": box2, "b3": box3}
    clashes = CADValidator.check_scene_interferences(bodies)
    assert len(clashes) == 0

    # 2. Ajout d'un quatrième solide qui entre en collision partielle avec box1
    clash_box = make_box(10.0, 10.0, 10.0).translate(Vector3D(5.0, 0.0, 0.0))
    bodies["b4"] = clash_box

    clashes2 = CADValidator.check_scene_interferences(bodies)
    assert len(clashes2) == 1
    report = clashes2[0]
    assert report.has_collision
    # Collision de 5 x 10 x 10 = 500 mm³
    assert math.isclose(report.clash_volume_mm3, 500.0, rel_tol=1e-2)
    assert set([report.body_1_id, report.body_2_id]) == {"b1", "b4"}
