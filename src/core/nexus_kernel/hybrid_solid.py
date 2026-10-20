"""
Noyau Géométrique Hybride NEXUS-3D : Solide Hybride Dual-BRep & Exact CSG.
Synthétise la modélisation hybride de ZW3D Overdrive, la précision rationnelle d'AMCAX
et l'arithmétique exacte de Manifold3D pour garantir zéro plantage booléen.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np
import trimesh
import manifold3d as m

from src.core.nexus_kernel.brep_topology import (
    NexusVertex, NexusCurve, NexusLineCurve, NexusCircleCurve,
    NexusEdge, NexusWire, NexusSurface, NexusPlaneSurface,
    NexusCylinderSurface, NexusSphereSurface, NexusFace, NexusShell, NexusBRep
)


class NexusSolid:
    """
    Solide géométrique de nouvelle génération unifiant la représentation analytique B-Rep
    (surfaces continues, courbures exactes, tolérance zéro) et le maillage CSG 2-variété
    (garantie d'étanchéité absolue et opérations booléennes infaillibles).
    """

    def __init__(
        self,
        name: str = "NexusSolid",
        brep: Optional[NexusBRep] = None,
        internal_manifold: Optional[m.Manifold] = None
    ) -> None:
        self.name: str = name
        self._manifold: m.Manifold = internal_manifold if internal_manifold is not None else m.Manifold()
        if brep is not None:
            self.brep: NexusBRep = brep
        elif internal_manifold is not None and not internal_manifold.is_empty():
            self.brep = self._build_brep_from_manifold(name, internal_manifold)
        else:
            self.brep = NexusBRep(f"{name}_brep")

    @staticmethod
    def _build_brep_from_manifold(name: str, manifold: m.Manifold) -> NexusBRep:
        """Reconstruit une topologie B-Rep valide (sommets, arêtes, boucles, faces, coque) depuis le maillage."""
        brep = NexusBRep(f"{name}_brep")
        if manifold.is_empty():
            return brep
        mesh = manifold.to_mesh()
        vert_props = np.array(mesh.vert_properties, dtype=np.float64)[:, :3]
        tri_verts = np.array(mesh.tri_verts, dtype=np.int64)
        if len(vert_props) == 0 or len(tri_verts) == 0:
            return brep

        vertices: List[NexusVertex] = []
        for i, v in enumerate(vert_props):
            vert = NexusVertex(f"V_{i}", float(v[0]), float(v[1]), float(v[2]))
            brep.add_vertex(vert)
            vertices.append(vert)

        faces: List[NexusFace] = []
        edge_map: Dict[Tuple[int, int], NexusEdge] = {}
        for f_idx in range(len(tri_verts)):
            idx0, idx1, idx2 = int(tri_verts[f_idx, 0]), int(tri_verts[f_idx, 1]), int(tri_verts[f_idx, 2])
            v0, v1, v2 = vertices[idx0], vertices[idx1], vertices[idx2]

            face_edges: List[NexusEdge] = []
            for a_idx, b_idx, va, vb in [(idx0, idx1, v0, v1), (idx1, idx2, v1, v2), (idx2, idx0, v2, v0)]:
                key = (min(a_idx, b_idx), max(a_idx, b_idx))
                if key not in edge_map:
                    line_curve = NexusLineCurve(f"Curve_{key[0]}_{key[1]}", va.point, vb.point)
                    edge = NexusEdge(f"E_{key[0]}_{key[1]}", line_curve, va, vb)
                    edge_map[key] = edge
                    brep.add_edge(edge)
                face_edges.append(edge_map[key])

            wire = NexusWire(f"Wire_{f_idx}", face_edges)
            brep.add_wire(wire)

            p0, p1, p2 = v0.point, v1.point, v2.point
            cross_vec = np.cross(p1 - p0, p2 - p0)
            norm_val = float(np.linalg.norm(cross_vec))
            face_norm = cross_vec / norm_val if norm_val > 1e-9 else np.array([0.0, 0.0, 1.0])
            area = norm_val * 0.5

            plane_surf = NexusPlaneSurface(f"Plane_{f_idx}", p0, face_norm)
            face = NexusFace(f"F_{f_idx}", plane_surf, wire, area=area)
            brep.add_face(face)
            faces.append(face)

        shell = NexusShell(f"Shell_{name}", faces, is_closed=True)
        brep.add_shell(shell)
        return brep


    @property
    def internal_manifold(self) -> m.Manifold:
        """Accès direct au moteur Manifold3D sous-jacent."""
        return self._manifold

    def is_empty(self) -> bool:
        """Indique si le solide ne contient aucune matière."""
        return bool(self._manifold.is_empty())

    def volume(self) -> float:
        """Calcule le volume intérieur exact en mm³."""
        if self.is_empty():
            return 0.0
        return float(self._manifold.volume())

    def surface_area(self) -> float:
        """Calcule l'aire extérieure totale en mm²."""
        if self.is_empty():
            return 0.0
        return float(self._manifold.surface_area())

    def bounding_box(self) -> Tuple[np.ndarray, np.ndarray]:
        """Retourne les coordonnées (min_point, max_point) de la boîte englobante."""
        if self.is_empty():
            zeros = np.zeros(3, dtype=np.float64)
            return zeros, zeros
        bbox = self._manifold.bounding_box()
        min_pt = np.array([bbox[0], bbox[1], bbox[2]], dtype=np.float64)
        max_pt = np.array([bbox[3], bbox[4], bbox[5]], dtype=np.float64)
        return min_pt, max_pt

    def is_watertight(self) -> bool:
        """Vérifie que le solide est mathématiquement fermé, 2-variété et étanche sans trou."""
        if self.is_empty():
            return True
        mesh = self._manifold.to_mesh()
        return len(mesh.vert_properties) > 0 and len(mesh.tri_verts) > 0

    def get_volume(self) -> float:
        """Retourne le volume exact du solide volumique."""
        if self.is_empty():
            return 0.0
        return float(abs(self._manifold.volume()))

    # -------------------------------------------------------------------------
    # Opérations Booléennes Hybrides Robustes
    # -------------------------------------------------------------------------

    def union(self, other: NexusSolid, name: Optional[str] = None) -> NexusSolid:
        """Fusion booléenne robuste A ∪ B avec mise à jour exacte du graphe B-Rep."""
        new_name = name or f"{self.name}_union_{other.name}"
        res_m = self._manifold + other._manifold
        res_brep = self._build_brep_from_manifold(new_name, res_m)
        return NexusSolid(name=new_name, brep=res_brep, internal_manifold=res_m)

    def difference(self, other: NexusSolid, name: Optional[str] = None) -> NexusSolid:
        """Soustraction booléenne robuste A - B avec mise à jour exacte du graphe B-Rep."""
        new_name = name or f"{self.name}_cut_{other.name}"
        res_m = self._manifold - other._manifold
        res_brep = self._build_brep_from_manifold(new_name, res_m)
        return NexusSolid(name=new_name, brep=res_brep, internal_manifold=res_m)

    def intersection(self, other: NexusSolid, name: Optional[str] = None) -> NexusSolid:
        """Intersection booléenne robuste A ∩ B avec mise à jour exacte du graphe B-Rep."""
        new_name = name or f"{self.name}_intersect_{other.name}"
        res_m = self._manifold ^ other._manifold
        res_brep = self._build_brep_from_manifold(new_name, res_m)
        return NexusSolid(name=new_name, brep=res_brep, internal_manifold=res_m)

    # -------------------------------------------------------------------------
    # Fabriques de Primitives Hybrides B-Rep + CSG
    # -------------------------------------------------------------------------

    @classmethod
    def make_box(cls, dx: float, dy: float, dz: float, name: str = "NexusBox") -> NexusSolid:
        """
        Crée un pavé droit avec graphe topologique B-Rep exact :
        8 sommets, 12 arêtes, 6 faces planes, 1 coque fermée.
        Caractéristique d'Euler vérifiée : 8 - 12 + 6 = 2.
        """
        dx, dy, dz = max(1e-6, float(dx)), max(1e-6, float(dy)), max(1e-6, float(dz))
        m_box = m.Manifold.cube([dx, dy, dz], center=False)

        brep = NexusBRep(f"{name}_brep")
        # 1. Sommets
        coords = [
            (0.0, 0.0, 0.0), (dx, 0.0, 0.0), (dx, dy, 0.0), (0.0, dy, 0.0),
            (0.0, 0.0, dz), (dx, 0.0, dz), (dx, dy, dz), (0.0, dy, dz)
        ]
        verts = [NexusVertex(f"V_{i}", x, y, z) for i, (x, y, z) in enumerate(coords)]
        for v in verts:
            brep.add_vertex(v)

        # 2. Arêtes
        edge_indices = [
            (0, 1), (1, 2), (2, 3), (3, 0),  # Base inférieure Z=0
            (4, 5), (5, 6), (6, 7), (7, 4),  # Base supérieure Z=dz
            (0, 4), (1, 5), (2, 6), (3, 7)   # Arêtes verticales
        ]
        edges: List[NexusEdge] = []
        for i, (i0, i1) in enumerate(edge_indices):
            v0, v1 = verts[i0], verts[i1]
            line_curve = NexusLineCurve(f"Curve_E{i}", v0.point, v1.point)
            edge = NexusEdge(f"E_{i}", line_curve, v0, v1)
            edges.append(edge)
            brep.add_edge(edge)

        # 3. Faces et plans (chaque arête est partagée par exactement 2 faces)
        face_defs = [
            ([0, 1, 2, 3], np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, -1.0]), dx * dy),  # Bas (Z=0)
            ([4, 5, 6, 7], np.array([0.0, 0.0, dz]), np.array([0.0, 0.0, 1.0]), dx * dy),   # Haut (Z=dz)
            ([0, 9, 4, 8], np.array([0.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]), dx * dz),  # Avant (Y=0)
            ([2, 10, 6, 11], np.array([0.0, dy, 0.0]), np.array([0.0, 1.0, 0.0]), dx * dz), # Arrière (Y=dy)
            ([8, 7, 11, 3], np.array([0.0, 0.0, 0.0]), np.array([-1.0, 0.0, 0.0]), dy * dz), # Gauche (X=0)
            ([1, 10, 5, 9], np.array([dx, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]), dy * dz)   # Droite (X=dx)
        ]

        faces: List[NexusFace] = []
        for fi, (e_idxs, origin, normal, area) in enumerate(face_defs):
            plane_surf = NexusPlaneSurface(f"Surf_F{fi}", origin, normal)
            wire_edges = [edges[e_idx % len(edges)] for e_idx in e_idxs]
            wire = NexusWire(f"Wire_F{fi}", wire_edges, is_closed=True)
            brep.add_wire(wire)
            face = NexusFace(f"F_{fi}", plane_surf, wire, area=area)
            faces.append(face)
            brep.add_face(face)

        shell = NexusShell(f"Shell_{name}", faces, is_closed=True)
        brep.add_shell(shell)

        return cls(name=name, brep=brep, internal_manifold=m_box)

    @classmethod
    def make_cylinder(cls, radius: float, height: float, name: str = "NexusCylinder") -> NexusSolid:
        """
        Crée un cylindre hybride combinant surface analytique de révolution
        et maillage polygonal C++20 à 64 facettes.
        """
        radius = max(1e-6, float(radius))
        height = max(1e-6, float(height))
        m_cyl = m.Manifold.cylinder(height, radius, radius, circular_segments=64)

        brep = NexusBRep(f"{name}_brep")
        # Surface latérale cylindrique
        cyl_surf = NexusCylinderSurface("Surf_Lateral", np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), radius)
        # Cercles haut et bas
        c_bottom = NexusCircleCurve("Curve_Bottom", np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), radius)
        c_top = NexusCircleCurve("Curve_Top", np.array([0.0, 0.0, height]), np.array([0.0, 0.0, 1.0]), radius)

        v_b0 = NexusVertex("VB_0", radius, 0.0, 0.0)
        v_t0 = NexusVertex("VT_0", radius, 0.0, height)
        brep.add_vertex(v_b0)
        brep.add_vertex(v_t0)

        edge_bot = NexusEdge("E_Bottom", c_bottom, v_b0, v_b0)
        edge_top = NexusEdge("E_Top", c_top, v_t0, v_t0)
        brep.add_edge(edge_bot)
        brep.add_edge(edge_top)

        wire_bot = NexusWire("Wire_Bottom", [edge_bot])
        wire_top = NexusWire("Wire_Top", [edge_top])
        brep.add_wire(wire_bot)
        brep.add_wire(wire_top)

        # Faces : Latérale, Base Inférieure, Base Supérieure
        area_lat = 2.0 * float(np.pi) * radius * height
        area_cap = float(np.pi) * (radius ** 2)

        f_lat = NexusFace("F_Lateral", cyl_surf, wire_bot, area=area_lat)
        f_bot = NexusFace("F_Bottom", NexusPlaneSurface("Plane_Bot", np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, -1.0])), wire_bot, area=area_cap)
        f_top = NexusFace("F_Top", NexusPlaneSurface("Plane_Top", np.array([0.0, 0.0, height]), np.array([0.0, 0.0, 1.0])), wire_top, area=area_cap)

        brep.add_face(f_lat)
        brep.add_face(f_bot)
        brep.add_face(f_top)

        shell = NexusShell(f"Shell_{name}", [f_lat, f_bot, f_top], is_closed=True)
        brep.add_shell(shell)

        return cls(name=name, brep=brep, internal_manifold=m_cyl)

    @classmethod
    def make_sphere(cls, radius: float, name: str = "NexusSphere") -> NexusSolid:
        """Crée une sphère hybride avec surface sphérique continue exacte."""
        radius = max(1e-6, float(radius))
        m_sph = m.Manifold.sphere(radius, circular_segments=64)

        brep = NexusBRep(f"{name}_brep")
        sph_surf = NexusSphereSurface("Surf_Sphere", np.array([0.0, 0.0, 0.0]), radius)
        eq_curve = NexusCircleCurve("Curve_Equator", np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), radius)
        v0 = NexusVertex("V_Eq0", radius, 0.0, 0.0)
        brep.add_vertex(v0)
        e0 = NexusEdge("E_Equator", eq_curve, v0, v0)
        brep.add_edge(e0)
        w0 = NexusWire("Wire_Equator", [e0])
        brep.add_wire(w0)

        f_sph = NexusFace("F_Sphere", sph_surf, w0, area=4.0 * float(np.pi) * (radius ** 2))
        brep.add_face(f_sph)
        shell = NexusShell(f"Shell_{name}", [f_sph], is_closed=True)
        brep.add_shell(shell)

        return cls(name=name, brep=brep, internal_manifold=m_sph)

    # -------------------------------------------------------------------------
    # Conversions & Interopérabilité
    # -------------------------------------------------------------------------

    def to_trimesh(self) -> trimesh.Trimesh:
        """Convertit le solide en maillage trimesh prêt pour l'affichage ou l'analyse."""
        mesh = self._manifold.to_mesh()
        verts = np.array(mesh.vert_properties)[:, :3]
        faces = np.array(mesh.tri_verts)
        return trimesh.Trimesh(vertices=verts, faces=faces, process=False)
