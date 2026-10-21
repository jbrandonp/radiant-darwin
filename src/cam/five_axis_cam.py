"""
Module de génération de trajectoires d'usinage 5-axes sans gouges (5-Axis Gouge-Free CAM).
Gère l'orientation continue de l'outil (Lead & Tilt), la détection de collision
avec l'enveloppe du porte-outil, la cinématique RTCP (Rotational Tool Center Point G43.4/TCPM)
et l'interpolation circulaire/hélicoïdale G02/G03.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Tuple, Optional, Sequence
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

        side_vec = norm_feed.cross(norm_surf).normalized()
        actual_feed = norm_surf.cross(side_vec).normalized()

        lead_rad = math.radians(lead_angle_deg)
        tilt_rad = math.radians(tilt_angle_deg)

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

            if 0.0 <= proj_dist <= total_length:
                radial_vec = to_pt - (tool_vec * proj_dist)
                dist_to_axis = radial_vec.length()

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
        
        t = (dist_from_tip - holder_start) / max(1e-6, (total_length - holder_start))
        return self.holder.holder_bottom_radius + t * (self.holder.holder_top_radius - self.holder.holder_bottom_radius)

    def convert_vector_to_rotary_angles(
        self,
        tool_vec: Vector3D,
        kinematics: MachineKinematics5Axis
    ) -> Tuple[float, float]:
        """
        Calcule les angles articulaires machine à partir du vecteur 3D unitaire.
        """
        vz = max(-1.0, min(1.0, tool_vec.z))
        tilt_angle = math.degrees(math.acos(vz))
        azimuth_angle = math.degrees(math.atan2(tool_vec.y, tool_vec.x))

        if kinematics == MachineKinematics5Axis.TABLE_TABLE_AC:
            axis_a = tilt_angle
            axis_c = azimuth_angle
            return axis_a, axis_c
        elif kinematics == MachineKinematics5Axis.HEAD_TABLE_BC:
            axis_b = tilt_angle
            axis_c = azimuth_angle
            return axis_b, axis_c
        elif kinematics == MachineKinematics5Axis.HEAD_HEAD_AB:
            # Tête bi-rotative A (autour de X) et B (autour de Y) sans axe vertical Z
            vx = max(-1.0, min(1.0, tool_vec.x))
            axis_b = math.degrees(math.asin(vx))
            axis_a = math.degrees(math.atan2(-tool_vec.y, tool_vec.z))
            return axis_a, axis_b
        else:
            axis_a = tilt_angle
            axis_b = azimuth_angle
            return axis_a, axis_b

    def generate_5axis_gcode_block(self, point: FiveAxisToolPoint, kinematics: MachineKinematics5Axis) -> str:
        """Génère le bloc ISO G-code normalisé avec cinématique 5-axes RTCP (G43.4)."""
        rot1, rot2 = self.convert_vector_to_rotary_angles(point.tool_vector, kinematics)
        if kinematics == MachineKinematics5Axis.TABLE_TABLE_AC:
            axis_names = ("A", "C")
        elif kinematics == MachineKinematics5Axis.HEAD_TABLE_BC:
            axis_names = ("B", "C")
        else:
            axis_names = ("A", "B")
        return (
            f"G01 X{point.position.x:.4f} Y{point.position.y:.4f} Z{point.position.z:.4f} "
            f"{axis_names[0]}{rot1:.3f} {axis_names[1]}{rot2:.3f} F{point.feed_rate_mm_min:.1f}"
        )


class RTCPKinematicsEngine:
    """
    Moteur cinématique RTCP (Rotational Tool Center Point / G43.4 / TCPM).
    Assure les transformations géométriques directes et inverses entre repère pièce et axes machine,
    avec compensation dynamique du point de pivot et de la longueur d'outil.
    """

    def __init__(
        self,
        kinematics_type: MachineKinematics5Axis = MachineKinematics5Axis.TABLE_TABLE_AC,
        pivot_offset_xyz: Tuple[float, float, float] = (0.0, 0.0, 150.0),
        tool_length_gage_mm: float = 120.0
    ) -> None:
        self.kinematics_type: MachineKinematics5Axis = kinematics_type
        self.pivot_offset: np.ndarray = np.array(pivot_offset_xyz, dtype=np.float64)
        self.tool_length: float = float(tool_length_gage_mm)

    def compute_rotation_matrix(self, rot1_deg: float, rot2_deg: float) -> np.ndarray:
        """Calcule la matrice de rotation 3x3 selon la cinématique sélectionnée."""
        r1_rad = math.radians(rot1_deg)
        r2_rad = math.radians(rot2_deg)

        c1, s1 = math.cos(r1_rad), math.sin(r1_rad)
        c2, s2 = math.cos(r2_rad), math.sin(r2_rad)

        if self.kinematics_type == MachineKinematics5Axis.HEAD_HEAD_AB:
            # Tête bi-rotative : axe A autour de X et axe B autour de Y
            rx = np.array([[1.0, 0.0, 0.0], [0.0, c1, -s1], [0.0, s1, c1]], dtype=np.float64)
            ry = np.array([[c2, 0.0, s2], [0.0, 1.0, 0.0], [-s2, 0.0, c2]], dtype=np.float64)
            return (rx @ ry).T

        rz = np.array([[c2, -s2, 0.0], [s2, c2, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        ry = np.array([[c1, 0.0, s1], [0.0, 1.0, 0.0], [-s1, 0.0, c1]], dtype=np.float64)
        r_orient = rz @ ry
        return r_orient.T

    def workpiece_to_machine(
        self,
        workpiece_pos: Vector3D,
        tool_vec: Vector3D
    ) -> Tuple[Vector3D, float, float]:
        """
        Cinématique inverse RTCP : transforme une consigne outil en repère pièce
        en coordonnées linéaires et angulaires de la machine-outil.
        """
        vz = max(-1.0, min(1.0, tool_vec.z))
        tilt = math.degrees(math.acos(vz))
        azimuth = math.degrees(math.atan2(tool_vec.y, tool_vec.x))

        rot1, rot2 = tilt, azimuth
        r_mat = self.compute_rotation_matrix(rot1, rot2)

        pw = np.array([workpiece_pos.x, workpiece_pos.y, workpiece_pos.z], dtype=np.float64)
        pm = r_mat @ pw + self.pivot_offset
        if self.kinematics_type == MachineKinematics5Axis.HEAD_HEAD_AB:
            tv = np.array([tool_vec.x, tool_vec.y, tool_vec.z], dtype=np.float64)
            norm_tv = float(np.linalg.norm(tv))
            tv_unit = tv / norm_tv if norm_tv > 1e-9 else np.array([0.0, 0.0, 1.0])
            pm += self.tool_length * tv_unit
        else:
            pm[2] += self.tool_length

        mach_pos = Vector3D(float(pm[0]), float(pm[1]), float(pm[2]))
        return mach_pos, rot1, rot2

    def machine_to_workpiece(
        self,
        machine_pos: Vector3D,
        rot1_deg: float,
        rot2_deg: float
    ) -> Tuple[Vector3D, Vector3D]:
        """
        Cinématique directe RTCP : calcule la position du point de contact outil
        dans le repère de la pièce usinée.
        """
        r_mat = self.compute_rotation_matrix(rot1_deg, rot2_deg)
        r_inv = r_mat.T

        pm = np.array([machine_pos.x, machine_pos.y, machine_pos.z], dtype=np.float64)
        pm[2] -= self.tool_length
        pm_relative = pm - self.pivot_offset

        pw = r_inv @ pm_relative
        spindle_dir = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        tw = r_inv @ spindle_dir

        work_pos = Vector3D(float(pw[0]), float(pw[1]), float(pw[2]))
        work_vec = Vector3D(float(tw[0]), float(tw[1]), float(tw[2])).normalized()
        return work_pos, work_vec


class GCodeArcInterpolator:
    """
    Interpolateur d'arcs circulaires et trajectoires hélicoïdales (G02 / G03).
    Gère les plans de travail ISO G17 (XY), G18 (ZX), G19 (YZ) et la discrétisation
    conforme à une tolérance de flèche (chordal deviation).
    """

    def __init__(self, chordal_tolerance_mm: float = 0.005) -> None:
        self.chordal_tolerance: float = max(1e-4, float(chordal_tolerance_mm))

    def interpolate_arc_2d(
        self,
        start_pt: Tuple[float, float],
        end_pt: Tuple[float, float],
        center_offset_ij: Tuple[float, float],
        is_clockwise: bool = True
    ) -> List[Tuple[float, float]]:
        """
        Discrétise un arc circulaire 2D en segments rectilignes sous tolérance de corde.
        """
        cx = start_pt[0] + center_offset_ij[0]
        cy = start_pt[1] + center_offset_ij[1]

        r = math.hypot(center_offset_ij[0], center_offset_ij[1])
        if r < 1e-6:
            return [start_pt, end_pt]

        start_angle = math.atan2(start_pt[1] - cy, start_pt[0] - cx)
        end_angle = math.atan2(end_pt[1] - cy, end_pt[0] - cx)

        # Calcul de la course angulaire totale selon le sens horaire/anti-horaire
        if is_clockwise:
            if end_angle >= start_angle:
                end_angle -= 2.0 * math.pi
            delta_angle = start_angle - end_angle
        else:
            if end_angle <= start_angle:
                end_angle += 2.0 * math.pi
            delta_angle = end_angle - start_angle

        # Pas angulaire maximal pour respecter la tolérance de corde: h = r * (1 - cos(dtheta/2)) <= tol
        max_dtheta = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - (self.chordal_tolerance / r))))
        max_dtheta = max(0.01, min(0.3, max_dtheta))

        num_segments = max(4, int(math.ceil(delta_angle / max_dtheta)))
        points: List[Tuple[float, float]] = []

        for i in range(num_segments + 1):
            fraction = float(i) / float(num_segments)
            angle = start_angle - fraction * delta_angle if is_clockwise else start_angle + fraction * delta_angle
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append((px, py))

        return points

    def generate_helical_gcode(
        self,
        start_pt: Vector3D,
        end_pt: Vector3D,
        center_ij: Tuple[float, float],
        pitch_mm: float,
        is_clockwise: bool = True,
        feed_rate_mm_min: float = 1200.0
    ) -> str:
        """Génère le bloc G-code hélicoïdal G02 ou G03 avec pas axial Z."""
        cmd = "G02" if is_clockwise else "G03"
        return (
            f"{cmd} X{end_pt.x:.4f} Y{end_pt.y:.4f} Z{end_pt.z:.4f} "
            f"I{center_ij[0]:.4f} J{center_ij[1]:.4f} P{pitch_mm:.3f} F{feed_rate_mm_min:.1f}"
        )
