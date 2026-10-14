"""
Moteur de FAO / CAM (Fabrication Assistée par Ordinateur) style Autodesk Fusion 360.
Génère les parcours d'outils 2.5D (Surfaçage, Contournage, Poche, Perçage)
et exporte le code d'usinage G-Code standard (GRBL / ISO).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple, Dict, Optional
import os
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import Solid


class ToolType(Enum):
    """Types d'outils de coupe pour fraiseuse CNC."""
    END_MILL = "end_mill"        # Fraise droite 2 ou 4 dents
    BALL_NOSE = "ball_nose"      # Fraise hémisphérique
    DRILL = "drill"              # Foret hélicoïdal


@dataclass
class CNCTool:
    """Outil d'usinage CNC paramétré."""
    tool_id: int
    name: str
    tool_type: ToolType
    diameter_mm: float
    flute_length_mm: float
    feedrate_mm_min: float = 800.0     # Vitesse d'avance de coupe (F)
    plunge_rate_mm_min: float = 200.0  # Vitesse de plongée en Z
    spindle_speed_rpm: float = 12000.0 # Vitesse de rotation de la broche (S)


@dataclass
class ToolpathPoint:
    """Point de passage d'un parcours d'outil."""
    pos: Vector3D
    is_rapid: bool = False  # Déplacement rapide G0 si True, avance d'usinage G1 si False


@dataclass
class ToolpathOperation:
    """Opération d'usinage avec liste de passes ordonnées."""
    name: str
    tool: CNCTool
    points: List[ToolpathPoint] = field(default_factory=list)


class CAMEngine:
    """
    Générateur de parcours d'outils d'usinage et post-processeur G-Code.
    """

    def __init__(self) -> None:
        """Initialise le moteur CAM avec un outil par défaut."""
        self.default_tool = CNCTool(
            tool_id=1,
            name="Fraise Droite Ø6mm",
            tool_type=ToolType.END_MILL,
            diameter_mm=6.0,
            flute_length_mm=25.0,
            feedrate_mm_min=900.0,
            plunge_rate_mm_min=250.0,
            spindle_speed_rpm=12000.0
        )
        self.safe_z: float = 5.0      # Hauteur de sécurité de dégagement
        self.stepdown_mm: float = 2.0  # Profondeur de passe en Z

    def generate_facing_toolpath(
        self,
        min_x: float, max_x: float,
        min_y: float, max_y: float,
        stock_z: float,
        target_z: float,
        tool: Optional[CNCTool] = None
    ) -> ToolpathOperation:
        """
        Génère un surfaçage en zigzag pour aplanir la face supérieure du brut.
        """
        active_tool = tool or self.default_tool
        op = ToolpathOperation("Surfaçage (Face Milling)", active_tool)

        x0, x1 = min(min_x, max_x), max(min_x, max_x)
        y0, y1 = min(min_y, max_y), max(min_y, max_y)
        stepover = max(0.1, active_tool.diameter_mm * 0.7)
        stepdown = max(0.1, self.stepdown_mm)
        current_z = stock_z

        if current_z <= target_z:
            current_z = target_z + stepdown

        clearance_z = max(stock_z + self.safe_z, target_z + self.safe_z, self.safe_z)

        while current_z > target_z:
            current_z = max(target_z, current_z - stepdown)
            y = y0
            direction = 1

            # Dégagement rapide vers le point de départ
            op.points.append(ToolpathPoint(Vector3D(x0, y0, clearance_z), is_rapid=True))
            op.points.append(ToolpathPoint(Vector3D(x0, y0, current_z), is_rapid=False))

            while y <= y1:
                if direction == 1:
                    op.points.append(ToolpathPoint(Vector3D(x1, y, current_z), is_rapid=False))
                else:
                    op.points.append(ToolpathPoint(Vector3D(x0, y, current_z), is_rapid=False))

                y += stepover
                if y <= y1:
                    if direction == 1:
                        op.points.append(ToolpathPoint(Vector3D(x1, y, current_z), is_rapid=False))
                    else:
                        op.points.append(ToolpathPoint(Vector3D(x0, y, current_z), is_rapid=False))
                direction = -direction

            if op.points:
                op.points.append(ToolpathPoint(Vector3D(op.points[-1].pos.x, op.points[-1].pos.y, clearance_z), is_rapid=True))

        return op

    def generate_contour_toolpath(
        self,
        solid: Solid,
        depth_mm: float,
        tool: Optional[CNCTool] = None
    ) -> ToolpathOperation:
        """
        Génère un contournage extérieur de la pièce par passes successives en Z.
        """
        active_tool = tool or self.default_tool
        op = ToolpathOperation("Contournage (2D Contour)", active_tool)

        b_min, b_max = solid.bounding_box()
        tool_r = active_tool.diameter_mm / 2.0

        # Contour rectangulaire décalé du rayon de l'outil
        x0, x1 = b_min.x - tool_r, b_max.x + tool_r
        y0, y1 = b_min.y - tool_r, b_max.y + tool_r

        start_z = b_max.z
        clearance_z = max(start_z + self.safe_z, self.safe_z)
        safe_depth = max(0.1, abs(depth_mm))
        num_passes = max(1, int(np.ceil(safe_depth / self.stepdown_mm)))
        z_step = safe_depth / num_passes

        # Position initiale rapide
        op.points.append(ToolpathPoint(Vector3D(x0, y0, clearance_z), is_rapid=True))

        current_z = 0.0
        for _ in range(num_passes):
            current_z -= z_step
            # Plongée
            op.points.append(ToolpathPoint(Vector3D(x0, y0, current_z), is_rapid=False))
            # Tour complet
            op.points.append(ToolpathPoint(Vector3D(x1, y0, current_z), is_rapid=False))
            op.points.append(ToolpathPoint(Vector3D(x1, y1, current_z), is_rapid=False))
            op.points.append(ToolpathPoint(Vector3D(x0, y1, current_z), is_rapid=False))
            op.points.append(ToolpathPoint(Vector3D(x0, y0, current_z), is_rapid=False))

        # Dégagement final
        op.points.append(ToolpathPoint(Vector3D(x0, y0, clearance_z), is_rapid=True))
        return op

    def export_gcode(self, operations: List[ToolpathOperation], filepath: str) -> str:
        """
        Post-processe les opérations en G-Code ISO standard prêt pour fraiseuse CNC.
        Compatible GRBL, Marlin, LinuxCNC, Mach3.
        """
        lines: List[str] = [
            "; ==========================================",
            "; G-Code généré par CAD Studio (CAM Module)",
            "; Date de génération : 2026",
            "; ==========================================",
            "G21 ; Unités en millimètres",
            "G90 ; Coordonnées absolues",
            "G17 ; Sélection plan XY",
            "G94 ; Avance en mm/min",
            f"G0 Z{self.safe_z:.3f} ; Dégagement de sécurité",
            ""
        ]

        for op_idx, op in enumerate(operations):
            tool = op.tool
            lines.append(f"; --- Opération {op_idx + 1} : {op.name} ---")
            lines.append(f"T{tool.tool_id} M6 ; Changement d'outil : {tool.name}")
            lines.append(f"S{int(tool.spindle_speed_rpm)} M3 ; Démarrage broche sens horaire")
            lines.append(f"G4 P1.5 ; Temporisation démarrage broche")
            lines.append(f"G0 Z{self.safe_z:.3f}")

            feed = tool.feedrate_mm_min
            plunge = tool.plunge_rate_mm_min

            last_z = self.safe_z
            for pt in op.points:
                p = pt.pos
                if pt.is_rapid:
                    lines.append(f"G0 X{p.x:.3f} Y{p.y:.3f} Z{p.z:.3f}")
                else:
                    # Choisir l'avance selon si on plonge ou si on coupe horizontalement
                    f_val = plunge if p.z < last_z - 1e-4 else feed
                    lines.append(f"G1 X{p.x:.3f} Y{p.y:.3f} Z{p.z:.3f} F{f_val:.1f}")
                last_z = p.z

            lines.append(f"G0 Z{self.safe_z:.3f}")
            lines.append("")

        lines.extend([
            "M5 ; Arrêt de la broche",
            f"G0 Z{self.safe_z * 3:.3f} ; Retour position haute",
            "G0 X0.000 Y0.000 ; Retour origine WCS",
            "M30 ; Fin du programme CNC",
            ""
        ])

        gcode_content = "\n".join(lines)
        if filepath:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(gcode_content)

        return gcode_content
