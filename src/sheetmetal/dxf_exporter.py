"""
Exportateur de fichiers AutoCAD DXF standard (ASCII R12) pour machines de découpe laser / jet d'eau.
Permet d'exporter les patrons de tôle dépliés (Flat Patterns) et les contours 2D d'esquisse.
"""

from __future__ import annotations
import os
from typing import List, Tuple
from src.core.types import Point2D
from src.sheetmetal.sheet_metal import FlatPattern


class DXFExporter:
    """Générateur de fichiers DXF ASCII compatibles découpeuses laser industrielles."""

    @staticmethod
    def export_flat_pattern_dxf(flat_pattern: FlatPattern, filepath: str) -> str:
        """
        Génère un fichier DXF avec deux calques :
        - Calque 'CUT' : Contour extérieur de découpe laser (lignes continues)
        - Calque 'BEND' : Lignes d'axe de pliage (pour repérage plieuse)
        """
        lines: List[str] = [
            "0", "SECTION",
            "2", "HEADER",
            "9", "$ACADVER",
            "1", "AC1009",  # Format standard AutoCAD R12
            "9", "$MEASUREMENT",
            "70", "1",      # Système métrique (millimètres)
            "0", "ENDSEC",
            "0", "SECTION",
            "2", "TABLES",
            "0", "TABLE",
            "2", "LAYER",
            "70", "2",
            # Calque CUT (Découpe - Blanc/Noir)
            "0", "LAYER",
            "2", "CUT",
            "70", "0",
            "62", "7",      # Couleur 7 (Blanc/Noir)
            "6", "CONTINUOUS",
            # Calque BEND (Pliage - Rouge)
            "0", "LAYER",
            "2", "BEND",
            "70", "0",
            "62", "1",      # Couleur 1 (Rouge)
            "6", "DASHED",
            "0", "ENDTAB",
            "0", "ENDSEC",
            "0", "SECTION",
            "2", "ENTITIES"
        ]

        # 1. Écrire le contour extérieur sur le calque 'CUT'
        pts = flat_pattern.outline_points
        if len(pts) >= 2:
            num = len(pts)
            for i in range(num):
                p_start = pts[i]
                p_end = pts[(i + 1) % num]
                lines.extend([
                    "0", "LINE",
                    "8", "CUT",
                    "10", f"{p_start.u:.4f}",
                    "20", f"{p_start.v:.4f}",
                    "30", "0.0000",
                    "11", f"{p_end.u:.4f}",
                    "21", f"{p_end.v:.4f}",
                    "31", "0.0000"
                ])

        # 2. Écrire les lignes de pliage sur le calque 'BEND'
        for b_start, b_end in flat_pattern.bend_centerlines:
            lines.extend([
                "0", "LINE",
                "8", "BEND",
                "10", f"{b_start.u:.4f}",
                "20", f"{b_start.v:.4f}",
                "30", "0.0000",
                "11", f"{b_end.u:.4f}",
                "21", f"{b_end.v:.4f}",
                "31", "0.0000"
            ])

        lines.extend([
            "0", "ENDSEC",
            "0", "EOF",
            ""
        ])

        dxf_content = "\n".join(lines)
        if filepath:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(dxf_content)

        return dxf_content

    # Alias pratique pour l'exportation standard
    export_dxf = export_flat_pattern_dxf
