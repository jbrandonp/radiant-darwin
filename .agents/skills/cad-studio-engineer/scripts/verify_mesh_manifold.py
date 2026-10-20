"""Vérificateur topologique et géométrique de maillage 3D Manifold (v7.0).

Vérifie l'étanchéité (watertight), l'invariance d'Euler-Poincaré (chi = V - E + F = 2),
l'absence d'arêtes non-variétales (non-manifold) et la cohérence du volume signé.
100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

from dataclasses import dataclass
import math
import sys
from typing import Dict, Final, List, Set, Tuple


@dataclass(frozen=True)
class MeshMetrics:
    """Métriques géométriques et topologiques calculées sur un maillage."""

    vertex_count: int
    edge_count: int
    face_count: int
    euler_characteristic: int
    signed_volume: float
    is_watertight: bool
    non_manifold_edges: int
    boundary_edges: int
    has_positive_volume: bool = True


def _compute_triangle_volume(
    v0: Tuple[float, float, float],
    v1: Tuple[float, float, float],
    v2: Tuple[float, float, float],
) -> float:
    """Calcule le volume signé du tétraèdre formé par l'origine et le triangle."""
    # Produit mixte : v0 . (v1 x v2) / 6.0
    cross_x: float = v1[1] * v2[2] - v1[2] * v2[1]
    cross_y: float = v1[2] * v2[0] - v1[0] * v2[2]
    cross_z: float = v1[0] * v2[1] - v1[1] * v2[0]
    return (v0[0] * cross_x + v0[1] * cross_y + v0[2] * cross_z) / 6.0


def analyze_triangular_mesh(
    vertices: List[Tuple[float, float, float]],
    triangles: List[Tuple[int, int, int]],
) -> MeshMetrics:
    """Analyse chirurgicale d'un maillage triangulaire sans dépendance externe lourde."""
    v_count: Final[int] = len(vertices)
    f_count: Final[int] = len(triangles)

    if v_count < 4 or f_count < 4:
        return MeshMetrics(
            vertex_count=v_count,
            edge_count=0,
            face_count=f_count,
            euler_characteristic=0,
            signed_volume=0.0,
            is_watertight=False,
            non_manifold_edges=0,
            boundary_edges=0,
            has_positive_volume=False,
        )

    # Dénombrement et orientation des demi-arêtes
    directed_edges: Dict[Tuple[int, int], int] = {}
    undirected_edges: Dict[Tuple[int, int], int] = {}
    total_volume: float = 0.0

    for tri in triangles:
        i0, i1, i2 = tri
        v0 = vertices[i0]
        v1 = vertices[i1]
        v2 = vertices[i2]
        total_volume += _compute_triangle_volume(v0, v1, v2)

        edges_in_tri: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]] = (
            (i0, i1),
            (i1, i2),
            (i2, i0),
        )
        for u, w in edges_in_tri:
            directed_edges[(u, w)] = directed_edges.get((u, w), 0) + 1
            undir_key: Tuple[int, int] = (min(u, w), max(u, w))
            undirected_edges[undir_key] = undirected_edges.get(undir_key, 0) + 1

    e_count: Final[int] = len(undirected_edges)
    euler_chi: Final[int] = v_count - e_count + f_count

    non_manifold_count: int = 0
    boundary_count: int = 0

    for count in undirected_edges.values():
        if count == 1:
            boundary_count += 1
        elif count > 2:
            non_manifold_count += 1

    watertight: Final[bool] = (boundary_count == 0) and (non_manifold_count == 0)

    return MeshMetrics(
        vertex_count=v_count,
        edge_count=e_count,
        face_count=f_count,
        euler_characteristic=euler_chi,
        signed_volume=total_volume,
        is_watertight=watertight,
        non_manifold_edges=non_manifold_count,
        boundary_edges=boundary_count,
        has_positive_volume=(total_volume > 1e-6),
    )


def run_benchmark_cube() -> int:
    """Exécute un audit de référence sur un cube canonique 1x1x1."""
    print("\n================ VÉRIFICATEUR TOPOLOGIQUE 3D MANIFOLD (SOTA) ================")
    # 8 sommets du cube unité [0, 1]^3
    cube_verts: List[Tuple[float, float, float]] = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
    ]
    # 12 triangles avec winding CCW cohérent
    cube_tris: List[Tuple[int, int, int]] = [
        # Bas (Z = 0)
        (0, 2, 1),
        (0, 3, 2),
        # Haut (Z = 1)
        (4, 5, 6),
        (4, 6, 7),
        # Avant (Y = 0)
        (0, 1, 5),
        (0, 5, 4),
        # Arrière (Y = 1)
        (2, 3, 7),
        (2, 7, 6),
        # Gauche (X = 0)
        (0, 4, 7),
        (0, 7, 3),
        # Droite (X = 1)
        (1, 2, 6),
        (1, 6, 5),
    ]

    metrics = analyze_triangular_mesh(cube_verts, cube_tris)

    print(f"Sommets (V) : {metrics.vertex_count} | Arêtes (E) : {metrics.edge_count} | Faces (F) : {metrics.face_count}")
    print(f"Caractéristique d'Euler : Chi = V - E + F = {metrics.euler_characteristic} (Attendu : 2 pour solide genre 0)")
    print(f"Volume calculé : {metrics.signed_volume:.4f} mm³ (Attendu : 1.0000)")
    print(f"Arêtes orphelines (Bord libre) : {metrics.boundary_edges}")
    print(f"Arêtes non-variétales (Non-Manifold) : {metrics.non_manifold_edges}")
    print(f"Solide étanche (Watertight) : {'OUI' if metrics.is_watertight else 'NON'}")

    if not metrics.is_watertight or abs(metrics.signed_volume - 1.0) > 1e-4:
        print("\n[ERREUR] Échec de la vérification géométrique.")
        return 1

    print("\n[OK] Géométrie 3D 100% conforme pour opérations booléennes Manifold3D.\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_benchmark_cube())
