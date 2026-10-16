"""
Package unifié d'Entrées/Sorties et Passerelles de Formats CAO/FAO (CAD Studio I/O Layer).
Expose l'ensemble des fonctionnalités d'importation et d'exportation de données techniques :
- Façade unifiée de haut niveau : CADIOFacade
- Formats d'échange standardisés 3D : STEP (AP203/214/242), IGES 5.3, glTF 2.0 PBR, 3MF
- Formats de maillage pour fabrication additive : STL (ASCII/Binaire), OBJ, PLY
- Formats vectoriels 2D & Mises en plan : DXF (AutoCAD), SVG vectoriel

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

# 1. Façade unifiée haut niveau
from src.io.facade import CADIOFacade

# 2. Importateurs & Exportateurs STEP ISO 10303-21
from src.core.step_importer import (
    STEPImporter,
    STEPGeometricContext,
    STEPModel,
)
from src.core.step_exporter import STEPExporter

# 3. Exportateur multi-formats (STL, OBJ, PLY)
from src.core.exporter import CADExporter

# 4. Importateur et Exportateur DXF (2D Esquisses et Tôlerie)
from src.core.dxf_importer import DXFImporter
from src.sheetmetal.dxf_exporter import DXFExporter

# 5. Importateur et Exportateur SVG (2D Vectoriel et Mises en plan normalisées ISO)
from src.core.svg_importer import SVGImporter
from src.drawing.svg_exporter import SVGDrawingExporter

# 6. Exportateur fabrication additive avancée 3MF (ISO/IEC 25422)
from src.core.threemf_exporter import ThreeMFExporter

# 7. Exportateurs IGES 5.3 et glTF 2.0 PBR
from src.core.iges_exporter import IgesExporter
from src.core.gltf_exporter import GltfExporter, PbrMaterial

__all__ = [
    # Façade
    "CADIOFacade",
    # STEP
    "STEPImporter",
    "STEPGeometricContext",
    "STEPModel",
    "STEPExporter",
    # STL / OBJ / PLY
    "CADExporter",
    # DXF
    "DXFImporter",
    "DXFExporter",
    # SVG
    "SVGImporter",
    "SVGDrawingExporter",
    # 3MF
    "ThreeMFExporter",
    # IGES & glTF
    "IgesExporter",
    "GltfExporter",
    "PbrMaterial",
]
