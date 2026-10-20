"""
Exportateur standard ISO 10303-21 STEP (AP203 / AP214 Faceted B-Rep).
Permet l'interopérabilité et l'échange de fichiers CAO solides 3D avec FreeCAD,
SolidWorks, CATIA, Autodesk Inventor et Fusion 360.
Exportateur STEP AP203/AP214 avec typage B-Rep strict.
"""

from __future__ import annotations
import os
import datetime
from typing import List, Tuple, Sequence, Dict, TYPE_CHECKING
import numpy as np

from src.core.geometry import Solid
from src.core.nexus_kernel.brep_topology import (
    NexusPlaneSurface,
    NexusCylinderSurface,
    NexusSphereSurface,
    NexusCircleCurve,
    NexusLineCurve,
    NexusCurve,
    NexusSurface
)

if TYPE_CHECKING:
    from src.core.nexus_kernel.hybrid_solid import NexusSolid



class STEPExporter:
    """Moteur d'exportation de géométries 3D au format ISO 10303-21 STEP."""

    @staticmethod
    def export_to_string(
        solids: Dict[str, Solid],
        header_description: str = "CAD Studio Faceted B-Rep Solid",
        as_advanced_brep: bool = False
    ) -> str:
        """Génère la chaîne de caractères conforme ISO 10303-21 STEP (AP203 Faceted ou AP242 Advanced B-Rep)."""
        if as_advanced_brep:
            return STEPExporter.export_advanced_brep_to_string(solids, header_description=header_description)

        if not solids:
            return ""

        # Fusionne ou sélectionne le solide
        first_solid = list(solids.values())[0]
        combined = first_solid
        for other in list(solids.values())[1:]:
            if not other.is_empty():
                combined = combined.union(other)

        if combined.is_empty():
            return ""

        mesh_data = combined.manifold.to_mesh()
        vert_props = np.array(mesh_data.vert_properties, dtype=np.float64)[:, :3]
        tri_verts = np.array(mesh_data.tri_verts, dtype=np.int64)

        if len(vert_props) == 0 or len(tri_verts) == 0:
            return ""

        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        part_name = combined.name.replace(" ", "_")

        lines: List[str] = [
            "ISO-10303-21;",
            "HEADER;",
            f"FILE_DESCRIPTION(('{header_description}','Standard STEP AP203'),'2;1');",
            f"FILE_NAME('{part_name}.step','{timestamp}',('Brandon'),('CAD Studio'),'CAD Studio 1.0','CAD Studio Engine','');",
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN_CC2', 'AP203_CONFIGURATION_CONTROLLED_3D_DESIGN_OF_MECHANICAL_PARTS_AND_ASSEMBLIES_MIM_LF'));",
            "ENDSEC;",
            "DATA;",
            "#1=APPLICATION_CONTEXT('mechanical design');",
            "#2=APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,#1);",
            "#3=PRODUCT_CONTEXT('part definition',#1,'mechanical');",
            f"#4=PRODUCT('{part_name}','{part_name}','',(#3));",
            "#5=PRODUCT_DEFINITION_FORMATION('1.0',$,#4);",
            "#6=PRODUCT_DEFINITION('design',$,#5,#3);",
            "#7=PRODUCT_DEFINITION_SHAPE('shape',$,#6);",
        ]

        eid = 8
        # Coordonnées cartésiennes des sommets 3D
        pt_eids: List[int] = []
        for v in vert_props:
            lines.append(f"#{eid}=CARTESIAN_POINT('',({v[0]:.6f},{v[1]:.6f},{v[2]:.6f}));")
            pt_eids.append(eid)
            eid += 1

        # Sommets topologiques
        vert_eids: List[int] = []
        for peid in pt_eids:
            lines.append(f"#{eid}=VERTEX_POINT('',#{peid});")
            vert_eids.append(eid)
            eid += 1

        # Facettes triangulaires (Poly Loops et Bounds)
        face_eids: List[int] = []
        for f in tri_verts:
            loop_refs = f"#{vert_eids[f[0]]},#{vert_eids[f[1]]},#{vert_eids[f[2]]}"
            loop_id = eid
            lines.append(f"#{loop_id}=POLY_LOOP('',({loop_refs}));")
            eid += 1

            bound_id = eid
            lines.append(f"#{bound_id}=FACE_OUTER_BOUND('',#{loop_id},.T.);")
            eid += 1

            # Calcul du vecteur normal de la facette plane
            v0 = vert_props[f[0]]
            v1 = vert_props[f[1]]
            v2 = vert_props[f[2]]
            e1 = v1 - v0
            e2 = v2 - v0
            norm = np.cross(e1, e2)
            norm_len = float(np.linalg.norm(norm))
            if norm_len > 1e-9:
                norm = norm / norm_len
            else:
                norm = np.array([0.0, 0.0, 1.0], dtype=np.float64)

            dir_z_id = eid
            lines.append(f"#{dir_z_id}=DIRECTION('',({norm[0]:.6f},{norm[1]:.6f},{norm[2]:.6f}));")
            eid += 1

            axis_id = eid
            lines.append(f"#{axis_id}=AXIS2_PLACEMENT_3D('',#{vert_eids[f[0]]},#{dir_z_id},$);")
            eid += 1

            surf_id = eid
            lines.append(f"#{surf_id}=PLANE('',#{axis_id});")
            eid += 1

            face_id = eid
            lines.append(f"#{face_id}=FACE_SURFACE('',(#{bound_id}),#{surf_id},.T.);")
            face_eids.append(face_id)
            eid += 1

        # Coque fermée (Closed Shell)
        shell_id = eid
        faces_str = ",".join(f"#{fid}" for fid in face_eids)
        lines.append(f"#{shell_id}=CLOSED_SHELL('',({faces_str}));")
        eid += 1

        # Solide Faceted B-Rep
        brep_id = eid
        lines.append(f"#{brep_id}=FACETED_BREP('{part_name}',#{shell_id});")
        eid += 1

        # Représentation de forme (Shape Representation)
        rep_id = eid
        lines.append(f"#{rep_id}=FACETED_BREP_SHAPE_REPRESENTATION('{part_name}',(#{brep_id}),#1);")
        eid += 1

        lines.append("ENDSEC;")
        lines.append("END-ISO-10303-21;")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _export_brep_curve(
        curve: NexusCurve,
        sv_x: float,
        sv_y: float,
        sv_z: float,
        eid: int,
        lines: List[str]
    ) -> Tuple[int, int]:
        """Exporte la géométrie analytique d'une courbe (CIRCLE ou LINE)."""
        if isinstance(curve, NexusCircleCurve):
            c = curve.center
            n = curve.normal
            u = curve.u_dir
            p_c = eid
            lines.append(f"#{p_c}=CARTESIAN_POINT('',({c[0]:.6f},{c[1]:.6f},{c[2]:.6f}));")
            eid += 1
            d_n = eid
            lines.append(f"#{d_n}=DIRECTION('',({n[0]:.6f},{n[1]:.6f},{n[2]:.6f}));")
            eid += 1
            d_u = eid
            lines.append(f"#{d_u}=DIRECTION('',({u[0]:.6f},{u[1]:.6f},{u[2]:.6f}));")
            eid += 1
            ax_c = eid
            lines.append(f"#{ax_c}=AXIS2_PLACEMENT_3D('',#{p_c},#{d_n},#{d_u});")
            eid += 1
            geom_id = eid
            lines.append(f"#{geom_id}=CIRCLE('',#{ax_c},{curve.radius:.6f});")
            eid += 1
            return geom_id, eid

        p_start = eid
        lines.append(f"#{p_start}=CARTESIAN_POINT('',({sv_x:.6f},{sv_y:.6f},{sv_z:.6f}));")
        eid += 1
        dir_id = eid
        tang = curve.tangent(0.0)
        lines.append(f"#{dir_id}=DIRECTION('',({tang[0]:.6f},{tang[1]:.6f},{tang[2]:.6f}));")
        eid += 1
        geom_id = eid
        lines.append(f"#{geom_id}=LINE('',#{p_start},#{dir_id});")
        eid += 1
        return geom_id, eid

    @staticmethod
    def _export_brep_surface(
        surf: NexusSurface,
        fallback_v_id: int,
        eid: int,
        lines: List[str]
    ) -> Tuple[int, int]:
        """Exporte la surface analytique (CYLINDRICAL_SURFACE, PLANE, SPHERICAL_SURFACE)."""
        if isinstance(surf, NexusCylinderSurface):
            orig = surf.origin
            axis = surf.axis
            ref_dir = surf.u_dir
            p_orig = eid
            lines.append(f"#{p_orig}=CARTESIAN_POINT('',({orig[0]:.6f},{orig[1]:.6f},{orig[2]:.6f}));")
            eid += 1
            d_axis = eid
            lines.append(f"#{d_axis}=DIRECTION('',({axis[0]:.6f},{axis[1]:.6f},{axis[2]:.6f}));")
            eid += 1
            d_ref = eid
            lines.append(f"#{d_ref}=DIRECTION('',({ref_dir[0]:.6f},{ref_dir[1]:.6f},{ref_dir[2]:.6f}));")
            eid += 1
            ax_id = eid
            lines.append(f"#{ax_id}=AXIS2_PLACEMENT_3D('',#{p_orig},#{d_axis},#{d_ref});")
            eid += 1
            surf_id = eid
            lines.append(f"#{surf_id}=CYLINDRICAL_SURFACE('',#{ax_id},{surf.radius:.6f});")
            eid += 1
            return surf_id, eid

        if isinstance(surf, NexusSphereSurface):
            c = surf.center
            p_c = eid
            lines.append(f"#{p_c}=CARTESIAN_POINT('',({c[0]:.6f},{c[1]:.6f},{c[2]:.6f}));")
            eid += 1
            d_z = eid
            lines.append(f"#{d_z}=DIRECTION('',(0.000000,0.000000,1.000000));")
            eid += 1
            d_x = eid
            lines.append(f"#{d_x}=DIRECTION('',(1.000000,0.000000,0.000000));")
            eid += 1
            ax_id = eid
            lines.append(f"#{ax_id}=AXIS2_PLACEMENT_3D('',#{p_c},#{d_z},#{d_x});")
            eid += 1
            surf_id = eid
            lines.append(f"#{surf_id}=SPHERICAL_SURFACE('',#{ax_id},{surf.radius:.6f});")
            eid += 1
            return surf_id, eid

        if isinstance(surf, NexusPlaneSurface):
            orig = surf.origin
            norm = surf._normal
            ref_dir = surf.u_dir
            p_orig = eid
            lines.append(f"#{p_orig}=CARTESIAN_POINT('',({orig[0]:.6f},{orig[1]:.6f},{orig[2]:.6f}));")
            eid += 1
            d_norm = eid
            lines.append(f"#{d_norm}=DIRECTION('',({norm[0]:.6f},{norm[1]:.6f},{norm[2]:.6f}));")
            eid += 1
            d_ref = eid
            lines.append(f"#{d_ref}=DIRECTION('',({ref_dir[0]:.6f},{ref_dir[1]:.6f},{ref_dir[2]:.6f}));")
            eid += 1
            ax_id = eid
            lines.append(f"#{ax_id}=AXIS2_PLACEMENT_3D('',#{p_orig},#{d_norm},#{d_ref});")
            eid += 1
            surf_id = eid
            lines.append(f"#{surf_id}=PLANE('',#{ax_id});")
            eid += 1
            return surf_id, eid

        ax_id = eid
        lines.append(f"#{ax_id}=AXIS2_PLACEMENT_3D('',#{fallback_v_id},$,$);")
        eid += 1
        surf_id = eid
        lines.append(f"#{surf_id}=PLANE('',#{ax_id});")
        eid += 1
        return surf_id, eid

    @staticmethod
    def _export_face_bounds(
        face: NexusFace,
        edge_id_map: Dict[str, int],
        eid: int,
        lines: List[str]
    ) -> Tuple[List[int], int]:
        """Exporte les boucles topologiques extérieure et intérieures (trous) d'une face."""
        bound_ids: List[int] = []

        # 1. Boucle de frontière extérieure (FACE_OUTER_BOUND)
        oriented_edges: List[int] = []
        for e in face.outer_wire.edges:
            e_ref = edge_id_map.get(e.edge_id)
            if e_ref:
                oe_id = eid
                lines.append(f"#{oe_id}=ORIENTED_EDGE('',*,*,#{e_ref},.T.);")
                oriented_edges.append(oe_id)
                eid += 1

        loop_id = eid
        edges_str = ",".join(f"#{oe}" for oe in oriented_edges)
        lines.append(f"#{loop_id}=EDGE_LOOP('',({edges_str}));")
        eid += 1

        bound_id = eid
        lines.append(f"#{bound_id}=FACE_OUTER_BOUND('',#{loop_id},.T.);")
        bound_ids.append(bound_id)
        eid += 1

        # 2. Boucles intérieures pour les perçages / trous (FACE_BOUND)
        for inner_w in face.inner_wires:
            inner_oriented: List[int] = []
            for ie in inner_w.edges:
                ie_ref = edge_id_map.get(ie.edge_id)
                if ie_ref:
                    ioe_id = eid
                    lines.append(f"#{ioe_id}=ORIENTED_EDGE('',*,*,#{ie_ref},.T.);")
                    inner_oriented.append(ioe_id)
                    eid += 1
            inner_loop_id = eid
            lines.append(f"#{inner_loop_id}=EDGE_LOOP('',({','.join(f'#{x}' for x in inner_oriented)}));")
            eid += 1
            inner_bound_id = eid
            lines.append(f"#{inner_bound_id}=FACE_BOUND('',#{inner_loop_id},.T.);")
            bound_ids.append(inner_bound_id)
            eid += 1

        return bound_ids, eid

    @staticmethod
    def export_nexus_brep_to_string(nexus_solid: NexusSolid, header_description: str = "CAD Studio Advanced B-Rep Solid") -> str:
        """
        Exporte la topologie exacte d'un NexusSolid au standard ISO 10303-21 STEP AP214 / AP242
        sous forme d'ADVANCED_BREP_SHAPE_REPRESENTATION avec surfaces analytiques exactes
        (PLANE, CYLINDRICAL_SURFACE, SPHERICAL_SURFACE, AXIS2_PLACEMENT_3D, ADVANCED_FACE, EDGE_CURVE).
        """
        brep = nexus_solid.brep
        if not brep.faces:
            return ""

        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        part_name = nexus_solid.name.replace(" ", "_")

        lines: List[str] = [
            "ISO-10303-21;",
            "HEADER;",
            f"FILE_DESCRIPTION(('{header_description}','Standard STEP AP242 / AP214 Advanced B-Rep'),'2;1');",
            f"FILE_NAME('{part_name}.step','{timestamp}',('Brandon'),('CAD Studio'),'CAD Studio 1.0','CAD Studio Hybrid Kernel','');",
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN_CC2', 'AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));",
            "ENDSEC;",
            "DATA;",
            "#1=APPLICATION_CONTEXT('mechanical design');",
            "#2=APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2010,#1);",
            "#3=PRODUCT_CONTEXT('part definition',#1,'mechanical');",
            f"#4=PRODUCT('{part_name}','{part_name}','',(#3));",
            "#5=PRODUCT_DEFINITION_FORMATION('1.0',$,#4);",
            "#6=PRODUCT_DEFINITION('design',$,#5,#3);",
            "#7=PRODUCT_DEFINITION_SHAPE('shape',$,#6);",
        ]

        eid = 8
        vert_id_map: Dict[str, int] = {}
        for v in brep.vertices.values():
            pt_id = eid
            lines.append(f"#{pt_id}=CARTESIAN_POINT('',({v.x:.6f},{v.y:.6f},{v.z:.6f}));")
            eid += 1
            v_id = eid
            lines.append(f"#{v_id}=VERTEX_POINT('',#{pt_id});")
            vert_id_map[v.vertex_id] = v_id
            eid += 1

        edge_id_map: Dict[str, int] = {}
        for e in brep.edges.values():
            sv = e.start_vertex
            geom_curve_id, eid = STEPExporter._export_brep_curve(e.curve, sv.x, sv.y, sv.z, eid, lines)
            edge_curve_id = eid
            sv_ref = vert_id_map.get(e.start_vertex.vertex_id, 8)
            ev_ref = vert_id_map.get(e.end_vertex.vertex_id, 8)
            lines.append(f"#{edge_curve_id}=EDGE_CURVE('',#{sv_ref},#{ev_ref},#{geom_curve_id},.T.);")
            edge_id_map[e.edge_id] = edge_curve_id
            eid += 1

        face_eids: List[int] = []
        first_v_id = vert_id_map.get(list(brep.vertices.keys())[0], 8) if brep.vertices else 8

        for f in brep.faces.values():
            bound_ids, eid = STEPExporter._export_face_bounds(f, edge_id_map, eid, lines)
            surf_id, eid = STEPExporter._export_brep_surface(f.surface, first_v_id, eid, lines)

            face_id = eid
            bounds_str = ",".join(f"#{b}" for b in bound_ids)
            lines.append(f"#{face_id}=ADVANCED_FACE('',({bounds_str}),#{surf_id},.T.);")
            face_eids.append(face_id)
            eid += 1

        shell_id = eid
        faces_str = ",".join(f"#{fid}" for fid in face_eids)
        lines.append(f"#{shell_id}=CLOSED_SHELL('',({faces_str}));")
        eid += 1

        solid_brep_id = eid
        lines.append(f"#{solid_brep_id}=MANIFOLD_SOLID_BREP('{part_name}',#{shell_id});")
        eid += 1

        rep_id = eid
        lines.append(f"#{rep_id}=ADVANCED_BREP_SHAPE_REPRESENTATION('{part_name}',(#{solid_brep_id}),#1);")
        eid += 1

        lines.append("ENDSEC;")
        lines.append("END-ISO-10303-21;")
        return "\n".join(lines) + "\n"

    @staticmethod
    def export_advanced_brep_to_string(
        solids: Dict[str, Solid],
        header_description: str = "CAD Studio Advanced B-Rep Solid"
    ) -> str:
        """Exporte les corps solides sous forme d'ADVANCED_BREP_SHAPE_REPRESENTATION avec surfaces exactes."""
        from src.core.nexus_kernel.hybrid_solid import NexusSolid
        if not solids:
            return ""
        first_solid = list(solids.values())[0]
        combined = first_solid
        for other in list(solids.values())[1:]:
            if not other.is_empty():
                combined = combined.union(other)
        if combined.is_empty():
            return ""
        nexus_solid = NexusSolid(name=combined.name, internal_manifold=combined.manifold)
        return STEPExporter.export_nexus_brep_to_string(nexus_solid, header_description=header_description)

    @staticmethod
    def export_nexus_solid(nexus_solid: NexusSolid, filepath: str) -> bool:
        """Exporte un NexusSolid au standard STEP AP242 Advanced B-Rep."""
        if not filepath.lower().endswith((".step", ".stp")):
            return False
        abs_path = os.path.abspath(filepath)
        os.path.commonpath([abs_path, abs_path])

        content = STEPExporter.export_nexus_brep_to_string(nexus_solid)
        if not content:
            return False

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        return True

    @staticmethod
    def export_solid(solid: Solid, filepath: str, prefer_advanced_brep: bool = True) -> bool:
        """Exporte un corps solide en fichier STEP ISO 10303-21."""
        return STEPExporter.export_multiple_solids({"solid": solid}, filepath, prefer_advanced_brep=prefer_advanced_brep)

    @staticmethod
    def export_multiple_solids(
        solids: Dict[str, Solid],
        filepath: str,
        prefer_advanced_brep: bool = True
    ) -> bool:
        """Exporte l'ensemble des corps solides du projet dans un fichier STEP unique."""
        if not filepath.lower().endswith((".step", ".stp")):
            return False
        abs_path = os.path.abspath(filepath)
        os.path.commonpath([abs_path, abs_path])

        if prefer_advanced_brep:
            content = STEPExporter.export_advanced_brep_to_string(solids)
            if not content:
                content = STEPExporter.export_to_string(solids)
        else:
            content = STEPExporter.export_to_string(solids)

        if not content:
            return False

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        return True

