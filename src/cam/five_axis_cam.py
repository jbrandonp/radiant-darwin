"""
Module de génération de trajectoires d'usinage 5-axes sans gouges (5-Axis Gouge-Free CAM).
Gère l'orientation continue de l'outil (Lead & Tilt), la détection de collision
avec l'enveloppe du porte-outil et la post-synchronisation cinématique machine.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Tuple, Optional
import numpy as np

from src.core.types import Vector3D


class MachineKinematics5Axis(Enum):
    """Configurations cinématiques standard des centres d'usinage 5-axes."""
    TABLE_TABLE_AC = "table_table_ac"  # Table basculante A et plateau rotatif C
    HEAD_TABLE_BC = "head_table_bc"    # Tête basculante B et table rotative C
    HEAD_HEAD_AB = "head_head_ab"      # Tête à double orientation continue A et B


@dataclass
class ToolHolderGeometry:
    """Enveloppe géométrique de la fraise et du porte-outil (Minkowski Hull)."""
    cutter_radius: float          # Rayon de la partie coupante (mm)
    flute_length: float           # Longueur taillée active (mm)
    shank_radius: float           # Rayon du corps de fraise (mm)
    shank_length: float           # Longueur libre avant mandrin (mm)
    holder_bottom_radius: float   # Rayon inférieur du porte-outil (mm)
    holder_top_radius: float      # Rayon supérieur du porte-outil (mm)
    holder_length: float          # Longueur totale du mandrin porte-outil (mm)


@dataclass
class FiveAxisToolPoint:
    """Point d'usinage 5-axes avec coordonnées spatiales et vecteur d'orientation."""
    position: Vector3D
    tool_vector: Vector3D         # Vecteur unitaire directeur de l'axe de la broche
    surface_normal: Vector3D      # Normale locale à la surface nominale
    feed_rate_mm_min: float = 1200.0
    spindle_rpm: float = 12000.0
    rotary_axis_1_deg: float = 0.0 # Ex: Axe A ou B
    rotary_axis_2_deg: float = 0.0 # Ex: Axe C


@dataclass
class FiveAxisGougeReport:
    """Rapport d'analyse de gougeage et d'interférence porte-outil."""
    is_safe: bool
    min_clearance_mm: float
    interference_point: Optional[Vector3D] = None
    corrected_tool_vector: Optional[Vector3D] = None


class FiveAxisGougeChecker:
    """
    Solveur d'orientation 5-axes et détecteur d'interférences de porte-outil.
    Oriente l'outil avec angles d'attaque (Lead) et de roulis (Tilt) pour éviter la vitesse
    de coupe nulle au centre d'une fraise hémisphérique, et corrige les collisions.
    """

    def __init__(self, holder: ToolHolderGeometry, safety_clearance_mm: float = 1.0) -> None:
        """Initialise le vérificateur avec l'enveloppe de la broche."""
        self.holder: ToolHolderGeometry = holder
        self.safety_clearance: float = safety_clearance_mm

    def compute_initial_orientation(
        self,
        surface_normal: Vector3D,
        feed_direction: Vector3D,
        lead_angle_deg: float = 15.0,
        tilt_angle_deg: float = 5.0
    ) -> Vector3D:
        """
        Calcule le vecteur directeur outil nominal à partir des angles de garde (Lead / Tilt).
        Évite le point mort au sommet de l'outil hémisphérique.
        """
        norm_surf = surface_normal.normalized()
        norm_feed = feed_direction.normalized()

        # Vecteur latéral (perpendiculaire à l'avance et à la normale)
        side_vec = norm_feed.cross(norm_surf).normalized()
        actual_feed = norm_surf.cross(side_vec).normalized()

        lead_rad = math.radians(lead_angle_deg)
        tilt_rad = math.radians(tilt_angle_deg)

        # Orientation combinant la normale, l'inclinaison avant (lead) et latérale (tilt)
        vec_x = norm_surf.x * math.cos(lead_rad) * math.cos(tilt_rad) + actual_feed.x * math.sin(lead_rad) + side_vec.x * math.sin(tilt_rad)
        vec_y = norm_surf.y * math.cos(lead_rad) * math.cos(tilt_rad) + actual_feed.y * math.sin(lead_rad) + side_vec.y * math.sin(tilt_rad)
        vec_z = norm_surf.z * math.cos(lead_rad) * math.cos(tilt_rad) + actual_feed.z * math.sin(lead_rad) + side_vec.z * math.sin(tilt_rad)

        res = Vector3D(vec_x, vec_y, vec_z)
        return res.normalized()

    def check_and_correct_point(
        self,
        tip_pos: Vector3D,
        initial_tool_vec: Vector3D,
        obstacle_points: List[Vector3D],
        max_tilt_correction_deg: float = 45.0
    ) -> FiveAxisGougeReport:
        """
        Vérifie la pénétration de l'enveloppe porte-outil dans les parois voisines de la pièce
        et incline dynamiquement l'outil jusqu'à dégager la surépaisseur de sécurité.
        """
        current_vec = initial_tool_vec.normalized()
        step_rad = math.radians(2.0)
        max_steps = int(max_tilt_correction_deg / 2.0)

        for _ in range(max_steps + 1):
            clearance, collision_pt, rad_dir = self._eval_holder_clearance(tip_pos, current_vec, obstacle_points)
            if clearance >= self.safety_clearance:
                return FiveAxisGougeReport(
                    is_safe=True,
                    min_clearance_mm=clearance,
                    interference_point=None,
                    corrected_tool_vector=current_vec
                )

            # Inflexion corrective : inclinaison du vecteur outil dans la direction opposée à l'obstacle (-rad_dir)
            if rad_dir is not None:
                repulsion_dir = -rad_dir.normalized()
                rotated_vec = (current_vec + repulsion_dir * math.sin(step_rad)).normalized()
                current_vec = rotated_vec
            else:
                break

        return FiveAxisGougeReport(
            is_safe=False,
            min_clearance_mm=0.0,
            interference_point=collision_pt,
            corrected_tool_vector=current_vec
        )

    def _eval_holder_clearance(
        self,
        tip_pos: Vector3D,
        tool_vec: Vector3D,
        obstacles: List[Vector3D]
    ) -> Tuple[float, Optional[Vector3D], Optional[Vector3D]]:
        """
        Calcule la distance minimale entre les points obstacles et l'axe tronconique du porte-outil.
        Retourne (clearance, pire_point, direction_radiale_axe_vers_obstacle).
        """
        min_dist = float("inf")
        worst_point: Optional[Vector3D] = None
        worst_radial: Optional[Vector3D] = None

        total_length = self.holder.flute_length + self.holder.shank_length + self.holder.holder_length
        holder_start = self.holder.flute_length + self.holder.shank_length

        for pt in obstacles:
            to_pt = pt - tip_pos
            proj_dist = to_pt.dot(tool_vec)

            # Si le point est en arrière de la pointe dans la zone du porte-outil
            if 0.0 <= proj_dist <= total_length:
                radial_vec = to_pt - (tool_vec * proj_dist)
                dist_to_axis = radial_vec.length()

                # Calcul du rayon local d'enveloppe à cette hauteur
                local_radius = self._get_envelope_radius_at(proj_dist, holder_start, total_length)
                clearance = dist_to_axis - local_radius

                if clearance < min_dist:
                    min_dist = clearance
                    worst_point = pt
                    worst_radial = radial_vec

        if min_dist == float("inf"):
            return 100.0, None, None
        return min_dist, worst_point, worst_radial

    def _get_envelope_radius_at(self, dist_from_tip: float, holder_start: float, total_length: float) -> float:
        """Retourne le rayon de l'enveloppe mécanique à une cote axiale donnée."""
        if dist_from_tip <= self.holder.flute_length:
            return self.holder.cutter_radius
        if dist_from_tip <= holder_start:
            return self.holder.shank_radius
        
        # Cône du mandrin porte-outil
        t = (dist_from_tip - holder_start) / max(1e-6, (total_length - holder_start))
        return self.holder.holder_bottom_radius + t * (self.holder.holder_top_radius - self.holder.holder_bottom_radius)

    def convert_vector_to_rotary_angles(
        self,
        tool_vec: Vector3D,
        kinematics: MachineKinematics5Axis
    ) -> Tuple[float, float]:
        """
        Calcule les angles articulaires machine (ex: Table AC ou Tête BC) à partir du vecteur 3D unitaire.
        """
        vz = max(-1.0, min(1.0, tool_vec.z))
        tilt_angle = math.degrees(math.acos(vz))  # Angle par rapport à la verticale
        azimuth_angle = math.degrees(math.atan2(tool_vec.y, tool_vec.x))

        if kinematics == MachineKinematics5Axis.TABLE_TABLE_AC:
            axis_a = tilt_angle
            axis_c = azimuth_angle
            return axis_a, axis_c
        elif kinematics == MachineKinematics5Axis.HEAD_TABLE_BC:
            axis_b = tilt_angle
            axis_c = azimuth_angle
            return axis_b, axis_c
        else:
            axis_a = tilt_angle
            axis_b = azimuth_angle
            return axis_a, axis_b

    def generate_5axis_gcode_block(self, point: FiveAxisToolPoint, kinematics: MachineKinematics5Axis) -> str:
        """Génère le bloc ISO G-code normalisé avec cinématique 5-axes RTCP (G43.4)."""
        rot1, rot2 = self.convert_vector_to_rotary_angles(point.tool_vector, kinematics)
        axis_names = ("A", "C") if kinematics == MachineKinematics5Axis.TABLE_TABLE_AC else ("B", "C")
        return (
            f"G01 X{point.position.x:.4f} Y{point.position.y:.4f} Z{point.position.z:.4f} "
            f"{axis_names[0]}{rot1:.3f} {axis_names[1]}{rot2:.3f} F{point.feed_rate_mm_min:.1f}"
        )
