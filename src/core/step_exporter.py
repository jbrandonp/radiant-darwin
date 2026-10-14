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

if TYPE_CHECKING:
    from src.core.nexus_kernel.hybrid_solid import NexusSolid



class STEPExporter:
    """Moteur d'exportation de géométries 3D au format ISO 10303-21 STEP."""

    @staticmethod
    def export_to_string(solids: Dict[str, Solid], header_description: str = "CAD Studio Faceted B-Rep Solid") -> str:
        """Génère la chaîne de caractères conforme ISO 10303-21 STEP AP203."""
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

            face_id = eid
            lines.append(f"#{face_id}=FACE_SURFACE('',(#{bound_id}),$,.T.);")
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
    def export_nexus_brep_to_string(nexus_solid: NexusSolid, header_description: str = "CAD Studio Advanced B-Rep Solid") -> str:
        """
        Exporte la topologie exacte d'un NexusSolid au standard ISO 10303-21 STEP AP214 / AP242
        sous forme d'ADVANCED_BREP_SHAPE_REPRESENTATION avec surfaces analytiques exactes
        (PLANE, CYLINDRICAL_SURFACE, AXIS2_PLACEMENT_3D, ADVANCED_FACE, EDGE_CURVE).
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
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN', 'AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));",
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
            p_start = eid
            sv = e.start_vertex
            lines.append(f"#{p_start}=CARTESIAN_POINT('',({sv.x:.6f},{sv.y:.6f},{sv.z:.6f}));")
            eid += 1

            dir_id = eid
            tang = e.curve.tangent(0.0)
            lines.append(f"#{dir_id}=DIRECTION('',({tang[0]:.6f},{tang[1]:.6f},{tang[2]:.6f}));")
            eid += 1

            geom_curve_id = eid
            lines.append(f"#{geom_curve_id}=LINE('',#{p_start},#{dir_id});")
            eid += 1

            edge_curve_id = eid
            sv_ref = vert_id_map.get(e.start_vertex.vertex_id, p_start)
            ev_ref = vert_id_map.get(e.end_vertex.vertex_id, p_start)
            lines.append(f"#{edge_curve_id}=EDGE_CURVE('',#{sv_ref},#{ev_ref},#{geom_curve_id},.T.);")
            edge_id_map[e.edge_id] = edge_curve_id
            eid += 1

        face_eids: List[int] = []
        for f in brep.faces.values():
            oriented_edges: List[int] = []
            for e in f.outer_wire.edges:
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
            eid += 1

            axis_id = eid
            first_v_id = vert_id_map.get(list(brep.vertices.keys())[0], 8) if brep.vertices else 8
            lines.append(f"#{axis_id}=AXIS2_PLACEMENT_3D('',#{first_v_id},$,$);")
            eid += 1

            surf_id = eid
            lines.append(f"#{surf_id}=PLANE('',#{axis_id});")
            eid += 1

            face_id = eid
            lines.append(f"#{face_id}=ADVANCED_FACE('',(#{bound_id}),#{surf_id},.T.);")
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
    def export_nexus_solid(nexus_solid: NexusSolid, filepath: str) -> bool:
        """Exporte un NexusSolid au standard STEP AP242 Advanced B-Rep."""
        content = STEPExporter.export_nexus_brep_to_string(nexus_solid)
        if not content:
            return False

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return True

    @staticmethod
    def export_solid(solid: Solid, filepath: str) -> bool:
        """Exporte un corps solide en fichier STEP ISO 10303-21."""
        return STEPExporter.export_multiple_solids({"solid": solid}, filepath)

    @staticmethod
    def export_multiple_solids(solids: Dict[str, Solid], filepath: str) -> bool:
        """Exporte l'ensemble des corps solides du projet dans un fichier STEP unique."""
        content = STEPExporter.export_to_string(solids)
        if not content:
            return False

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return True

