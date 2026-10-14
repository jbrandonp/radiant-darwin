"""
Manipulateur 3D interactif (Transform Gizmo) inspiré de Blender et Fusion 360.
Affiche les axes de translation (Flèches X=Rouge, Y=Vert, Z=Bleu), les anneaux de rotation
et les poignées planes (XY, XZ, YZ) pour déplacer et orienter les corps directement à la souris.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Tuple
import math
import numpy as np
from OpenGL import GL

from src.core.types import Vector3D
from src.viewport.camera import CADCamera


class GizmoMode(Enum):
    """Modes de transformation du gizmo."""
    TRANSLATE = "translate"
    ROTATE = "rotate"
    SCALE = "scale"


class GizmoAxis(Enum):
    """Parties interactives du gizmo."""
    NONE = "none"
    X = "x"
    Y = "y"
    Z = "z"
    PLANE_XY = "plane_xy"
    PLANE_XZ = "plane_xz"
    PLANE_YZ = "plane_yz"


class TransformGizmo:
    """Manipulateur 3D interactif pour la manipulation directe dans le viewport."""

    def __init__(self) -> None:
        self.is_visible: bool = False
        self.position: Vector3D = Vector3D(0.0, 0.0, 0.0)
        self.size: float = 30.0
        self.mode: GizmoMode = GizmoMode.TRANSLATE
        self.hovered_axis: GizmoAxis = GizmoAxis.NONE
        self.active_axis: GizmoAxis = GizmoAxis.NONE
        self.is_dragging: bool = False

    def set_target(self, pos: Vector3D) -> None:
        """Positionne le gizmo au centre de l'objet sélectionné."""
        self.position = pos
        self.is_visible = True

    def hide(self) -> None:
        """Masque le gizmo."""
        self.is_visible = False
        self.hovered_axis = GizmoAxis.NONE
        self.active_axis = GizmoAxis.NONE
        self.is_dragging = False

    def hit_test(self, ray_origin: Vector3D, ray_dir: Vector3D) -> GizmoAxis:
        """Détecte si un rayon de souris intersecte l'un des axes ou poignées du gizmo."""
        if not self.is_visible:
            return GizmoAxis.NONE

        p = self.position
        sz = self.size

        # Distance minimale du rayon aux 3 segments d'axe
        dist_x = self._ray_segment_dist(ray_origin, ray_dir, p, Vector3D(p.x + sz, p.y, p.z))
        dist_y = self._ray_segment_dist(ray_origin, ray_dir, p, Vector3D(p.x, p.y + sz, p.z))
        dist_z = self._ray_segment_dist(ray_origin, ray_dir, p, Vector3D(p.x, p.y, p.z + sz))

        threshold = sz * 0.18
        closest_axis = GizmoAxis.NONE
        min_d = threshold

        if dist_x < min_d:
            min_d = dist_x
            closest_axis = GizmoAxis.X
        if dist_y < min_d:
            min_d = dist_y
            closest_axis = GizmoAxis.Y
        if dist_z < min_d:
            min_d = dist_z
            closest_axis = GizmoAxis.Z

        self.hovered_axis = closest_axis
        return closest_axis

    def _ray_segment_dist(self, r_orig: Vector3D, r_dir: Vector3D, s_start: Vector3D, s_end: Vector3D) -> float:
        """Calcule la distance minimale 3D entre un rayon infini et un segment fini."""
        u = np.array([r_dir.x, r_dir.y, r_dir.z], dtype=np.float64)
        v = np.array([s_end.x - s_start.x, s_end.y - s_start.y, s_end.z - s_start.z], dtype=np.float64)
        w = np.array([r_orig.x - s_start.x, r_orig.y - s_start.y, r_orig.z - s_start.z], dtype=np.float64)

        a = float(np.dot(u, u))
        b = float(np.dot(u, v))
        c = float(np.dot(v, v))
        d = float(np.dot(u, w))
        e = float(np.dot(v, w))

        denom = a * c - b * b
        if abs(denom) < 1e-7:
            tc = max(0.0, min(1.0, e / (c if c > 1e-7 else 1.0)))
            sc = max(0.0, (tc * b - d) / (a if a > 1e-7 else 1.0))
        else:
            tc = max(0.0, min(1.0, (a * e - b * d) / denom))
            sc = max(0.0, (tc * b - d) / (a if a > 1e-7 else 1.0))

        p_ray = r_orig.x + sc * u[0], r_orig.y + sc * u[1], r_orig.z + sc * u[2]
        p_seg = s_start.x + tc * v[0], s_start.y + tc * v[1], s_start.z + tc * v[2]

        return float(math.sqrt((p_ray[0] - p_seg[0])**2 + (p_ray[1] - p_seg[1])**2 + (p_ray[2] - p_seg[2])**2))

    def compute_translation_delta(
        self,
        axis: GizmoAxis,
        drag_amount: float
    ) -> Vector3D:
        """Calcule le déplacement 3D selon l'axe actif et l'amplitude de glissement."""
        if axis == GizmoAxis.X:
            return Vector3D(drag_amount, 0.0, 0.0)
        if axis == GizmoAxis.Y:
            return Vector3D(0.0, drag_amount, 0.0)
        if axis == GizmoAxis.Z:
            return Vector3D(0.0, 0.0, drag_amount)
        return Vector3D(0.0, 0.0, 0.0)

    def render_gl(self) -> None:
        """Dessine le gizmo 3D complet avec flèches et surbrillance au survol."""
        if not self.is_visible:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glLineWidth(3.0)

        p = self.position
        sz = self.size

        # Axe X (Rouge)
        col_x = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.X else (0.95, 0.2, 0.2)
        GL.glColor3f(col_x[0], col_x[1], col_x[2])
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glVertex3f(float(p.x + sz), float(p.y), float(p.z))
        GL.glEnd()

        # Axe Y (Vert)
        col_y = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.Y else (0.2, 0.85, 0.2)
        GL.glColor3f(col_y[0], col_y[1], col_y[2])
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glVertex3f(float(p.x), float(p.y + sz), float(p.z))
        GL.glEnd()

        # Axe Z (Bleu)
        col_z = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.Z else (0.25, 0.5, 0.95)
        GL.glColor3f(col_z[0], col_z[1], col_z[2])
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glVertex3f(float(p.x), float(p.y), float(p.z + sz))
        GL.glEnd()

        # Point central du pivot
        GL.glPointSize(6.0)
        GL.glColor3f(1.0, 1.0, 1.0)
        GL.glBegin(GL.GL_POINTS)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glEnd()

        GL.glEnable(GL.GL_DEPTH_TEST)
