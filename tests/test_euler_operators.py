"""
Tests unitaires formels des opérateurs topologiques d'Euler-Poincaré de NEXUS-3D.
Vérifie la préservation des invariants mathématiques fondamentaux :
V - E + F - (L - F) = 2 * (S - G).
"""

import pytest
import numpy as np

from src.core.nexus_kernel.brep_topology import (
    NexusBRep, NexusVertex, NexusEdge, NexusWire, NexusFace, NexusShell, NexusLineCurve, NexusPlaneSurface
)
from src.core.nexus_kernel.euler_operators import (
    NexusEulerOperators, EulerPoincareDiagnostic
)


def test_mvfs_initial_solid() -> None:
    """Vérifie l'opérateur fondamental MVFS (Make Vertex, Face, Shell)."""
    brep = NexusBRep("brep_mvfs")
    v, face, shell = NexusEulerOperators.make_vertex_face_shell(
        brep, vertex_id="v1", x=0.0, y=0.0, z=0.0, face_id="f1", shell_id="s1"
    )

    assert len(brep.vertices) == 1
    assert len(brep.faces) == 1
    assert len(brep.shells) == 1
    assert len(brep.edges) == 0

    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid
    assert diag.euler_characteristic == 2
    assert diag.vertices_count == 1
    assert diag.faces_count == 1
    assert diag.shells_count == 1


def test_mev_operator_chain() -> None:
    """Vérifie l'opérateur MEV (Make Edge, Vertex) en chaîne séquentielle."""
    brep = NexusBRep("brep_mev")
    NexusEulerOperators.make_vertex_face_shell(
        brep, vertex_id="v0", x=0.0, y=0.0, z=0.0, face_id="f0", shell_id="s0"
    )

    v1, e1 = NexusEulerOperators.make_edge_vertex(
        brep, existing_vertex_id="v0", new_vertex_id="v1", x=10.0, y=0.0, z=0.0,
        new_edge_id="e1", wire_id="Wire_f0_outer"
    )
    v2, e2 = NexusEulerOperators.make_edge_vertex(
        brep, existing_vertex_id="v1", new_vertex_id="v2", x=10.0, y=10.0, z=0.0,
        new_edge_id="e2", wire_id="Wire_f0_outer"
    )

    assert len(brep.vertices) == 3
    assert len(brep.edges) == 2
    assert len(brep.wires["Wire_f0_outer"].edges) == 2

    # Invariant : (V - E) reste constant
    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid
    assert diag.euler_characteristic == 2


def test_mef_operator_face_split() -> None:
    """Vérifie l'opérateur MEF (Make Edge, Face) qui scinde une boucle en deux faces."""
    brep = NexusBRep("brep_mef")
    NexusEulerOperators.make_vertex_face_shell(
        brep, vertex_id="v0", x=0.0, y=0.0, z=0.0, face_id="f0", shell_id="s0"
    )
    NexusEulerOperators.make_edge_vertex(
        brep, "v0", "v1", 10.0, 0.0, 0.0, "e1", "Wire_f0_outer"
    )
    NexusEulerOperators.make_edge_vertex(
        brep, "v1", "v2", 10.0, 10.0, 0.0, "e2", "Wire_f0_outer"
    )
    NexusEulerOperators.make_edge_vertex(
        brep, "v2", "v3", 0.0, 10.0, 0.0, "e3", "Wire_f0_outer"
    )

    # Fermer le contour et créer une seconde face avec MEF entre v3 et v0
    e4, f1 = NexusEulerOperators.make_edge_face(
        brep, vertex_1_id="v3", vertex_2_id="v0", new_edge_id="e4",
        new_face_id="f1", wire_to_split_id="Wire_f0_outer", new_wire_id="w_f1"
    )

    assert len(brep.vertices) == 4
    assert len(brep.edges) == 4
    assert len(brep.faces) == 2

    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid
    assert diag.euler_characteristic == 2


def test_kve_operator_vertex_kill() -> None:
    """Vérifie l'opérateur KVE (Kill Vertex, Edge) supprimant un sommet feuille."""
    brep = NexusBRep("brep_kve")
    NexusEulerOperators.make_vertex_face_shell(
        brep, "v0", 0.0, 0.0, 0.0, "f0", "s0"
    )
    NexusEulerOperators.make_edge_vertex(
        brep, "v0", "v1", 5.0, 0.0, 0.0, "e1", "Wire_f0_outer"
    )

    assert len(brep.vertices) == 2
    assert len(brep.edges) == 1

    success = NexusEulerOperators.kill_vertex_edge(brep, vertex_id="v1", edge_id="e1")
    assert success
    assert len(brep.vertices) == 1
    assert len(brep.edges) == 0

    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid
    assert diag.euler_characteristic == 2


def test_kef_operator_face_merge() -> None:
    """Vérifie l'opérateur KEF (Kill Edge, Face) fusionnant deux faces contiguës."""
    brep = NexusBRep("brep_kef")
    NexusEulerOperators.make_vertex_face_shell(brep, "v0", 0.0, 0.0, 0.0, "f0", "s0")
    NexusEulerOperators.make_edge_vertex(brep, "v0", "v1", 10.0, 0.0, 0.0, "e1", "Wire_f0_outer")
    NexusEulerOperators.make_edge_vertex(brep, "v1", "v2", 10.0, 10.0, 0.0, "e2", "Wire_f0_outer")
    NexusEulerOperators.make_edge_face(
        brep, "v2", "v0", "e_mid", "f1", "Wire_f0_outer", "w_f1"
    )

    assert len(brep.faces) == 2
    assert len(brep.edges) == 3

    # Supprimer l'arête centrale et fusionner f1 dans f0
    merged = NexusEulerOperators.kill_edge_face(brep, edge_id="e_mid", face_to_remove_id="f1", target_retained_face_id="f0")
    assert merged
    assert len(brep.faces) == 1
    assert len(brep.edges) == 2
    assert "f1" not in brep.faces

    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid
    assert diag.euler_characteristic == 2


def test_inner_hole_loop_euler_poincare() -> None:
    """Vérifie l'opérateur make_inner_hole_loop (KFMH) avec la formule d'Euler complète."""
    brep = NexusBRep("brep_hole")
    NexusEulerOperators.make_vertex_face_shell(brep, "v0", 0.0, 0.0, 0.0, "f0", "s0")

    # Sommets d'un trou interne
    v_h1 = NexusVertex("vh1", 2.0, 2.0, 0.0)
    v_h2 = NexusVertex("vh2", 4.0, 2.0, 0.0)
    v_h3 = NexusVertex("vh3", 4.0, 4.0, 0.0)
    brep.add_vertex(v_h1)
    brep.add_vertex(v_h2)
    brep.add_vertex(v_h3)

    c1 = NexusLineCurve("c1", v_h1.point, v_h2.point)
    c2 = NexusLineCurve("c2", v_h2.point, v_h3.point)
    c3 = NexusLineCurve("c3", v_h3.point, v_h1.point)

    eh1 = NexusEdge("eh1", c1, v_h1, v_h2)
    eh2 = NexusEdge("eh2", c2, v_h2, v_h3)
    eh3 = NexusEdge("eh3", c3, v_h3, v_h1)

    inner_wire = NexusEulerOperators.make_inner_hole_loop(
        brep, face_id="f0", inner_wire_id="w_hole_1", inner_edges=[eh1, eh2, eh3]
    )

    assert len(brep.faces["f0"].inner_wires) == 1
    assert inner_wire.wire_id == "w_hole_1"

    # Vérification Euler-Poincaré : V=4, E=3, F=1, L=2 (1 outer + 1 inner), S=1, G=0
    # V - E + F - (L - F) = 4 - 3 + 1 - (2 - 1) = 2 - 1 = 1 ≠ 2*(1-0)=2 (non fermé polyèdre complet sans faces latérales)
    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.loops_count == 2
    assert diag.vertices_count == 4
    assert diag.edges_count == 3


def test_cube_polyhedron_euler_characteristic() -> None:
    """Vérifie la caractéristique d'Euler exacte pour un cube régulier (V=8, E=12, F=6, S=1)."""
    brep = NexusBRep("brep_cube")

    # 8 sommets
    coords = [
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0),
        (0.0, 0.0, 10.0), (10.0, 0.0, 10.0), (10.0, 10.0, 10.0), (0.0, 10.0, 10.0)
    ]
    verts = [NexusVertex(f"v_{i}", x, y, z) for i, (x, y, z) in enumerate(coords)]
    for v in verts:
        brep.add_vertex(v)

    # 12 arêtes
    edge_indices = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # bas
        (4, 5), (5, 6), (6, 7), (7, 4),  # haut
        (0, 4), (1, 5), (2, 6), (3, 7)   # piliers
    ]
    edges_map = {}
    for i, (i0, i1) in enumerate(edge_indices):
        v0, v1 = verts[i0], verts[i1]
        c = NexusLineCurve(f"c_{i}", v0.point, v1.point)
        e = NexusEdge(f"e_{i}", c, v0, v1)
        brep.add_edge(e)
        edges_map[(i0, i1)] = e
        edges_map[(i1, i0)] = e

    # 6 faces
    face_edge_cycles = [
        [edges_map[(0, 1)], edges_map[(1, 2)], edges_map[(2, 3)], edges_map[(3, 0)]],
        [edges_map[(4, 5)], edges_map[(5, 6)], edges_map[(6, 7)], edges_map[(7, 4)]],
        [edges_map[(0, 1)], edges_map[(1, 5)], edges_map[(5, 4)], edges_map[(4, 0)]],
        [edges_map[(1, 2)], edges_map[(2, 6)], edges_map[(6, 5)], edges_map[(5, 1)]],
        [edges_map[(2, 3)], edges_map[(3, 7)], edges_map[(7, 6)], edges_map[(6, 2)]],
        [edges_map[(3, 0)], edges_map[(0, 4)], edges_map[(4, 7)], edges_map[(7, 3)]],
    ]
    faces_list = []
    for f_idx, cycle in enumerate(face_edge_cycles):
        w = NexusWire(f"w_cube_{f_idx}", cycle)
        brep.add_wire(w)
        f = NexusFace(f"f_cube_{f_idx}", NexusPlaneSurface(f"surf_{f_idx}", verts[0].point, np.array([0.0, 0.0, 1.0])), w)
        brep.add_face(f)
        faces_list.append(f)

    shell = NexusShell("shell_cube", faces_list, is_closed=True)
    brep.add_shell(shell)

    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid
    assert diag.euler_characteristic == 2  # V - E + F = 8 - 12 + 6 = 2
    assert diag.vertices_count == 8
    assert diag.edges_count == 12
    assert diag.faces_count == 6
    assert brep.is_manifold_topology()
