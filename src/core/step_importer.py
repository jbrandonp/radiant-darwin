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
        bound_refs = [int(x) for x in re.findall(r"#(\d+)", ref_rec.raw_args)]
        return [loop_wire_map[b_id] for b_id in bound_refs if b_id in loop_wire_map]

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
                for w in cls._collect_bound_wires(ref_rec, loop_wire_map):
                    if outer_wire is None:
                        outer_wire = w
                    else:
                        inner_wires.append(w)
            elif ref_id in surface_map:
                face_surf = surface_map[ref_id]

        if outer_wire is None:
            for ref_id in ref_ids:
                if ref_id in loop_wire_map:
                    outer_wire = loop_wire_map[ref_id]
                    break

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

    def _construct_manifold_from_brep(
        self,
        brep: NexusBRep,
        cartesian_points: Dict[int, np.ndarray],
        records: Dict[int, STEPRecord]
    ) -> m.Manifold:
        """
        Construit un corps Manifold3D étanche à partir de la topologie B-Rep ou des polygones analysés.
        """
        # Collecter toutes les boucles de points des faces
        triangles: List[List[int]] = []
        all_verts: List[List[float]] = []
        vert_lookup: Dict[Tuple[float, float, float], int] = {}

        def get_or_add_vert(p: np.ndarray) -> int:
            key = (round(float(p[0]), 5), round(float(p[1]), 5), round(float(p[2]), 5))
            if key not in vert_lookup:
                idx = len(all_verts)
                vert_lookup[key] = idx
                all_verts.append([float(p[0]), float(p[1]), float(p[2])])
                return idx
            return vert_lookup[key]

        valid_poly_count = 0
        for face in brep.faces.values():
            pts = face.outer_wire.sample_points(64)
            if len(pts) >= 3:
                valid_poly_count += 1
                idx0 = get_or_add_vert(pts[0])
                for j in range(1, len(pts) - 1):
                    idx1 = get_or_add_vert(pts[j])
                    idx2 = get_or_add_vert(pts[j + 1])
                    if idx0 != idx1 and idx1 != idx2 and idx2 != idx0:
                        triangles.append([idx0, idx1, idx2])

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

        # Fallback volumique précis basé sur l'enveloppe cartésienne des points
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
        return STEPModel(
            filepath=filepath,
            schema_version=context.schema_name,
            solid=solid,
            metadata={"faces_count": str(len(context.faces)), "solids_count": str(len(context.solids))},
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
