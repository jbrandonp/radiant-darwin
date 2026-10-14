"""
Moteur de modélisation directe 'Press-Pull' inspiré d'Autodesk Fusion 360.
Permet d'extruder, décaler (offset) ou évider directement n'importe quelle face
sélectionnée en 3D sans redessiner d'esquisse 2D préalable.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import math
import numpy as np

from src.core.types import Vector3D, Point2D, PlaneType
from src.core.geometry import Solid, make_box, make_cylinder, extrude_polygon


@dataclass
class PushPullResult:
    """Résultat d'une opération de modélisation directe Press-Pull."""
    success: bool
    modified_solid: Solid
    offset_distance: float
    volume_delta: float
    operation_type: str
    message: str


class PushPullEngine:
    """
    Moteur de modélisation directe Push-Pull (Fusion 360 PressPull).
    Analyse la normale et le point cliqué pour extruder vers l'extérieur (+ offset)
    ou creuser une poche vers l'intérieur (- offset).
    """

    @staticmethod
    def execute_press_pull(
        solid: Solid,
        hit_point: Vector3D,
        face_normal: Vector3D,
        offset_distance: float,
        footprint_radius: float = 25.0
    ) -> PushPullResult:
        """
        Exécute une extrusion ou un perçage direct le long de la normale de face.
        offset_distance > 0 : extrusion / ajout de matière (Union).
        offset_distance < 0 : creusement / retrait de matière (Cut).
        """
        if solid.is_empty():
            return PushPullResult(
                success=False,
                modified_solid=solid,
                offset_distance=offset_distance,
                volume_delta=0.0,
                operation_type="NONE",
                message="Impossible d'appliquer Press-Pull sur un solide vide."
            )

        if abs(offset_distance) < 1e-4:
            return PushPullResult(
                success=True,
                modified_solid=solid,
                offset_distance=0.0,
                volume_delta=0.0,
                operation_type="NO_OP",
                message="Déplacement nul."
            )

        initial_vol = solid.volume()

        # Normaliser la direction d'extrusion
        norm = math.sqrt(face_normal.x**2 + face_normal.y**2 + face_normal.z**2)
        if norm < 1e-6:
            nx, ny, nz = 0.0, 0.0, 1.0
        else:
            nx = face_normal.x / norm
            ny = face_normal.y / norm
            nz = face_normal.z / norm

        depth = abs(offset_distance)
        rad = max(2.0, footprint_radius)

        # Générer l'outil cylindrique d'extrusion ou de perçage centré sur le hit_point
        tool = make_cylinder(radius=rad, height=depth, segments=36, center=False, name="PressPull_Tool")

        # Aligner l'axe Z du cylindre outil sur la normale de la face
        aligned_tool = PushPullEngine._align_tool_to_normal(tool, nx, ny, nz)

        if offset_distance > 0.0:
            # Pousser vers l'extérieur : positionner l'outil à la surface
            pos_x = hit_point.x
            pos_y = hit_point.y
            pos_z = hit_point.z
            placed_tool = aligned_tool.translate(pos_x, pos_y, pos_z)
            new_solid = solid.union(placed_tool)
            op_name = "BOSS_EXTRUSION"
        else:
            # Creuser vers l'intérieur : enfoncer l'outil dans la matière
            pos_x = hit_point.x - nx * depth
            pos_y = hit_point.y - ny * depth
            pos_z = hit_point.z - nz * depth
            placed_tool = aligned_tool.translate(pos_x, pos_y, pos_z)
            new_solid = solid.difference(placed_tool)
            op_name = "POCKET_CUT"

        final_vol = new_solid.volume()
        delta = final_vol - initial_vol

        return PushPullResult(
            success=True,
            modified_solid=new_solid,
            offset_distance=offset_distance,
            volume_delta=delta,
            operation_type=op_name,
            message=f"Press-Pull appliqué avec succès ({op_name}, distance: {offset_distance:+.2f} mm)."
        )

    @staticmethod
    def _align_tool_to_normal(tool: Solid, nx: float, ny: float, nz: float) -> Solid:
        """Oriente un cylindre (initialement selon l'axe +Z) vers le vecteur unitaire (nx, ny, nz)."""
        # Si la normale est déjà proche de +Z
        if abs(nx) < 1e-4 and abs(ny) < 1e-4 and nz > 0.9:
            return tool

        # Si la normale est opposée (-Z)
        if abs(nx) < 1e-4 and abs(ny) < 1e-4 and nz < -0.9:
            return tool.rotate(180.0, 0.0, 0.0)

        # Calcul des angles d'Euler pitch et yaw
        pitch_deg = math.degrees(math.acos(max(-1.0, min(1.0, nz))))
        yaw_deg = math.degrees(math.atan2(ny, nx))

        # Rotation autour de Y pour incliner de Z vers le plan, puis rotation autour de Z pour le lacet
        rotated = tool.rotate(0.0, pitch_deg, yaw_deg)
        return rotated
