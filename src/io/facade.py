"""
Façade unifiée pour toutes les opérations d'entrée/sortie (CAD Studio I/O Gateway).
Fournit un point d'entrée unique et fortement typé pour l'import/export de tous les formats :
- 3D B-Rep & Maillages : STEP (ISO 10303-21), IGES, STL, OBJ, PLY, glTF 2.0, 3MF
- 2D Esquisses & Découpe : DXF (AutoCAD R12/2000+), SVG vectoriel
- Dessin Technique : SVG normalisé ISO
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple, Union

from src.core.geometry import Solid
from src.core.sketch import Sketch2D
from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.core.exporter import CADExporter
from src.core.step_importer import STEPImporter, STEPGeometricContext
from src.core.step_exporter import STEPExporter
from src.core.dxf_importer import DXFImporter
from src.sheetmetal.dxf_exporter import DXFExporter
from src.core.svg_importer import SVGImporter
from src.drawing.svg_exporter import SVGDrawingExporter
from src.core.threemf_exporter import ThreeMFExporter
from src.sheetmetal.sheet_metal import FlatPattern
from src.drawing.drawing_generator import TechnicalSheet


class CADIOFacade:
    """Façade unifiée d'E/S (Gateway) pour l'importation et l'exportation de données CAO/FAO."""

    # --- Imports 3D & 2D ---

    @classmethod
    def import_step_context(cls, filepath_or_content: str) -> STEPGeometricContext:
        """Importe et analyse le contexte géométrique complet d'un fichier STEP ISO 10303-21."""
        importer = STEPImporter()
        return importer.import_step(filepath_or_content)

    @classmethod
    def import_step(cls, filepath_or_content: str, solid_name: Optional[str] = None) -> NexusSolid:
        """Importe un fichier ou contenu STEP et reconstruit le solide B-Rep complet NexusSolid."""
        importer = STEPImporter()
        return importer.import_to_nexus_solid(filepath_or_content, solid_name=solid_name)

    @classmethod
    def import_dxf_to_sketch(cls, filepath: str) -> Sketch2D:
        """Importe un fichier DXF 2D dans une esquisse paramétrique Sketch2D."""
        return DXFImporter.import_dxf_to_sketch(filepath)

    @classmethod
    def import_svg_to_sketch(cls, filepath: str) -> Sketch2D:
        """Importe un fichier SVG vectoriel dans une esquisse paramétrique Sketch2D."""
        return SVGImporter.import_svg_to_sketch(filepath)

    # --- Exports 3D ---

    @classmethod
    def export_step(cls, solids: Union[Solid, Dict[str, Solid], NexusSolid], filepath: str) -> bool:
        """Exporte un ou plusieurs solides au format STEP ISO 10303-21."""
        if isinstance(solids, NexusSolid):
            return STEPExporter.export_nexus_solid(solids, filepath)
        if isinstance(solids, Solid):
            return STEPExporter.export_solid(solids, filepath)
        return STEPExporter.export_multiple_solids(solids, filepath)

    @classmethod
    def export_mesh(cls, bodies: Dict[str, Solid], filepath: str, fmt: str = "stl") -> bool:
        """Exporte les corps solides au format de maillage spécifié (stl, obj, ply)."""
        fmt_clean = fmt.lower().strip().lstrip(".")
        if fmt_clean == "stl":
            return CADExporter.export_stl(bodies, filepath)
        if fmt_clean == "obj":
            return CADExporter.export_obj(bodies, filepath)
        if fmt_clean == "ply":
            return CADExporter.export_ply(bodies, filepath)
        raise ValueError(f"Format de maillage non supporté : '{fmt}'. Formats acceptés : stl, obj, ply")

    @classmethod
    def export_3mf(cls, filepath: str, solids: Optional[Dict[str, Solid]] = None) -> bool:
        """Exporte un modèle au format 3MF conteneur OPC ZIP pour fabrication additive."""
        return ThreeMFExporter.export_to_file(filepath, solids=solids)

    # --- Exports 2D & Mises en Plan ---

    @classmethod
    def export_flat_pattern_dxf(cls, flat_pattern: FlatPattern, filepath: str) -> str:
        """Exporte un patron déplié de tôlerie industrielle au format DXF."""
        return DXFExporter.export_flat_pattern_dxf(flat_pattern, filepath)

    @classmethod
    def export_technical_drawing_svg(cls, sheet: TechnicalSheet, filepath: str) -> str:
        """Exporte une mise en plan technique normalisée ISO au format vectoriel SVG."""
        return SVGDrawingExporter.export_svg(sheet, filepath)
