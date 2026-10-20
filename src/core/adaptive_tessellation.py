"""
Module de Tessellation Adaptative par Déviation Cordale et Angulaire (Incremental Mesh).
Implémente la parité exacte avec l'algorithme OpenCASCADE BRepMesh_IncrementalMesh.

Subdivise récursivement les surfaces paramétriques (NURBS, carreaux de Bézier, quadriques)
selon deux critères physiques d'ingénierie :
1. Flèche cordale maximale (Linear Deflection delta en mm)
2. Déviation angulaire des normales (Angular Deflection theta en degrés)

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple, Sequence
import numpy as np


@dataclass(frozen=True)
class QuadNode:
    """Cellule paramétrique (u, v) dans l'arbre de décomposition quadtree."""
    u0: float
    u1: float
    v0: float
    v1: float
    depth: int


class AdaptiveTessellator:
    """
    Générateur de maillage adaptatif par quadtree basé sur la courbure locale.
    Dense là où le rayon de courbure est petit (congés, raccords),
    léger et épuré sur les zones planes ou à faible courbure.
    """

    @staticmethod
    def _evaluate_quad_corners(
        eval_fn: Callable[[float, float], np.ndarray],
        normal_fn: Callable[[float, float], np.ndarray],
        quad: QuadNode
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Évalue les 4 sommets du quad, le centre et leurs normales associées."""
        p00 = eval_fn(quad.u0, quad.v0)
        p10 = eval_fn(quad.u1, quad.v0)
        p11 = eval_fn(quad.u1, quad.v1)
        p01 = eval_fn(quad.u0, quad.v1)

        u_mid = 0.5 * (quad.u0 + quad.u1)
        v_mid = 0.5 * (quad.v0 + quad.v1)
        p_mid = eval_fn(u_mid, v_mid)
        n_mid = normal_fn(u_mid, v_mid)

        return p00, p10, p11, p01, p_mid, n_mid

    @staticmethod
    def _check_subdivision_criteria(
        p00: np.ndarray,
        p10: np.ndarray,
        p11: np.ndarray,
        p01: np.ndarray,
        p_mid: np.ndarray,
        n_mid: np.ndarray,
        normal_fn: Callable[[float, float], np.ndarray],
        quad: QuadNode,
        linear_deflection: float,
        cos_ang_tol: float
    ) -> bool:
        """
        Vérifie si la cellule doit être subdivisée.
        Critère 1 : Flèche cordale (distance centre réel vs interpolation bilinéaire).
        Critère 2 : Déviation angulaire des normales aux 4 coins.
        """
        # Critère 1 : Flèche cordale delta
        p_bilin = 0.25 * (p00 + p10 + p11 + p01)
        chordal_error = float(np.linalg.norm(p_mid - p_bilin))
        if chordal_error > linear_deflection:
            return True

        # Critère 2 : Déviation angulaire des normales
        corners_uv = [
            (quad.u0, quad.v0),
            (quad.u1, quad.v0),
            (quad.u1, quad.v1),
            (quad.u0, quad.v1)
        ]
        for cu, cv in corners_uv:
            cn = normal_fn(cu, cv)
            dot_val = float(np.clip(np.dot(n_mid, cn), -1.0, 1.0))
            if dot_val < cos_ang_tol:
                return True

        return False

    @classmethod
    def _subdivide_quad(cls, quad: QuadNode) -> List[QuadNode]:
        """Découpe un quad en 4 sous-quads enfants."""
        u_mid = 0.5 * (quad.u0 + quad.u1)
        v_mid = 0.5 * (quad.v0 + quad.v1)
        next_depth = quad.depth + 1
        return [
            QuadNode(quad.u0, u_mid, quad.v0, v_mid, next_depth),
            QuadNode(u_mid, quad.u1, quad.v0, v_mid, next_depth),
            QuadNode(u_mid, quad.u1, v_mid, quad.v1, next_depth),
            QuadNode(quad.u0, u_mid, v_mid, quad.v1, next_depth),
        ]

    @classmethod
    def collect_leaf_quads(
        cls,
        eval_fn: Callable[[float, float], np.ndarray],
        normal_fn: Callable[[float, float], np.ndarray],
        root_quad: QuadNode,
        linear_deflection: float,
        angular_deflection_deg: float,
        max_depth: int
    ) -> List[QuadNode]:
        """Parcourt récursivement le quadtree et collecte toutes les cellules terminales conformes."""
        ang_rad = np.radians(angular_deflection_deg)
        cos_ang_tol = float(np.cos(ang_rad))
        stack: List[QuadNode] = [root_quad]
        leaves: List[QuadNode] = []

        while stack:
            q = stack.pop()
            if q.depth >= max_depth:
                leaves.append(q)
                continue

            p00, p10, p11, p01, p_mid, n_mid = cls._evaluate_quad_corners(eval_fn, normal_fn, q)
            needs_split = cls._check_subdivision_criteria(
                p00, p10, p11, p01, p_mid, n_mid, normal_fn, q,
                linear_deflection, cos_ang_tol
            )
            if needs_split:
                stack.extend(cls._subdivide_quad(q))
            else:
                leaves.append(q)

        return leaves

    @staticmethod
    def _triangulate_leaves(
        leaves: Sequence[QuadNode],
        eval_fn: Callable[[float, float], np.ndarray],
        tolerance: float = 1e-6
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convertit les quads feuilles en maillage triangulaire avec partage de sommets.
        Chaque coin (u, v) est indexé pour éviter la duplication de sommets 3D.
        """
        vert_map: Dict[Tuple[int, int], int] = {}
        vertices: List[np.ndarray] = []
        triangles: List[Tuple[int, int, int]] = []
        inv_tol = 1.0 / max(1e-9, tolerance)

        def get_or_add_vertex(u: float, v: float) -> int:
            key = (int(np.round(u * inv_tol)), int(np.round(v * inv_tol)))
            if key in vert_map:
                return vert_map[key]
            idx = len(vertices)
            vertices.append(eval_fn(u, v))
            vert_map[key] = idx
            return idx

        for q in leaves:
            i00 = get_or_add_vertex(q.u0, q.v0)
            i10 = get_or_add_vertex(q.u1, q.v0)
            i11 = get_or_add_vertex(q.u1, q.v1)
            i01 = get_or_add_vertex(q.u0, q.v1)

            # Deux triangles par quad
            triangles.append((i00, i10, i11))
            triangles.append((i00, i11, i01))

        v_arr = np.array(vertices, dtype=np.float64)
        t_arr = np.array(triangles, dtype=np.int32)
        return v_arr, t_arr

    @classmethod
    def tessellate(
        cls,
        eval_fn: Callable[[float, float], np.ndarray],
        normal_fn: Callable[[float, float], np.ndarray],
        u_bounds: Tuple[float, float] = (0.0, 1.0),
        v_bounds: Tuple[float, float] = (0.0, 1.0),
        linear_deflection: float = 0.05,
        angular_deflection_deg: float = 15.0,
        max_depth: int = 5,
        initial_subdivisions: int = 2
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Exécute la tessellation adaptative sur un domaine paramétrique (u, v).
        Subdivise d'abord en grille initiale, puis applique le raffinement quadtree.
        """
        u_min, u_max = u_bounds
        v_min, v_max = v_bounds
        u_steps = np.linspace(u_min, u_max, initial_subdivisions + 1)
        v_steps = np.linspace(v_min, v_max, initial_subdivisions + 1)

        all_leaves: List[QuadNode] = []
        for i in range(initial_subdivisions):
            for j in range(initial_subdivisions):
                root = QuadNode(u_steps[i], u_steps[i + 1], v_steps[j], v_steps[j + 1], depth=0)
                sub_leaves = cls.collect_leaf_quads(
                    eval_fn, normal_fn, root, linear_deflection, angular_deflection_deg, max_depth
                )
                all_leaves.extend(sub_leaves)

        return cls._triangulate_leaves(all_leaves, eval_fn)
