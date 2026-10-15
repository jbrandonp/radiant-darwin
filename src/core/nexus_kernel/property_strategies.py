"""
Stratégies Génératives Bornées (Hypothesis SOTA) pour le Kernel CAO NEXUS-3D.
Fournit des générateurs formels pour tester les invariants mathématiques et géométriques :
1. Topologies B-Rep et polyèdres 2-variétés (Formule d'Euler-Poincaré : V - E + F = 2).
2. Isométries spatiales rigides (Translations, Rotations).
3. Éléments finis tétraédriques et déplacements nodaux (Semi-définitude positive FEA U >= 0).
4. Arbres d'opérations booléennes CSG pour le fuzzing différentiel.

Typage statique strict sans `Any` et documentation exhaustive.
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Sequence, Union, Callable
from dataclasses import dataclass
import numpy as np
import hypothesis.strategies as st

from src.core.types import Vector3D, Point2D
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere
from src.core.nexus_kernel.brep_topology import (
    NexusBRep,
    NexusVertex,
    NexusEdge,
    NexusWire,
    NexusFace,
    NexusShell,
    NexusLineCurve,
    NexusPlaneSurface,
)
from src.core.nexus_kernel.euler_operators import NexusEulerOperators
from src.fea.nonlinear_fem import Tet10Element, BilinearPlasticMaterial


# -------------------------------------------------------------------------
# 1. Stratégies de Dimensions et Transformations Rigides Bornées
# -------------------------------------------------------------------------

@st.composite
def bounded_dimension(
    draw: st.DrawFn,
    min_value: float = 0.5,
    max_value: float = 150.0
) -> float:
    """
    Génère une dimension géométrique positive bornée non nulle.
    Évite les singularités numériques tout en explorant un spectre réaliste de CAO.
    """
    return float(draw(st.floats(
        min_value=min_value,
        max_value=max_value,
        allow_nan=False,
        allow_infinity=False
    )))


@st.composite
def bounded_translation_vector(
    draw: st.DrawFn,
    max_offset: float = 250.0
) -> Vector3D:
    """
    Génère un vecteur de translation cartésienne 3D dans un cube borné [-max, +max]^3.
    """
    tx = float(draw(st.floats(min_value=-max_offset, max_value=max_offset, allow_nan=False, allow_infinity=False)))
    ty = float(draw(st.floats(min_value=-max_offset, max_value=max_offset, allow_nan=False, allow_infinity=False)))
    tz = float(draw(st.floats(min_value=-max_offset, max_value=max_offset, allow_nan=False, allow_infinity=False)))
    return Vector3D(tx, ty, tz)


@st.composite
def bounded_rotation_angles(
    draw: st.DrawFn
) -> Tuple[float, float, float]:
    """
    Génère un triplet d'angles d'Euler (rx, ry, rz) en degrés dans [-180.0, 180.0].
    """
    rx = float(draw(st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)))
    ry = float(draw(st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)))
    rz = float(draw(st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)))
    return rx, ry, rz


# -------------------------------------------------------------------------
# 2. Stratégies de Solides 3D Bornés
# -------------------------------------------------------------------------

@st.composite
def bounded_solid_primitive(draw: st.DrawFn) -> Solid:
    """
    Génère une primitive géométrique solide étanche (boîte, cylindre ou sphère)
    avec des cotes aléatoires bornées.
    """
    shape_type = draw(st.sampled_from(["box", "cylinder", "sphere"]))
    if shape_type == "box":
        dx = draw(bounded_dimension(min_value=1.0, max_value=100.0))
        dy = draw(bounded_dimension(min_value=1.0, max_value=100.0))
        dz = draw(bounded_dimension(min_value=1.0, max_value=100.0))
        center = draw(st.booleans())
        return make_box(dx, dy, dz, center=center)
    elif shape_type == "cylinder":
        radius = draw(bounded_dimension(min_value=1.0, max_value=50.0))
        height = draw(bounded_dimension(min_value=1.0, max_value=100.0))
        center = draw(st.booleans())
        return make_cylinder(radius, height, center=center)
    else:
        radius = draw(bounded_dimension(min_value=1.0, max_value=50.0))
        return make_sphere(radius)


# -------------------------------------------------------------------------
# 3. Stratégies de Polyèdres 2-Variétés et Topologies B-Rep
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class PolyhedralTopology:
    """Description topologique d'un polyèdre fermé 2-variété."""
    name: str
    num_vertices: int
    num_edges: int
    num_faces: int
    genus: int
    shells: int

    @property
    def euler_characteristic(self) -> int:
        """Calcule V - E + F."""
        return self.num_vertices - self.num_edges + self.num_faces

    @property
    def expected_euler_characteristic(self) -> int:
        """Calcule 2 * (S - G)."""
        return 2 * (self.shells - self.genus)

    @property
    def is_euler_valid(self) -> bool:
        """Vérifie la stricte conformité à la formule d'Euler-Poincaré."""
        return self.euler_characteristic == self.expected_euler_characteristic


@st.composite
def bounded_2manifold_polyhedron(draw: st.DrawFn) -> PolyhedralTopology:
    """
    Génère une topologie polyédrique 2-variété fermée régulière ou semi-régulière
    (prismes polygonaux, pyramides, solides platoniciens) pour tester V - E + F = 2.
    """
    poly_family = draw(st.sampled_from(["prism", "pyramid", "platonic", "euler_solid"]))

    if poly_family == "prism":
        # Prisme à base n-gonale (n sommets en bas, n en haut)
        # V = 2n, E = 3n, F = n + 2
        # V - E + F = 2n - 3n + n + 2 = 2
        n = draw(st.integers(min_value=3, max_value=24))
        return PolyhedralTopology(
            name=f"Prisme_{n}_gonal",
            num_vertices=2 * n,
            num_edges=3 * n,
            num_faces=n + 2,
            genus=0,
            shells=1
        )

    elif poly_family == "pyramid":
        # Pyramide à base n-gonale (n sommets de base + 1 apex)
        # V = n + 1, E = 2n, F = n + 1
        # V - E + F = (n + 1) - 2n + (n + 1) = 2
        n = draw(st.integers(min_value=3, max_value=24))
        return PolyhedralTopology(
            name=f"Pyramide_{n}_gonale",
            num_vertices=n + 1,
            num_edges=2 * n,
            num_faces=n + 1,
            genus=0,
            shells=1
        )

    elif poly_family == "platonic":
        # Polyèdres réguliers convexes classiques
        platonic_data = [
            ("Tetraedre", 4, 6, 4),
            ("Cube", 8, 12, 6),
            ("Octaedre", 6, 12, 8),
            ("Dodecaedre", 20, 30, 12),
            ("Icosaedre", 12, 30, 20),
        ]
        chosen = draw(st.sampled_from(platonic_data))
        return PolyhedralTopology(
            name=chosen[0],
            num_vertices=chosen[1],
            num_edges=chosen[2],
            num_faces=chosen[3],
            genus=0,
            shells=1
        )

    else:
        # Solide de genre G >= 0 et S coques
        genus = draw(st.integers(min_value=0, max_value=3))
        shells = draw(st.integers(min_value=1, max_value=3))
        # Pour une triangulation quelconque de genre G et shells S :
        # Chaque face est un triangle -> 2E = 3F -> E = 3F/2
        # V - E + F = V - F/2 = 2*(S - G)
        # Choisissons F pair >= 4
        f_div_2 = draw(st.integers(min_value=4, max_value=50))
        num_faces = 2 * f_div_2
        num_edges = 3 * f_div_2
        num_vertices = 2 * (shells - genus) + f_div_2
        return PolyhedralTopology(
            name=f"Manifold_G{genus}_S{shells}",
            num_vertices=num_vertices,
            num_edges=num_edges,
            num_faces=num_faces,
            genus=genus,
            shells=shells
        )


@st.composite
def bounded_euler_brep_sequence(draw: st.DrawFn) -> NexusBRep:
    """
    Génère un B-Rep NEXUS valide construit exclusivement par des séquences
    d'opérateurs d'Euler atomiques (MVFS, MEV, MEF) garantissant l'invariant topologique.
    """
    brep = NexusBRep(f"Brep_Fuzz_{draw(st.integers(min_value=1000, max_value=9999))}")
    v0, f0, s0 = NexusEulerOperators.make_vertex_face_shell(
        brep, vertex_id="v0", x=0.0, y=0.0, z=0.0, face_id="f0", shell_id="s0"
    )

    num_steps = draw(st.integers(min_value=3, max_value=8))
    prev_v_id = "v0"
    vertices_chain: List[str] = ["v0"]

    for i in range(1, num_steps):
        v_id = f"v{i}"
        e_id = f"e{i}"
        x = float(draw(st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)))
        y = float(draw(st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)))
        z = float(draw(st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)))
        NexusEulerOperators.make_edge_vertex(
            brep,
            existing_vertex_id=prev_v_id,
            new_vertex_id=v_id,
            x=x,
            y=y,
            z=z,
            new_edge_id=e_id,
            wire_id="Wire_f0_outer"
        )
        vertices_chain.append(v_id)
        prev_v_id = v_id

    # Fermeture de la boucle avec MEF reliant le dernier sommet au premier
    if len(vertices_chain) >= 3:
        NexusEulerOperators.make_edge_face(
            brep,
            vertex_1_id=vertices_chain[-1],
            vertex_2_id=vertices_chain[0],
            new_edge_id=f"e_close",
            new_face_id="f1",
            wire_to_split_id="Wire_f0_outer",
            new_wire_id="Wire_f1_outer"
        )

    return brep


# -------------------------------------------------------------------------
# 4. Stratégies Éléments Finis (FEA Tet10 et Énergie de Déformation U >= 0)
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class Tet10Case:
    """Cas de test élément fini Tet10 avec matériau et champ de déplacement."""
    element: Tet10Element
    node_coords: np.ndarray  # Shape (10, 3)
    material: BilinearPlasticMaterial
    displacement_vector: np.ndarray  # Shape (30,)


@st.composite
def bounded_tet10_case(draw: st.DrawFn) -> Tet10Case:
    """
    Génère un tétraèdre quadratique Tet10 valide à volume strictement positif,
    avec matériau d'ingénierie et champ de déplacement aléatoire borné.
    """
    # 4 sommets principaux formant un tétraèdre bien conditionné
    scale = float(draw(st.floats(min_value=5.0, max_value=50.0, allow_nan=False, allow_infinity=False)))
    v0 = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    v1 = np.array([scale, 0.0, 0.0], dtype=np.float64)
    v2 = np.array([0.0, scale, 0.0], dtype=np.float64)
    v3 = np.array([0.0, 0.0, scale], dtype=np.float64)

    # Perturbation aléatoire modérée pour explorer différentes géométries
    noise = np.array(
        [[draw(st.floats(min_value=-0.2 * scale, max_value=0.2 * scale)) for _ in range(3)] for _ in range(4)],
        dtype=np.float64
    )
    v0 += noise[0]
    v1 += noise[1]
    v2 += noise[2]
    v3 += noise[3]

    # Vérification du déterminant volumique
    mat = np.ones((4, 4), dtype=np.float64)
    mat[:, :3] = np.vstack([v0, v1, v2, v3])
    det_val = np.linalg.det(mat)
    if abs(det_val) < 1e-4:
        v3[2] += scale * 0.5

    # 6 nœuds aux milieux d'arêtes
    edges_pairs = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
    main_verts = [v0, v1, v2, v3]
    mid_nodes = [0.5 * (main_verts[p[0]] + main_verts[p[1]]) for p in edges_pairs]

    node_coords = np.vstack(main_verts + mid_nodes)  # Shape (10, 3)

    # Paramètres matériau réalistes
    young = float(draw(st.floats(min_value=1e4, max_value=3.5e5, allow_nan=False, allow_infinity=False)))
    poisson = float(draw(st.floats(min_value=0.1, max_value=0.45, allow_nan=False, allow_infinity=False)))
    material = BilinearPlasticMaterial(
        youngs_modulus_mpa=young,
        poissons_ratio=poisson,
        yield_strength_mpa=250.0
    )

    # Déplacement nodale quelconque (30 DDL)
    disp = np.array(
        [draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)) for _ in range(30)],
        dtype=np.float64
    )

    elem = Tet10Element(element_id=1, node_indices=list(range(10)))
    return Tet10Case(elem, node_coords, material, disp)


# -------------------------------------------------------------------------
# 5. Stratégies pour le Fuzzing Différentiel CSG vs Quadrature
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class DifferentialCSGCase:
    """Cas de test différentiel combinant deux solides et une opération booléenne."""
    solid_a: Solid
    solid_b: Solid
    operation: str  # "UNION", "DIFFERENCE", "INTERSECTION"
    box_a_dims: Tuple[float, float, float]
    box_b_dims: Tuple[float, float, float]
    translation_b: Vector3D


@st.composite
def bounded_differential_csg_case(draw: st.DrawFn) -> DifferentialCSGCase:
    """
    Génère un cas de modélisation CSG entre deux solides aux dimensions et décalages bornés
    pour comparer les résultats de Manifold3D avec les quadratures géométriques alternatives.
    """
    w1 = draw(bounded_dimension(min_value=5.0, max_value=40.0))
    h1 = draw(bounded_dimension(min_value=5.0, max_value=40.0))
    d1 = draw(bounded_dimension(min_value=5.0, max_value=40.0))

    w2 = draw(bounded_dimension(min_value=5.0, max_value=40.0))
    h2 = draw(bounded_dimension(min_value=5.0, max_value=40.0))
    d2 = draw(bounded_dimension(min_value=5.0, max_value=40.0))

    trans_b = draw(bounded_translation_vector(max_offset=25.0))
    op = draw(st.sampled_from(["UNION", "DIFFERENCE", "INTERSECTION"]))

    solid_a = make_box(w1, h1, d1, center=True)
    solid_b = make_box(w2, h2, d2, center=True).translate(trans_b)

    return DifferentialCSGCase(
        solid_a=solid_a,
        solid_b=solid_b,
        operation=op,
        box_a_dims=(w1, h1, d1),
        box_b_dims=(w2, h2, d2),
        translation_b=trans_b
    )
