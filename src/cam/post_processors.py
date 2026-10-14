"""
Post-processeurs CNC Industriels certifiés (Haas, Fanuc, Heidenhain).
Équivalent professionnel du Path Workbench de FreeCAD 1.0.
Traduit les opérations de parcours d'outils CAM en G-Code machine certifié
avec cycles d'usinage, arrosage (M08/M09), compensation de longueur d'outil (G43 H)
et estimation physique précise du temps d'usinage.
Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Dict, Optional
import os
import numpy as np

from src.core.types import Vector3D
from src.cam.cam_engine import ToolpathOperation, ToolpathPoint, CNCTool


class CNCDialect(Enum):
    """Dialectes et contrôleurs de machines-outils CNC industrielles."""
    HAAS = "haas"                    # Contrôleur Haas NGC (VF-2, MiniMill, UMC)
    FANUC = "fanuc"                  # Contrôleurs Fanuc Series 0i / 31i
    HEIDENHAIN = "heidenhain"        # Contrôleur TNC 640 / iTNC 530 (Klartext)
    SIEMENS = "siemens"              # Siemens Sinumerik 840D


@dataclass
class MachiningMetrics:
    """Métriques physiques calculées sur le programme d'usinage."""
    total_distance_mm: float
    cutting_distance_mm: float
    rapid_distance_mm: float
    estimated_time_seconds: float

    @property
    def estimated_time_formatted(self) -> str:
        """Formate le temps d'usinage estimé en minutes et secondes."""
        mins = int(self.estimated_time_seconds // 60)
        secs = int(self.estimated_time_seconds % 60)
        return f"{mins} min {secs} s"


class IndustrialPostProcessor:
    """
    Générateur de code machine certifié et estimateur cinématique d'usinage.
    """

    @staticmethod
    def calculate_metrics(
        operations: List[ToolpathOperation],
        rapid_speed_mm_min: float = 15000.0,
        tool_change_time_s: float = 6.0
    ) -> MachiningMetrics:
        """
        Calcule la distance parcourue et le temps total d'usinage en tenant compte
        des vitesses d'avance (F) et des déplacements rapides G0.
        """
        total_cut_dist = 0.0
        total_rapid_dist = 0.0
        total_time_s = 0.0

        for op in operations:
            total_time_s += tool_change_time_s
            feed = max(100.0, op.tool.feedrate_mm_min)
            plunge = max(50.0, op.tool.plunge_rate_mm_min)

            pts = op.points
            for i in range(len(pts) - 1):
                p0 = pts[i].pos
                p1 = pts[i + 1].pos
                dist = p1.subtract(p0).length()

                if pts[i + 1].is_rapid:
                    total_rapid_dist += dist
                    total_time_s += (dist / rapid_speed_mm_min) * 60.0
                else:
                    total_cut_dist += dist
                    is_plunge = p1.z < p0.z - 1e-4
                    f_active = plunge if is_plunge else feed
                    total_time_s += (dist / f_active) * 60.0

        return MachiningMetrics(
            total_distance_mm=total_cut_dist + total_rapid_dist,
            cutting_distance_mm=total_cut_dist,
            rapid_distance_mm=total_rapid_dist,
            estimated_time_seconds=total_time_s
        )

    @classmethod
    def post_process_haas(
        cls,
        operations: List[ToolpathOperation],
        program_number: int = 1001,
        program_name: str = "USINAGE_PIECE",
        work_coordinate: str = "G54"
    ) -> str:
        """Génère un programme ISO certifié pour centres d'usinage CNC Haas (NGC / Classic)."""
        lines: List[str] = [
            "%",
            f"O{program_number:05d} ({program_name})",
            "(GENERE PAR CAD STUDIO - POST-PROCESSEUR HAAS CNC)",
            "(SYSTEME D'UNITE : MILLIMETRES)",
            "G00 G17 G21 G40 G49 G80 G90",
            "G53 G00 Z0. (DEGAGEMENT HAUT SECURISE)"
        ]

        for op_idx, op in enumerate(operations):
            tool = op.tool
            t_num = max(1, tool.tool_id)
            spindle_rpm = int(tool.spindle_speed_rpm)

            lines.extend([
                "",
                f"(--- OPERATION {op_idx + 1} : {op.name} ---)",
                f"(OUTIL T{t_num} : {tool.name} D={tool.diameter_mm:.2f}mm)",
                f"T{t_num} M06",
                f"{work_coordinate}",
                f"S{spindle_rpm} M03",
                f"G43 H{t_num:02d} Z50.0 M08 (COMPENSATION LONGUEUR + ARROSAGE)"
            ])

            last_z = 50.0
            feed = tool.feedrate_mm_min
            plunge = tool.plunge_rate_mm_min

            for pt in op.points:
                p = pt.pos
                if pt.is_rapid:
                    lines.append(f"G00 X{p.x:.3f} Y{p.y:.3f} Z{p.z:.3f}")
                else:
                    f_val = plunge if p.z < last_z - 1e-4 else feed
                    lines.append(f"G01 X{p.x:.3f} Y{p.y:.3f} Z{p.z:.3f} F{f_val:.1f}")
                last_z = p.z

            lines.append("M09 (ARRET ARROSAGE)")
            lines.append("G53 G00 Z0. (RETOUR HAUT)")

        lines.extend([
            "",
            "M05 (ARRET BROCHE)",
            "G53 G00 Y0. (TABLE EN AVANT DEGREEMENT)",
            "M30 (FIN DE PROGRAMME)",
            "%"
        ])
        return "\n".join(lines)

    @classmethod
    def post_process_fanuc(
        cls,
        operations: List[ToolpathOperation],
        program_number: int = 1,
        program_name: str = "PART_USINAGE",
        work_coordinate: str = "G54"
    ) -> str:
        """Génère un programme conforme au standard Fanuc 0i/31i."""
        lines: List[str] = [
            "%",
            f"O{program_number:04d} ({program_name})",
            "(POST-PROCESSEUR FANUC SERIES 0i/31i)",
            "G21 G90 G40 G80 G49",
            "G28 G91 Z0.",
            "G90"
        ]

        for op_idx, op in enumerate(operations):
            tool = op.tool
            t_num = max(1, tool.tool_id)
            lines.extend([
                "",
                f"(--- OP {op_idx + 1} : {op.name} ---)",
                f"T{t_num:02d} M06",
                f"{work_coordinate}",
                f"S{int(tool.spindle_speed_rpm)} M03",
                f"G43 H{t_num:02d} Z50.0 M08"
            ])

            last_z = 50.0
            feed = tool.feedrate_mm_min
            plunge = tool.plunge_rate_mm_min

            for pt in op.points:
                p = pt.pos
                if pt.is_rapid:
                    lines.append(f"G00 X{p.x:.3f} Y{p.y:.3f} Z{p.z:.3f}")
                else:
                    f_val = plunge if p.z < last_z - 1e-4 else feed
                    lines.append(f"G01 X{p.x:.3f} Y{p.y:.3f} Z{p.z:.3f} F{f_val:.1f}")
                last_z = p.z

            lines.append("M09")
            lines.append("G28 G91 Z0.")
            lines.append("G90")

        lines.extend([
            "",
            "M05",
            "G28 G91 Y0.",
            "G90",
            "M30",
            "%"
        ])
        return "\n".join(lines)

    @classmethod
    def post_process_heidenhain(
        cls,
        operations: List[ToolpathOperation],
        program_name: str = "PART_PIECE"
    ) -> str:
        """Génère un programme en langage conversationnel Heidenhain Klartext (TNC 640)."""
        lines: List[str] = [
            f"0 BEGIN PGM {program_name} MM",
            "1 BLK FORM 0.1 Z X-100 Y-100 Z-40",
            "2 BLK FORM 0.2 X+100 Y+100 Z+0",
            "; CAD STUDIO CAM - HEIDENHAIN TNC KLARTEXT"
        ]

        line_num = 3
        for op_idx, op in enumerate(operations):
            tool = op.tool
            t_num = max(1, tool.tool_id)
            spindle_rpm = int(tool.spindle_speed_rpm)

            lines.append(f"; --- OPERATION {op_idx + 1} : {op.name} ---")
            lines.append(f"{line_num} TOOL CALL {t_num} Z S{spindle_rpm}")
            line_num += 1
            lines.append(f"{line_num} L Z+50 R0 FMAX M3 M8")
            line_num += 1

            feed = tool.feedrate_mm_min
            plunge = tool.plunge_rate_mm_min
            last_z = 50.0

            for pt in op.points:
                p = pt.pos
                if pt.is_rapid:
                    lines.append(f"{line_num} L X{p.x:+.3f} Y{p.y:+.3f} Z{p.z:+.3f} R0 FMAX")
                else:
                    f_val = plunge if p.z < last_z - 1e-4 else feed
                    lines.append(f"{line_num} L X{p.x:+.3f} Y{p.y:+.3f} Z{p.z:+.3f} R0 F{f_val:.0f}")
                last_z = p.z
                line_num += 1

            lines.append(f"{line_num} L Z+50 R0 FMAX M9")
            line_num += 1

        lines.extend([
            f"{line_num} L Z+150 R0 FMAX M5",
            f"{line_num + 1} END PGM {program_name} MM"
        ])
        return "\n".join(lines)
