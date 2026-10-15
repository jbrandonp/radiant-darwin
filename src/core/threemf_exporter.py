"""
Exportateur standard 3MF (3D Manufacturing Format - ISO/IEC 25422).
Génère un conteneur OPC ZIP conforme incluant le modèle 3D surfacique
et l'extension Beam Lattice pour la fabrication additive avancée.
Conforme aux standards de typage strict et SonarQube (complexité cognitive <= 25).
"""

from __future__ import annotations
import io
import os
import zipfile
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.core.geometry import Solid
from src.core.types import MeshBuffer, Vector3D, ColorRGBA
from src.core.threemf_types import (
    BeamLatticeTopology,
    ThreeMFMaterial,
    BeamCapMode,
    BeamBallMode,
)


class ThreeMFExporter:
    """Moteur d'exportation de maquettes pour la fabrication additive au format 3MF."""

    XML_NS_CORE: str = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    XML_NS_BEAM: str = "http://schemas.microsoft.com/3dmanufacturing/beamlattice/2017/02"

    @classmethod
    def export_to_bytes(
        cls,
        solids: Optional[Dict[str, Solid]] = None,
        lattices: Optional[Dict[str, BeamLatticeTopology]] = None,
        material: Optional[ThreeMFMaterial] = None,
        part_name: str = "RadiantPart"
    ) -> bytes:
        """Génère les octets binaires d'un conteneur 3MF OPC ZIP en mémoire."""
        xml_content = cls.build_model_xml(solids, lattices, material, part_name)
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", cls._build_content_types_xml())
            zf.writestr("_rels/.rels", cls._build_rels_xml())
            zf.writestr("3D/3dmodel.model", xml_content)
        return bio.getvalue()

    @classmethod
    def export_to_file(
        cls,
        filepath: str,
        solids: Optional[Dict[str, Solid]] = None,
        lattices: Optional[Dict[str, BeamLatticeTopology]] = None,
        material: Optional[ThreeMFMaterial] = None,
        part_name: str = "RadiantPart"
    ) -> bool:
        """Exporte les solides et/ou réseaux réticulaires dans une archive .3mf."""
        if not filepath.lower().endswith(".3mf"):
            raise ValueError(f"Extension de fichier non supportée pour l'export 3MF : '{filepath}'")
        safe_path = os.path.abspath(filepath)
        dir_name = os.path.dirname(safe_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        try:
            zip_bytes = cls.export_to_bytes(solids, lattices, material, part_name)
            with open(safe_path, "wb") as f:
                f.write(zip_bytes)
            return True
        except Exception as err:
            print(f"Erreur lors de l'exportation 3MF : {err}")
            return False

    @classmethod
    def _build_content_types_xml(cls) -> str:
        """Génère le manifeste de types MIME [Content_Types].xml."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
            '</Types>\n'
        )

    @classmethod
    def _build_rels_xml(cls) -> str:
        """Génère le registre de relations racines _rels/.rels."""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>\n'
        )

    @classmethod
    def build_model_xml(
        cls,
        solids: Optional[Dict[str, Solid]] = None,
        lattices: Optional[Dict[str, BeamLatticeTopology]] = None,
        material: Optional[ThreeMFMaterial] = None,
        part_name: str = "RadiantPart"
    ) -> str:
        """Construit le document XML principal 3D/3dmodel.model."""
        has_beams = bool(lattices and any(not lat.is_empty() for lat in lattices.values()))
        ns_decl = f'xmlns="{cls.XML_NS_CORE}"'
        if has_beams:
            ns_decl += f' xmlns:b="{cls.XML_NS_BEAM}" requiredextensions="b"'

        mat = material if material is not None else ThreeMFMaterial()
        lines: List[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<model unit="millimeter" xml:lang="en-US" {ns_decl}>',
            '  <metadata name="Title">CAD Studio Generative 3MF Model</metadata>',
            '  <metadata name="Application">Radiant-Darwin CAD Studio</metadata>',
            '  <resources>',
            f'    <basematerials id="1">',
            f'      <base name="{mat.name}" displaycolor="{cls._format_color(mat.color)}"/>',
            '    </basematerials>',
        ]

        obj_id = 2
        build_items: List[int] = []

        # 1. Export des solides volumiques
        if solids:
            for s_name, solid in solids.items():
                if solid.is_empty():
                    continue
                buf = solid.to_mesh_buffer()
                if buf.is_empty():
                    continue
                mesh_xml = cls._build_mesh_object_xml(obj_id, s_name, buf)
                lines.append(mesh_xml)
                build_items.append(obj_id)
                obj_id += 1

        # 2. Export des treillis réticulaires (Beam Lattice)
        if lattices:
            for l_name, lattice in lattices.items():
                if lattice.is_empty():
                    continue
                lattice_xml = cls._build_lattice_object_xml(obj_id, l_name, lattice)
                lines.append(lattice_xml)
                build_items.append(obj_id)
                obj_id += 1

        lines.append('  </resources>')
        lines.append('  <build>')
        for b_id in build_items:
            lines.append(f'    <item objectid="{b_id}"/>')
        lines.append('  </build>')
        lines.append('</model>\n')

        return '\n'.join(lines)

    @classmethod
    def _format_color(cls, col: ColorRGBA) -> str:
        """Convertit une couleur RGBA en format hexadécimal #RRGGBBAA pour 3MF."""
        r = int(np.clip(col.r * 255.0, 0.0, 255.0))
        g = int(np.clip(col.g * 255.0, 0.0, 255.0))
        b = int(np.clip(col.b * 255.0, 0.0, 255.0))
        a = int(np.clip(col.a * 255.0, 0.0, 255.0))
        return f"#{r:02X}{g:02X}{b:02X}{a:02X}"

    @classmethod
    def _build_mesh_object_xml(cls, object_id: int, name: str, buf: MeshBuffer) -> str:
        """Génère l'entité <object> pour un maillage de surface fermé."""
        lines: List[str] = [
            f'    <object id="{object_id}" type="model" name="{name}" pid="1" pindex="0">',
            '      <mesh>',
            '        <vertices>',
        ]
        for v in buf.vertices:
            lines.append(f'          <vertex x="{v[0]:.6f}" y="{v[1]:.6f}" z="{v[2]:.6f}"/>')
        lines.append('        </vertices>')
        lines.append('        <triangles>')
        for f in buf.faces:
            lines.append(f'          <triangle v1="{int(f[0])}" v2="{int(f[1])}" v3="{int(f[2])}"/>')
        lines.append('        </triangles>')
        lines.append('      </mesh>')
        lines.append('    </object>')
        return '\n'.join(lines)

    @classmethod
    def _build_lattice_object_xml(
        cls,
        object_id: int,
        name: str,
        lattice: BeamLatticeTopology
    ) -> str:
        """Génère l'entité <object> contenant un treillis Beam Lattice."""
        lines: List[str] = [
            f'    <object id="{object_id}" type="model" name="{name}">',
            '      <mesh>',
            '        <vertices>',
        ]
        for node in lattice.nodes:
            lines.append(f'          <vertex x="{node.x:.6f}" y="{node.y:.6f}" z="{node.z:.6f}"/>')
        lines.append('        </vertices>')
        lines.append(f'        <b:beamlattice minlength="{lattice.min_length:.4f}"'
                     f' cap="{lattice.beams[0].cap_mode.value if lattice.beams else "sphere"}"'
                     f' ballmode="{lattice.ball_mode.value}">')
        lines.append('          <b:beams>')
        for beam in lattice.beams:
            lines.append(
                f'            <b:beam v1="{beam.node_idx_1}" v2="{beam.node_idx_2}" '
                f'r1="{beam.radius_1:.4f}" r2="{beam.radius_2:.4f}" cap="{beam.cap_mode.value}"/>'
            )
        lines.append('          </b:beams>')
        if lattice.balls:
            lines.append('          <b:balls>')
            for ball in lattice.balls:
                lines.append(f'            <b:ball vindex="{ball.node_idx}" r="{ball.radius:.4f}"/>')
            lines.append('          </b:balls>')
        lines.append('        </b:beamlattice>')
        lines.append('      </mesh>')
        lines.append('    </object>')
        return '\n'.join(lines)


def export_3mf_to_bytes(
    solids: Optional[Dict[str, Solid]] = None,
    lattices: Optional[Dict[str, BeamLatticeTopology]] = None,
    material: Optional[ThreeMFMaterial] = None,
    part_name: str = "RadiantPart"
) -> bytes:
    """Helper direct pour exporter en octets 3MF."""
    return ThreeMFExporter.export_to_bytes(solids, lattices, material, part_name)

