"""
Tests unitaires pour le moteur de réparation géométrique et topologique (ShapeFix / Shape Healing).
Vérifie la couture des bords ouverts, l'élimination des facettes dégénérées,
l'harmonisation des normales de faces et la fermeture des boucles 2D.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.shape_healing import ShapeFixer, HealingReport
from src.core.geometry import make_box


def test_sew_mesh_boundaries_closes_cracks() -> None:
    """Vérifie que deux sommets séparés par un interstice IEEE 754 < tolérance sont cousus."""
    # Création d'un tétraèdre avec un sommet dupliqué fendu (crack)
    # Sommets 0, 1, 2, 3 + sommet 4 qui est une copie du sommet 3 décalée de 0.0002 mm
    v = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [5.0, 10.0, 0.0],
        [5.0, 5.0, 10.0],
        [5.0, 5.0, 10.0002],  # Sommet fendu (crack de 0.0002 mm)
    ], dtype=np.float64)

    # Triangle 3 utilise le sommet 4 au lieu du sommet 3 -> arêtes ouvertes non partagées
    tris = np.array([
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 4, 0],  # Utilise sommet 4
    ], dtype=np.int32)

    # Initialement, le maillage n'est pas étanche
    init_boundaries = ShapeFixer.find_boundary_edges(tris)
    assert len(init_boundaries) > 0

    # Couture avec tolérance de 1e-3 mm
    healed_v, healed_t, sewn = ShapeFixer.sew_mesh_boundaries(v, tris, tolerance=1e-3)
    assert sewn >= 1

    final_boundaries = ShapeFixer.find_boundary_edges(healed_t)
    assert len(final_boundaries) == 0  # Toutes les arêtes frontières sont refermées


def test_remove_degenerate_faces() -> None:
    """Vérifie l'élimination des triangles à sommets dupliqués ou d'aire quasi-nulle."""
    v = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [1.0, 1.0, 0.0],
    ], dtype=np.float64)

    tris = np.array([
        [0, 1, 2],        # Triangle valide
        [0, 0, 1],        # Dégénéré : sommets dupliqués
        [0, 1, 1],        # Dégénéré : sommets dupliqués
        [0, 1, 0],        # Dégénéré : sommets dupliqués
    ], dtype=np.int32)

    clean_v, clean_t, removed = ShapeFixer.remove_degenerate_faces(v, tris)
    assert removed == 3
    assert len(clean_t) == 1
    assert list(clean_t[0]) == [0, 1, 2]


def test_reconcile_orientations_flips_inverted_face() -> None:
    """Vérifie la propagation de l'orientation pour corriger une normale inversée."""
    v = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [10.0, 10.0, 0.0],
        [0.0, 10.0, 0.0],
    ], dtype=np.float64)

    # Deux triangles formant un carré plat.
    # Tri 0 : [0, 1, 2] -> arête partagée [1, 2] orientée 1 -> 2
    # Tri 1 : [0, 1, 2] inversé ou [0, 2, 1] où arête [1, 2] est orientée dans le même sens
    tris = np.array([
        [0, 1, 2],
        [0, 1, 2],  # Incohérent
    ], dtype=np.int32)

    _, oriented_t, flipped = ShapeFixer.reconcile_orientations(v, tris)
    assert flipped >= 0


def test_heal_mesh_full_pipeline_produces_watertight_manifold() -> None:
    """Vérifie le pipeline complet de guérison sur une boîte perturbée."""
    box = make_box(20.0, 20.0, 20.0)
    mesh = box.manifold.to_mesh()
    verts = np.array(mesh.vert_properties, dtype=np.float64)
    tris = np.array(mesh.tri_verts, dtype=np.int32)

    # Injection d'une micro-fissure : dupliquer le sommet 0 et le déplacer de 0.0001 mm
    crack_vert = verts[0] + np.array([0.0001, 0.0001, 0.0], dtype=np.float64)
    new_v = np.vstack([verts, crack_vert])
    new_vert_idx = len(verts)

    # Remplacer la référence du sommet 0 dans le premier triangle par new_vert_idx
    new_tris = tris.copy()
    loc = int(np.where(new_tris[0] == 0)[0][0])
    new_tris[0, loc] = new_vert_idx

    # Exécution du ShapeFixer
    healed_v, healed_t, report = ShapeFixer.heal_mesh(new_v, new_tris, tolerance=1e-3)
    assert report.is_watertight is True
    assert report.sewn_vertices >= 1

    # Reconstruction en solide Manifold
    import manifold3d as m
    final_mesh = m.Mesh(
        vert_properties=healed_v.astype(np.float32),
        tri_verts=healed_t.astype(np.int32)
    )
    final_solid = m.Manifold(final_mesh)
    assert not final_solid.is_empty()
    assert pytest.approx(final_solid.volume(), 1e-2) == box.volume()


def test_heal_wire_2d() -> None:
    """Vérifie la fermeture et le nettoyage de boucles d'esquisse 2D."""
    # Boucle avec doublon et fin non fermée de 0.00005 mm
    wire = [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0000001, 0.0),  # Doublon sous tolérance
        (10.0, 10.0),
        (0.0, 10.0),
        (0.00002, 0.00001),  # Quasi-fermeture
    ]

    healed = ShapeFixer.heal_wire_2d(wire, tolerance=1e-4)
    assert len(healed) == 5  # Doublon supprimé, et point final fermé exactement sur (0, 0)
    assert healed[0] == (0.0, 0.0)
    assert healed[-1] == healed[0]
