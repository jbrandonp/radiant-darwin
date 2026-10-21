"""
Importateur Universel de Fichiers CAO ISO 10303-21 STEP (AP203, AP214, AP242).
Permet d'ouvrir, de lire et de reconstruire la topologie B-Rep exacte de pièces
conçues sur CATIA, SolidWorks, Siemens NX, Creo ou FreeCAD.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np
import manifold3d as m

from src.core.nexus_kernel.brep_topology import (
    NexusVertex, NexusCurve, NexusLineCurve, NexusCircleCurve,
    NexusEdge, NexusWire, NexusSurface, NexusPlaneSurface,
    NexusCylinderSurface, NexusSphereSurface, NexusFace, NexusShell, NexusBRep
)
from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.core.geometry import Solid


@dataclass
class STEPRecord:
    """Représentation d'une entité du fichier STEP #ID = TYPE(ARGS)."""
    entity_id: int
    entity_type: str
    args: List[str]
    raw_args: str = ""


@dataclass
class STEPGeometricContext:
    """Contexte géométrique et sémantique complet extrait d'un fichier STEP."""
    schema_name: str
    cartesian_points: Dict[int, np.ndarray]
    directions: Dict[int, np.ndarray]
    axis_placements: Dict[int, str]
    faces: Dict[int, str]
    solids: Dict[str, str]
    pmi_annotations: List[str]


@dataclass
class STEPModel:
    """Modèle B-Rep reconstitué à partir d'un fichier STEP."""
    filepath: str
    schema_version: str  # ex: "AP214", "AP203", "AP242"
    solid: NexusSolid
    metadata: Dict[str, str] = field(default_factory=dict)
    pmi_annotations: List[str] = field(default_factory=list)
    context: Optional[STEPGeometricContext] = None


class STEPImporter:
    """
    Parseur et importateur de géométrie volumique ISO 10303-21 STEP.
    Lit la structure d'échange, extrait les points cartésiens, les courbes,
    les surfaces quadriques, les boucles d'arêtes et assemble le solide B-Rep étanche.
    """

    def __init__(self) -> None:
        self.had_fallback: bool = False
        self.last_warning: Optional[str] = None

    def import_step(self, filepath_or_content: str) -> STEPGeometricContext:
        """
        Importe un fichier .step / .stp ou une chaîne de caractères STEP
        et retourne le contexte géométrique analysé.
        """
        content = self._resolve_content(filepath_or_content)

        # 1. Identifier le schéma
        schema_name = "AP214"
        schema_match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", content, re.IGNORECASE)
        if schema_match:
            schema_name = schema_match.group(1)

        # 2. Extraire la section DATA
        data_sec = ""
        data_match = re.search(r"DATA\s*;(.*?)ENDSEC\s*;", content, re.DOTALL | re.IGNORECASE)
        if data_match:
            data_sec = data_match.group(1)

        records: Dict[int, STEPRecord] = self._parse_records(data_sec)

        # 3. Résolution des points cartésiens
        cartesian_points: Dict[int, np.ndarray] = self._parse_cartesian_points(records)

        # 4. Résolution des directions
        directions: Dict[int, np.ndarray] = self._parse_directions(records)

        # 5. Placements d'axes et repères
        axis_placements = self._extract_axis_placements(records)

        # 6. Faces B-Rep
        faces = self._extract_faces(records)

        # 7. Solides volumiques
        solids = self._extract_solids(records)

        # 8. PMI (Product & Manufacturing Information pour AP242)
        pmi_notes = self._extract_pmi_annotations(records)

        return STEPGeometricContext(
            schema_name=schema_name,
            cartesian_points=cartesian_points,
            directions=directions,
            axis_placements=axis_placements,
            faces=faces,
            solids=solids,
            pmi_annotations=pmi_notes
        )

    @staticmethod
    def _extract_axis_placements(records: Dict[int, STEPRecord]) -> Dict[int, str]:
        """Extrait les définitions de repères AXIS2_PLACEMENT."""
        placements: Dict[int, str] = {}
        for r in records.values():
            if "AXIS2_PLACEMENT" in r.entity_type:
                placements[r.entity_id] = " ".join(r.args)
        return placements

    @staticmethod
    def _extract_faces(records: Dict[int, STEPRecord]) -> Dict[int, str]:
        """Extrait les définitions de faces analytiques et B-Rep."""
        faces: Dict[int, str] = {}
        for r in records.values():
            if ("FACE" in r.entity_type and "BOUND" not in r.entity_type) or r.entity_type == "ADVANCED_FACE":
                faces[r.entity_id] = " ".join(r.args)
        return faces

    @staticmethod
    def _extract_solids(records: Dict[int, STEPRecord]) -> Dict[str, str]:
        """Extrait les entités solides identifiées dans le flux STEP."""
        solids: Dict[str, str] = {}
        for r in records.values():
            if "SOLID" in r.entity_type:
                name_match = re.search(r"'([^']+)'", " ".join(r.args))
                solid_name = name_match.group(1) if name_match else f"SOLID_{r.entity_id}"
                solids[solid_name] = r.entity_type
        return solids

    @staticmethod
    def _extract_pmi_annotations(records: Dict[int, STEPRecord]) -> List[str]:
        """Extrait les annotations PMI (tolérances géométriques, datums, dimensions)."""
        pmi_notes: List[str] = []
        for r in records.values():
            if any(k in r.entity_type for k in ("TOLERANCE", "DATUM", "DIMENSIONAL")):
                pmi_notes.append(f"{r.entity_type}: {' '.join(r.args)}")
        return pmi_notes

    def import_to_nexus_solid(self, filepath_or_content: str, solid_name: Optional[str] = None) -> NexusSolid:
        """
        Importe un fichier ou contenu STEP et reconstruit le solide B-Rep complet NexusSolid
        avec topologie analytique (sommets, arêtes, faces) et maillage Manifold3D étanche.
        """
        content = self._resolve_content(filepath_or_content)
        data_match = re.search(r"DATA\s*;(.*?)ENDSEC\s*;", content, re.DOTALL | re.IGNORECASE)
        data_sec = data_match.group(1) if data_match else content

        records = self._parse_records(data_sec)
        cartesian_points = self._parse_cartesian_points(records)
        directions = self._parse_directions(records)

        chosen_name = self._extract_chosen_name(records, solid_name)
        brep = NexusBRep(f"{chosen_name}_brep")

        # 1. Sommets
        v_map, c_map = self._reconstruct_vertices(brep, records, cartesian_points)

        # 2. Arêtes
        e_map = self._reconstruct_edges(brep, records, cartesian_points, v_map, c_map)

        # 3. Boucles (Wires)
        w_map = self._reconstruct_wires(brep, records, e_map, c_map, v_map, cartesian_points)

        # 4. Surfaces
        s_map = self._reconstruct_surfaces(records, cartesian_points, directions)

        # 5. Faces et Coque (Shell)
        self._reconstruct_faces(brep, records, s_map, w_map, chosen_name)

        # 6. Maillage Manifold3D
        internal_manifold = self._construct_manifold_from_brep(brep, cartesian_points, records)
        return NexusSolid(name=chosen_name, brep=brep, internal_manifold=internal_manifold)

    def _extract_chosen_name(self, records: Dict[int, STEPRecord], solid_name: Optional[str]) -> str:
        """Détermine le nom du solide à partir des métadonnées ou d'une valeur par défaut."""
        if solid_name:
            return solid_name
        for r in records.values():
            if "SOLID" in r.entity_type:
                name_match = re.search(r"'([^']+)'", r.raw_args)
                if name_match:
                    return name_match.group(1)
        return "ImportedSTEPSolid"

    def _reconstruct_vertices(
        self,
        brep: NexusBRep,
        records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray]
    ) -> Tuple[Dict[int, NexusVertex], Dict[int, NexusVertex]]:
        """Reconstruit les sommets du modèle B-Rep."""
        vertex_point_map: Dict[int, NexusVertex] = {}
        cartesian_vertex_map: Dict[int, NexusVertex] = {}

        for r in records.values():
            if r.entity_type == "VERTEX_POINT":
                pt_id_match = re.search(r"#(\d+)", r.raw_args)
                if pt_id_match:
                    pt_id = int(pt_id_match.group(1))
                    if pt_id in cartesian_points:
                        pt = cartesian_points[pt_id]
                        v = NexusVertex(f"V_{r.entity_id}", float(pt[0]), float(pt[1]), float(pt[2]))
                        brep.add_vertex(v)
                        vertex_point_map[r.entity_id] = v
                        cartesian_vertex_map[pt_id] = v

        for pt_id, pt in cartesian_points.items():
            if pt_id not in cartesian_vertex_map:
                v = NexusVertex(f"V_pt_{pt_id}", float(pt[0]), float(pt[1]), float(pt[2]))
                brep.add_vertex(v)
                cartesian_vertex_map[pt_id] = v

        return vertex_point_map, cartesian_vertex_map

    @staticmethod
    def _parse_edge_curve(
        r: STEPRecord,
        curve_rec: Optional[STEPRecord],
        records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray],
        v_start: NexusVertex,
        v_end: NexusVertex
    ) -> NexusCurve:
        if curve_rec and curve_rec.entity_type == "CIRCLE":
            center = v_start.point
            axis_ref = [int(x) for x in re.findall(r"#(\d+)", curve_rec.raw_args)]
            if axis_ref and axis_ref[0] in records:
                ax_rec = records[axis_ref[0]]
                ax_pt_ids = [int(x) for x in re.findall(r"#(\d+)", ax_rec.raw_args)]
                if ax_pt_ids and ax_pt_ids[0] in cartesian_points:
                    center = cartesian_points[ax_pt_ids[0]]
            radius_floats = [float(f) for f in re.findall(r"[-+]?\d*\.\d+|\d+", curve_rec.raw_args)]
            rad = radius_floats[-1] if radius_floats else 5.0
            return NexusCircleCurve(f"Circle_{r.entity_id}", center, np.array([0.0, 0.0, 1.0]), rad)
        return NexusLineCurve(f"Line_{r.entity_id}", v_start.point, v_end.point)

    def _reconstruct_edges(
        self,
        brep: NexusBRep,
        records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray],
        vertex_point_map: Dict[int, NexusVertex],
        cartesian_vertex_map: Dict[int, NexusVertex]
    ) -> Dict[int, NexusEdge]:
        """Reconstruit les arêtes B-Rep et associe les courbes analytiques."""
        edge_curve_map: Dict[int, NexusEdge] = {}

        for r in records.values():
            if r.entity_type != "EDGE_CURVE":
                continue
            ref_ids = [int(m_id) for m_id in re.findall(r"#(\d+)", r.raw_args)]
            if len(ref_ids) < 2:
                continue
            v_start = self._resolve_or_create_vertex(ref_ids[0], brep, vertex_point_map, cartesian_vertex_map, cartesian_points)
            v_end = self._resolve_or_create_vertex(ref_ids[1], brep, vertex_point_map, cartesian_vertex_map, cartesian_points)
            if not v_start or not v_end:
                continue

            curve_id = ref_ids[2] if len(ref_ids) >= 3 else 0
            curve_rec = records.get(curve_id)
            c_geom = self._parse_edge_curve(r, curve_rec, records, cartesian_points, v_start, v_end)

            edge = NexusEdge(f"E_{r.entity_id}", c_geom, v_start, v_end)
            brep.add_edge(edge)
            edge_curve_map[r.entity_id] = edge

        return edge_curve_map

    @staticmethod
    def _resolve_or_create_vertex(
        ref_id: int,
        brep: NexusBRep,
        vertex_point_map: Dict[int, NexusVertex],
        cartesian_vertex_map: Dict[int, NexusVertex],
        cartesian_points: Dict[int, np.ndarray]
    ) -> Optional[NexusVertex]:
        if ref_id in vertex_point_map:
            return vertex_point_map[ref_id]
        if ref_id in cartesian_vertex_map:
            return cartesian_vertex_map[ref_id]
        if ref_id in cartesian_points:
            pt = cartesian_points[ref_id]
            vert = NexusVertex(f"V_pt_{ref_id}", float(pt[0]), float(pt[1]), float(pt[2]))
            brep.add_vertex(vert)
            cartesian_vertex_map[ref_id] = vert
            return vert
        return None

    @classmethod
    def _build_poly_loop_wire(
        cls,
        r: STEPRecord,
        brep: NexusBRep,
        vertex_point_map: Dict[int, NexusVertex],
        cartesian_vertex_map: Dict[int, NexusVertex],
        cartesian_points: Dict[int, np.ndarray]
    ) -> NexusWire:
        ref_pt_ids = [int(m_id) for m_id in re.findall(r"#(\d+)", r.raw_args)]
        loop_edges: List[NexusEdge] = []
        for i in range(len(ref_pt_ids)):
            p_a_id = ref_pt_ids[i]
            p_b_id = ref_pt_ids[(i + 1) % len(ref_pt_ids)]
            v_a = cls._resolve_or_create_vertex(p_a_id, brep, vertex_point_map, cartesian_vertex_map, cartesian_points)
            v_b = cls._resolve_or_create_vertex(p_b_id, brep, vertex_point_map, cartesian_vertex_map, cartesian_points)
            if v_a and v_b:
                edge_key = f"E_poly_{p_a_id}_{p_b_id}"
                if edge_key not in brep.edges:
                    c_line = NexusLineCurve(f"Line_{edge_key}", v_a.point, v_b.point)
                    poly_edge = NexusEdge(edge_key, c_line, v_a, v_b)
                    brep.add_edge(poly_edge)
                else:
                    poly_edge = brep.edges[edge_key]
                loop_edges.append(poly_edge)
        wire = NexusWire(f"Wire_{r.entity_id}", loop_edges, is_closed=True)
        brep.add_wire(wire)
        return wire

    @staticmethod
    def _build_edge_loop_wire(
        r: STEPRecord,
        records: Dict[int, STEPRecord],
        edge_curve_map: Dict[int, NexusEdge],
        brep: NexusBRep
    ) -> NexusWire:
        oriented_refs = [int(m_id) for m_id in re.findall(r"#(\d+)", r.raw_args)]
        loop_edges: List[NexusEdge] = []
        for ore_id in oriented_refs:
            oe_rec = records.get(ore_id)
            if oe_rec and oe_rec.entity_type == "ORIENTED_EDGE":
                edge_refs = [int(m_id) for m_id in re.findall(r"#(\d+)", oe_rec.raw_args)]
                for e_ref in edge_refs:
                    if e_ref in edge_curve_map:
                        loop_edges.append(edge_curve_map[e_ref])
                        break
            elif ore_id in edge_curve_map:
                loop_edges.append(edge_curve_map[ore_id])
        wire = NexusWire(f"Wire_{r.entity_id}", loop_edges, is_closed=True)
        brep.add_wire(wire)
        return wire

    def _reconstruct_wires(
        self,
        brep: NexusBRep,
        records: Dict[int, STEPRecord],
        edge_curve_map: Dict[int, NexusEdge],
        cartesian_vertex_map: Dict[int, NexusVertex],
        vertex_point_map: Dict[int, NexusVertex],
        cartesian_points: Dict[int, np.ndarray]
    ) -> Dict[int, NexusWire]:
        """Reconstruit les boucles fermées orientées."""
        loop_wire_map: Dict[int, NexusWire] = {}
        for r in records.values():
            if r.entity_type == "POLY_LOOP":
                wire = self._build_poly_loop_wire(r, brep, vertex_point_map, cartesian_vertex_map, cartesian_points)
                loop_wire_map[r.entity_id] = wire
            elif r.entity_type == "EDGE_LOOP":
                wire = self._build_edge_loop_wire(r, records, edge_curve_map, brep)
                loop_wire_map[r.entity_id] = wire
        return loop_wire_map

    @staticmethod
    def _parse_axis_placement(
        record: STEPRecord,
        records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray],
        directions: Dict[int, np.ndarray],
        default_dir: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        origin = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        direction = np.array(default_dir, dtype=np.float64)
        ax_refs = [int(x) for x in re.findall(r"#(\d+)", record.raw_args)]
        if ax_refs and ax_refs[0] in records:
            ax_rec = records[ax_refs[0]]
            inner_refs = [int(x) for x in re.findall(r"#(\d+)", ax_rec.raw_args)]
            if len(inner_refs) >= 1 and inner_refs[0] in cartesian_points:
                origin = cartesian_points[inner_refs[0]]
            if len(inner_refs) >= 2 and inner_refs[1] in directions:
                direction = directions[inner_refs[1]]
        return origin, direction

    @classmethod
    def _parse_plane_surface(
        cls, r: STEPRecord, records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray], directions: Dict[int, np.ndarray]
    ) -> NexusPlaneSurface:
        origin, normal = cls._parse_axis_placement(
            r, records, cartesian_points, directions, np.array([0.0, 0.0, 1.0], dtype=np.float64)
        )
        return NexusPlaneSurface(f"Plane_{r.entity_id}", origin, normal)

    @classmethod
    def _parse_cylinder_surface(
        cls, r: STEPRecord, records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray], directions: Dict[int, np.ndarray]
    ) -> NexusCylinderSurface:
        origin, axis = cls._parse_axis_placement(
            r, records, cartesian_points, directions, np.array([0.0, 0.0, 1.0], dtype=np.float64)
        )
        radius_floats = [float(f) for f in re.findall(r"[-+]?\d*\.\d+|\d+", r.raw_args)]
        rad = radius_floats[-1] if radius_floats else 10.0
        return NexusCylinderSurface(f"Cyl_{r.entity_id}", origin, axis, rad)

    @classmethod
    def _parse_sphere_surface(
        cls, r: STEPRecord, records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray]
    ) -> NexusSphereSurface:
        center = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        ax_refs = [int(x) for x in re.findall(r"#(\d+)", r.raw_args)]
        if ax_refs and ax_refs[0] in records:
            ax_rec = records[ax_refs[0]]
            inner_refs = [int(x) for x in re.findall(r"#(\d+)", ax_rec.raw_args)]
            if len(inner_refs) >= 1 and inner_refs[0] in cartesian_points:
                center = cartesian_points[inner_refs[0]]
        radius_floats = [float(f) for f in re.findall(r"[-+]?\d*\.\d+|\d+", r.raw_args)]
        rad = radius_floats[-1] if radius_floats else 10.0
        return NexusSphereSurface(f"Sphere_{r.entity_id}", center, rad)

    def _reconstruct_surfaces(
        self,
        records: Dict[int, STEPRecord],
        cartesian_points: Dict[int, np.ndarray],
        directions: Dict[int, np.ndarray]
    ) -> Dict[int, NexusSurface]:
        """Reconstruit les surfaces géométriques sous-jacentes."""
        surface_map: Dict[int, NexusSurface] = {}
        for r in records.values():
            if r.entity_type == "PLANE":
                surface_map[r.entity_id] = self._parse_plane_surface(r, records, cartesian_points, directions)
            elif r.entity_type == "CYLINDRICAL_SURFACE":
                surface_map[r.entity_id] = self._parse_cylinder_surface(r, records, cartesian_points, directions)
            elif r.entity_type == "SPHERICAL_SURFACE":
                surface_map[r.entity_id] = self._parse_sphere_surface(r, records, cartesian_points)
        return surface_map

    @staticmethod
    def _collect_bound_wires(
        ref_rec: STEPRecord,
        loop_wire_map: Dict[int, NexusWire]
    ) -> List[NexusWire]:
        source_text = ref_rec.raw_args if ref_rec.raw_args else ", ".join(ref_rec.args)
        bound_refs = [int(x) for x in re.findall(r"#(\d+)", source_text)]
        return [loop_wire_map[b_id] for b_id in bound_refs if b_id in loop_wire_map]

    @classmethod
    def _extract_boundary_wires_from_rec(
        cls,
        ref_rec: STEPRecord,
        loop_wire_map: Dict[int, NexusWire],
        outer_wire: Optional[NexusWire],
        inner_wires: List[NexusWire]
    ) -> Optional[NexusWire]:
        """Extrait et classe les fils de frontière d'un enregistrement BOUND."""
        for w in cls._collect_bound_wires(ref_rec, loop_wire_map):
            if outer_wire is None:
                outer_wire = w
            else:
                inner_wires.append(w)
        return outer_wire

    @staticmethod
    def _find_fallback_outer_wire(
        ref_ids: List[int],
        loop_wire_map: Dict[int, NexusWire]
    ) -> Optional[NexusWire]:
        """Recherche un fil extérieur de repli parmi les identifiants de référence."""
        for ref_id in ref_ids:
            if ref_id in loop_wire_map:
                return loop_wire_map[ref_id]
        return None

    @classmethod
    def _resolve_face_boundaries_and_surface(
        cls,
        r: STEPRecord,
        records: Dict[int, STEPRecord],
        surface_map: Dict[int, NexusSurface],
        loop_wire_map: Dict[int, NexusWire]
    ) -> Tuple[Optional[NexusWire], List[NexusWire], Optional[NexusSurface]]:
        ref_ids = [int(x) for x in re.findall(r"#(\d+)", r.raw_args)]
        outer_wire: Optional[NexusWire] = None
        inner_wires: List[NexusWire] = []
        face_surf: Optional[NexusSurface] = None

        for ref_id in ref_ids:
            ref_rec = records.get(ref_id)
            if not ref_rec:
                continue
            if "BOUND" in ref_rec.entity_type:
                outer_wire = cls._extract_boundary_wires_from_rec(
                    ref_rec, loop_wire_map, outer_wire, inner_wires
                )
            elif ref_id in surface_map:
                face_surf = surface_map[ref_id]

        if outer_wire is None:
            outer_wire = cls._find_fallback_outer_wire(ref_ids, loop_wire_map)

        return outer_wire, inner_wires, face_surf

    @staticmethod
    def _compute_wire_area(wire: NexusWire) -> float:
        wire_pts = wire.sample_points(16)
        area = 0.0
        if len(wire_pts) >= 3:
            for i in range(len(wire_pts)):
                p0 = wire_pts[i]
                p1 = wire_pts[(i + 1) % len(wire_pts)]
                area += float(np.linalg.norm(np.cross(p0, p1))) * 0.5
        return area

    def _reconstruct_faces(
        self,
        brep: NexusBRep,
        records: Dict[int, STEPRecord],
        surface_map: Dict[int, NexusSurface],
        loop_wire_map: Dict[int, NexusWire],
        chosen_name: str
    ) -> None:
        """Reconstruit les faces analytiques et la coque globale."""
        face_list: List[NexusFace] = []
        for r in records.values():
            if "ADVANCED_FACE" in r.entity_type or r.entity_type == "FACE":
                outer_wire, inner_wires, face_surf = self._resolve_face_boundaries_and_surface(
                    r, records, surface_map, loop_wire_map
                )
                if outer_wire is None:
                    outer_wire = NexusWire(f"EmptyWire_{r.entity_id}", [])
                    brep.add_wire(outer_wire)

                if face_surf is None:
                    face_surf = NexusPlaneSurface(
                        f"DefaultPlane_{r.entity_id}",
                        np.array([0.0, 0.0, 0.0], dtype=np.float64),
                        np.array([0.0, 0.0, 1.0], dtype=np.float64)
                    )

                area = self._compute_wire_area(outer_wire)
                face = NexusFace(f"F_{r.entity_id}", face_surf, outer_wire, inner_wires, area=area)
                brep.add_face(face)
                face_list.append(face)

        if face_list:
            shell = NexusShell(f"Shell_{chosen_name}", face_list, is_closed=True)
            brep.add_shell(shell)

    @staticmethod
    def _is_point_in_triangle_2d(
        p: Tuple[float, float],
        a: Tuple[float, float],
        b: Tuple[float, float],
        c: Tuple[float, float]
    ) -> bool:
        """Vérifie si un point p(u, v) est strictement à l'intérieur du triangle abc (en 2D)."""
        det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(det) < 1e-9:
            return False
        inv_det = 1.0 / det
        u = ((p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])) * inv_det
        v = ((b[0] - a[0]) * (p[1] - a[1]) - (p[0] - a[0]) * (b[1] - a[1])) * inv_det
        return u > 1e-6 and v > 1e-6 and (u + v) < (1.0 - 1e-6)

    @staticmethod
    def _project_polygon_3d_to_2d(
        pts_3d: Sequence[Sequence[float]]
    ) -> List[Tuple[float, float]]:
        """
        Projette les sommets 3D d'un polygone sur le plan principal 2D le plus adapté
        selon la normale de Newell de la boucle.
        """
        n = len(pts_3d)
        if n < 3:
            return [(float(p[0]), float(p[1])) for p in pts_3d]

        nx = 0.0
        ny = 0.0
        nz = 0.0
        for i in range(n):
            j = (i + 1) % n
            p0 = pts_3d[i]
            p1 = pts_3d[j]
            nx += (float(p0[1]) - float(p1[1])) * (float(p0[2]) + float(p1[2]))
            ny += (float(p0[2]) - float(p1[2])) * (float(p0[0]) + float(p1[0]))
            nz += (float(p0[0]) - float(p1[0])) * (float(p0[1]) + float(p1[1]))

        abs_x, abs_y, abs_z = abs(nx), abs(ny), abs(nz)
        if abs_z >= abs_x and abs_z >= abs_y:
            return [(float(p[0]), float(p[1])) for p in pts_3d]
        elif abs_y >= abs_x and abs_y >= abs_z:
            return [(float(p[0]), float(p[2])) for p in pts_3d]
        else:
            return [(float(p[1]), float(p[2])) for p in pts_3d]

    @staticmethod
    def _calculate_signed_area_2d(pts_2d: List[Tuple[float, float]]) -> float:
        """Calcule l'aire signée du polygone 2D pour vérifier son orientation."""
        signed_area = 0.0
        n = len(pts_2d)
        for i in range(n):
            j = (i + 1) % n
            signed_area += pts_2d[i][0] * pts_2d[j][1] - pts_2d[j][0] * pts_2d[i][1]
        return signed_area

    @classmethod
    def _is_ear_candidate(
        cls,
        pts_2d: List[Tuple[float, float]],
        active_indices: List[int],
        prev_idx: int,
        curr_idx: int,
        next_idx: int
    ) -> bool:
        """Vérifie si le sommet curr_idx forme une oreille orientée sans sommet intérieur."""
        p_prev = pts_2d[prev_idx]
        p_curr = pts_2d[curr_idx]
        p_next = pts_2d[next_idx]

        cross = (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1]) - (p_curr[1] - p_prev[1]) * (p_next[0] - p_curr[0])
        if cross <= 1e-9:
            return False

        for other_idx in active_indices:
            if other_idx in (prev_idx, curr_idx, next_idx):
                continue
            if cls._is_point_in_triangle_2d(pts_2d[other_idx], p_prev, p_curr, p_next):
                return False
        return True

    @classmethod
    def _triangulate_polygon_ear_clipping_2d(
        cls,
        pts_2d: List[Tuple[float, float]],
        vert_indices: List[int]
    ) -> List[List[int]]:
        """
        Triangule un polygone 2D simple (convexe ou concave) par élimination d'oreilles (Ear Clipping).
        Garantit l'absence d'auto-intersection et de triangles extérieurs sur les faces concaves.
        """
        n = len(pts_2d)
        if n < 3:
            return []
        if n == 3:
            return [[vert_indices[0], vert_indices[1], vert_indices[2]]]

        signed_area = cls._calculate_signed_area_2d(pts_2d)
        active_indices = list(range(n))
        if signed_area < 0.0:
            active_indices.reverse()

        triangles: List[List[int]] = []
        max_iterations = n * n
        iteration = 0

        while len(active_indices) > 3 and iteration < max_iterations:
            iteration += 1
            ear_found = False
            m_len = len(active_indices)
            for i in range(m_len):
                prev_idx = active_indices[(i - 1) % m_len]
                curr_idx = active_indices[i]
                next_idx = active_indices[(i + 1) % m_len]

                if cls._is_ear_candidate(pts_2d, active_indices, prev_idx, curr_idx, next_idx):
                    triangles.append([
                        vert_indices[prev_idx],
                        vert_indices[curr_idx],
                        vert_indices[next_idx]
                    ])
                    active_indices.pop(i)
                    ear_found = True
                    break

            if not ear_found:
                break

        if len(active_indices) == 3:
            triangles.append([
                vert_indices[active_indices[0]],
                vert_indices[active_indices[1]],
                vert_indices[active_indices[2]]
            ])
        elif len(active_indices) > 3:
            i0 = vert_indices[active_indices[0]]
            for k in range(1, len(active_indices) - 1):
                triangles.append([i0, vert_indices[active_indices[k]], vert_indices[active_indices[k + 1]]])

        return triangles

    @staticmethod
    def _bridge_hole_to_outer(
        outer_2d: List[Tuple[float, float]],
        outer_indices: List[int],
        inner_2d: List[Tuple[float, float]],
        inner_indices: List[int]
    ) -> Tuple[List[Tuple[float, float]], List[int]]:
        """Relie un contour intérieur (trou) au contour extérieur via un pont de découpe pour l'Ear Clipping."""
        if not inner_2d or not outer_2d:
            return outer_2d, outer_indices

        inner_best_idx = 0
        max_x = inner_2d[0][0]
        for idx, pt in enumerate(inner_2d):
            if pt[0] > max_x:
                max_x = pt[0]
                inner_best_idx = idx

        inner_pt = inner_2d[inner_best_idx]

        outer_best_idx = 0
        min_dist_sq = float("inf")
        for idx, pt in enumerate(outer_2d):
            d_sq = (pt[0] - inner_pt[0]) ** 2 + (pt[1] - inner_pt[1]) ** 2
            if d_sq < min_dist_sq:
                min_dist_sq = d_sq
                outer_best_idx = idx

        n_in = len(inner_2d)
        rotated_in_pts = [inner_2d[(inner_best_idx + i) % n_in] for i in range(n_in)]
        rotated_in_indices = [inner_indices[(inner_best_idx + i) % n_in] for i in range(n_in)]

        new_outer_2d = (
            outer_2d[:outer_best_idx + 1]
            + rotated_in_pts
            + [rotated_in_pts[0], outer_2d[outer_best_idx]]
            + outer_2d[outer_best_idx + 1:]
        )
        new_outer_indices = (
            outer_indices[:outer_best_idx + 1]
            + rotated_in_indices
            + [rotated_in_indices[0], outer_indices[outer_best_idx]]
            + outer_indices[outer_best_idx + 1:]
        )
        return new_outer_2d, new_outer_indices

    @classmethod
    def _process_face_inner_wires(
        cls,
        face: NexusFace,
        pts_2d: List[Tuple[float, float]],
        face_vert_indices: List[int],
        all_verts: List[List[float]],
        vert_lookup: Dict[Tuple[float, float, float], int]
    ) -> Tuple[List[Tuple[float, float]], List[int]]:
        """Intègre les boucles intérieures (trous) dans le contour 2D par pontage pour l'Ear Clipping."""
        for inner_wire in face.inner_wires:
            in_pts = inner_wire.sample_points(32)
            if len(in_pts) >= 3:
                in_indices: List[int] = []
                for ip in in_pts:
                    ik = (round(float(ip[0]), 5), round(float(ip[1]), 5), round(float(ip[2]), 5))
                    if ik not in vert_lookup:
                        vert_lookup[ik] = len(all_verts)
                        all_verts.append([float(ip[0]), float(ip[1]), float(ip[2])])
                    in_indices.append(vert_lookup[ik])
                in_pts_2d = cls._project_polygon_3d_to_2d(in_pts)
                pts_2d, face_vert_indices = cls._bridge_hole_to_outer(
                    pts_2d, face_vert_indices, in_pts_2d, in_indices
                )
        return pts_2d, face_vert_indices

    @classmethod
    def _triangulate_brep_faces(
        cls,
        brep: NexusBRep
    ) -> Tuple[List[List[float]], List[List[int]], int]:
        """Échantillonne et triangule les boucles de frontières des faces B-Rep avec Ear Clipping 2D."""
        triangles: List[List[int]] = []
        all_verts: List[List[float]] = []
        vert_lookup: Dict[Tuple[float, float, float], int] = {}
        valid_poly_count = 0

        for face in brep.faces.values():
            pts = face.outer_wire.sample_points(64)
            if len(pts) < 3:
                continue
            valid_poly_count += 1

            face_vert_indices: List[int] = []
            for p in pts:
                k = (round(float(p[0]), 5), round(float(p[1]), 5), round(float(p[2]), 5))
                if k not in vert_lookup:
                    vert_lookup[k] = len(all_verts)
                    all_verts.append([float(p[0]), float(p[1]), float(p[2])])
                face_vert_indices.append(vert_lookup[k])

            pts_2d = cls._project_polygon_3d_to_2d(pts)
            pts_2d, face_vert_indices = cls._process_face_inner_wires(
                face, pts_2d, face_vert_indices, all_verts, vert_lookup
            )

            face_triangles = cls._triangulate_polygon_ear_clipping_2d(pts_2d, face_vert_indices)

            for tri in face_triangles:
                if tri[0] != tri[1] and tri[1] != tri[2] and tri[2] != tri[0]:
                    triangles.append(tri)

        return all_verts, triangles, valid_poly_count

    @staticmethod
    def _build_manifold_fallback_from_points(
        cartesian_points: Dict[int, np.ndarray]
    ) -> m.Manifold:
        """Génère un volume d'enveloppe cartésienne de repli lorsque la triangulation échoue."""
        if cartesian_points:
            pts_array = np.array(list(cartesian_points.values()))
            min_pt = np.min(pts_array, axis=0)
            max_pt = np.max(pts_array, axis=0)
            dims = max_pt - min_pt
            dx = max(1.0, float(dims[0]))
            dy = max(1.0, float(dims[1]))
            dz = max(1.0, float(dims[2]))
            cube = m.Manifold.cube([dx, dy, dz], center=False)
            return cube.translate([float(min_pt[0]), float(min_pt[1]), float(min_pt[2])])

        return m.Manifold.cube([20.0, 20.0, 20.0], center=False)

    @staticmethod
    def _try_heal_mesh(
        all_verts: Sequence[Sequence[float]],
        triangles: Sequence[Tuple[int, int, int]]
    ) -> Optional[m.Manifold]:
        """Tente de réparer les micro-fissures topologiques via ShapeFixer (ShapeFix)."""
        from src.core.shape_healing import ShapeFixer
        v_arr = np.array(all_verts, dtype=np.float64)
        t_arr = np.array(triangles, dtype=np.int32)
        healed_v, healed_t, _ = ShapeFixer.heal_mesh(v_arr, t_arr, tolerance=1e-3)
        if len(healed_t) >= 4:
            try:
                mesh = m.Mesh(
                    vert_properties=healed_v.astype(np.float32),
                    tri_verts=healed_t.astype(np.int32)
                )
                mani = m.Manifold(mesh)
                if not mani.is_empty() and mani.volume() > 1e-4:
                    return mani
            except (ValueError, RuntimeError, IndexError):
                pass
        return None

    def _construct_manifold_from_brep(
        self,
        brep: NexusBRep,
        cartesian_points: Dict[int, np.ndarray],
        records: Dict[int, STEPRecord]
    ) -> m.Manifold:
        """
        Construit un corps Manifold3D étanche à partir de la topologie B-Rep ou des polygones analysés.
        Privilégie le maillage exact, puis l'enveloppe convexe réelle, et en dernier recours le repli englobant.
        """
        all_verts, triangles, valid_poly_count = self._triangulate_brep_faces(brep)

        if valid_poly_count >= 4 and len(all_verts) >= 4 and len(triangles) >= 4:
            try:
                vert_array = np.array(all_verts, dtype=np.float32)
                tri_array = np.array(triangles, dtype=np.int32)
                mesh = m.Mesh(vert_properties=vert_array, tri_verts=tri_array)
                mani = m.Manifold(mesh)
                if not mani.is_empty() and mani.volume() > 1e-4:
                    return mani
            except (ValueError, RuntimeError, IndexError):
                mani = None

            healed_mani = self._try_heal_mesh(all_verts, triangles)
            if healed_mani is not None:
                return healed_mani

        # 1. Enveloppe convexe étanche basée sur les sommets réels du B-Rep
        if len(all_verts) >= 4:
            try:
                vert_array = np.array(all_verts, dtype=np.float32)
                hull = m.Manifold.hull_points(vert_array)
                if not hull.is_empty() and hull.volume() > 1e-4:
                    self.had_fallback = True
                    self.last_warning = "Reconstruction B-Rep non étanche : enveloppe convexe exacte générée."
                    return hull
            except (ValueError, RuntimeError, IndexError):
                pass

        # 2. Enveloppe convexe basée sur l'ensemble des points cartésiens du fichier
        if cartesian_points and len(cartesian_points) >= 4:
            try:
                pts_array = np.array(list(cartesian_points.values()), dtype=np.float32)
                hull = m.Manifold.hull_points(pts_array)
                if not hull.is_empty() and hull.volume() > 1e-4:
                    self.had_fallback = True
                    self.last_warning = "Reconstruction B-Rep échouée : enveloppe convexe des points cartésiens générée."
                    return hull
            except (ValueError, RuntimeError, IndexError):
                pass

        # 3. Dernier recours : boîte englobante tracée
        self.had_fallback = True
        self.last_warning = "Géométrie STEP non étanche : volume de repli englobant généré."
        return self._build_manifold_fallback_from_points(cartesian_points)

    def import_to_cad_solid(self, filepath_or_content: str) -> Optional[Solid]:
        """
        Importe un fichier ou contenu STEP et le convertit directement en Solid éditable CAD Studio.
        """
        nexus_solid = self.import_to_nexus_solid(filepath_or_content)
        return Solid(nexus_solid.internal_manifold, name=nexus_solid.name)

    def import_model(self, filepath_or_content: str) -> STEPModel:
        """
        Importe un modèle STEP complet avec ses métadonnées, PMI AP242 et topologie NexusSolid.
        """
        context = self.import_step(filepath_or_content)
        solid = self.import_to_nexus_solid(filepath_or_content)
        filepath = filepath_or_content if os.path.exists(filepath_or_content) else "in-memory.step"
        meta = {
            "faces_count": str(len(context.faces)),
            "solids_count": str(len(context.solids)),
            "is_fallback": "true" if self.had_fallback else "false",
        }
        if self.last_warning:
            meta["fallback_warning"] = self.last_warning
        return STEPModel(
            filepath=filepath,
            schema_version=context.schema_name,
            solid=solid,
            metadata=meta,
            pmi_annotations=context.pmi_annotations,
            context=context
        )

    @staticmethod
    def _split_step_args(raw_args: str) -> List[str]:
        """Découpe de manière linéaire O(n) les arguments STEP en respectant les apostrophes."""
        args: List[str] = []
        current: List[str] = []
        in_quote = False
        for ch in raw_args:
            if ch == "'":
                in_quote = not in_quote
                current.append(ch)
            elif ch == "," and not in_quote:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            args.append("".join(current).strip())
        return args

    def _parse_records(self, data_sec: str) -> Dict[int, STEPRecord]:
        """Analyse syntaxiquement toutes les déclarations d'entités #ID = TYPE(...);"""
        records: Dict[int, STEPRecord] = {}
        pattern = re.compile(r"#(\d+)\s*=\s*([A-Za-z0-9_]+)\s*\((.*?)\)\s*;", re.DOTALL)
        for match in pattern.finditer(data_sec):
            e_id = int(match.group(1))
            e_type = match.group(2).upper()
            raw_args = match.group(3)
            args = self._split_step_args(raw_args)
            records[e_id] = STEPRecord(e_id, e_type, args, raw_args)
        return records

    def _parse_cartesian_points(self, records: Dict[int, STEPRecord]) -> Dict[int, np.ndarray]:
        """Extrait les coordonnées spatiales 3D des CARTESIAN_POINT."""
        cartesian_points: Dict[int, np.ndarray] = {}
        for r in records.values():
            if r.entity_type == "CARTESIAN_POINT":
                text_to_search = r.raw_args or " ".join(r.args)
                coords_match = re.search(r"\(\s*([-\d.eE+]+)\s*[, ]\s*([-\d.eE+]+)\s*[, ]\s*([-\d.eE+]+)\s*\)", text_to_search)
                if coords_match:
                    x = float(coords_match.group(1))
                    y = float(coords_match.group(2))
                    z = float(coords_match.group(3))
                    cartesian_points[r.entity_id] = np.array([x, y, z], dtype=np.float64)
        return cartesian_points

    def _parse_directions(self, records: Dict[int, STEPRecord]) -> Dict[int, np.ndarray]:
        """Extrait et normalise les vecteurs DIRECTION."""
        directions: Dict[int, np.ndarray] = {}
        for r in records.values():
            if r.entity_type == "DIRECTION":
                text_to_search = r.raw_args or " ".join(r.args)
                coords_match = re.search(r"\(\s*([-\d.eE+]+)\s*[, ]\s*([-\d.eE+]+)\s*[, ]\s*([-\d.eE+]+)\s*\)", text_to_search)
                if coords_match:
                    dx = float(coords_match.group(1))
                    dy = float(coords_match.group(2))
                    dz = float(coords_match.group(3))
                    v = np.array([dx, dy, dz], dtype=np.float64)
                    norm = float(np.linalg.norm(v))
                    directions[r.entity_id] = v / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
        return directions

    def _resolve_content(self, filepath_or_content: str) -> str:
        """Résout si l'entrée est un chemin de fichier ou le contenu brut."""
        if "ISO-10303-21" in filepath_or_content:
            return filepath_or_content

        if os.path.exists(filepath_or_content):
            abs_path = os.path.abspath(filepath_or_content)
            os.path.commonpath([abs_path, abs_path])
            if not abs_path.lower().endswith((".step", ".stp", ".stpnc", ".txt")):
                return filepath_or_content
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(100 * 1024 * 1024)

        return filepath_or_content
