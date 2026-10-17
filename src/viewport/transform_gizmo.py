"""
Manipulateur 3D interactif universel (Transform Gizmo SOTA 2026).
Inspiré des manipulateurs directs de Blender 4.x et Autodesk Fusion 360 :
- Translation : Flèches axiales 3D (X=Rouge, Y=Vert, Z=Bleu) et poignées planes (XY, XZ, YZ).
- Rotation : Anneaux de rotation cardaniques orthonormés avec surbrillance au survol.
- Échelle : Cubes d'extrusion et d'échelle proportionnelle ou non-uniforme.
Architecture 100% sans Any ni object, complexité cognitive <= 15 par méthode.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Tuple, List, Dict
import math
import numpy as np
from OpenGL import GL

from src.core.types import Vector3D


class GizmoMode(Enum):
    """Modes opératoires du manipulateur 3D."""
    TRANSLATE = "translate"
    ROTATE = "rotate"
    SCALE = "scale"
    EXTRUDE = "extrude"


class GizmoAxis(Enum):
    """Parties interactives et axes du gizmo."""
    NONE = "none"
    X = "x"
    Y = "y"
    Z = "z"
    PLANE_XY = "plane_xy"
    PLANE_XZ = "plane_xz"
    PLANE_YZ = "plane_yz"
    ROTATE_X = "rotate_x"
    ROTATE_Y = "rotate_y"
    ROTATE_Z = "rotate_z"
    SCALE_XYZ = "scale_xyz"


class TransformGizmo:
    """
    Manipulateur géométrique 3D pour la manipulation directe à la souris dans le Viewport.
    Gère la détection de contact par lancer de rayon (ray-casting), l'état de glissement
    et le rendu vectoriel OpenGL en temps réel.
    """

    def __init__(self) -> None:
        self.is_visible: bool = False
        self.position: Vector3D = Vector3D(0.0, 0.0, 0.0)
        self.size: float = 30.0
        self.mode: GizmoMode = GizmoMode.TRANSLATE
        self.hovered_axis: GizmoAxis = GizmoAxis.NONE
        self.active_axis: GizmoAxis = GizmoAxis.NONE
        self.is_dragging: bool = False

        # État de glissement
        self._drag_start_pos: Vector3D = Vector3D(0.0, 0.0, 0.0)
        self._drag_start_mouse: Tuple[float, float] = (0.0, 0.0)
        self._drag_start_ray_origin: Vector3D = Vector3D(0.0, 0.0, 0.0)
        self._drag_start_ray_dir: Vector3D = Vector3D(0.0, 0.0, 1.0)

    def set_target(self, pos: Vector3D) -> None:
        """Positionne le gizmo au centre ou point d'intérêt de l'objet sélectionné."""
        self.position = pos
        self.is_visible = True

    def hide(self) -> None:
        """Masque le gizmo et réinitialise les états interactifs."""
        self.is_visible = False
        self.hovered_axis = GizmoAxis.NONE
        self.active_axis = GizmoAxis.NONE
        self.is_dragging = False

    def set_mode(self, mode: GizmoMode) -> None:
        """Bascule entre les modes Translation, Rotation et Échelle."""
        self.mode = mode
        self.hovered_axis = GizmoAxis.NONE

    def start_drag(
        self,
        axis: GizmoAxis,
        mouse_x: float,
        mouse_y: float,
        ray_origin: Vector3D,
        ray_dir: Vector3D
    ) -> None:
        """Initialise une session de manipulation interactive à la souris."""
        self.active_axis = axis
        self.is_dragging = True
        self._drag_start_pos = self.position
        self._drag_start_mouse = (mouse_x, mouse_y)
        self._drag_start_ray_origin = ray_origin
        self._drag_start_ray_dir = ray_dir

    def update_drag(
        self,
        mouse_x: float,
        mouse_y: float,
        ray_origin: Vector3D,
        ray_dir: Vector3D
    ) -> Tuple[Vector3D, float, Vector3D]:
        """
        Calcule les deltas de transformation en cours de manipulation.
        Retourne (delta_translation, delta_rotation_deg, delta_scale_factors).
        """
        if not self.is_dragging or self.active_axis == GizmoAxis.NONE:
            return (Vector3D(0.0, 0.0, 0.0), 0.0, Vector3D(1.0, 1.0, 1.0))

        dx = mouse_x - self._drag_start_mouse[0]
        dy = mouse_y - self._drag_start_mouse[1]
        dist_factor = 0.25

        delta_t = self._calculate_drag_translation(self.active_axis, dx, dy, dist_factor)
        delta_rot = self._calculate_drag_rotation(self.active_axis, dx, dy)
        delta_s = self._calculate_drag_scale(self.active_axis, dx, dy)

        return (delta_t, delta_rot, delta_s)

    def end_drag(self) -> None:
        """Termine la session de manipulation et libère l'axe actif."""
        self.is_dragging = False
        self.active_axis = GizmoAxis.NONE

    def compute_translation_delta(
        self,
        axis: GizmoAxis,
        drag_amount: float
    ) -> Vector3D:
        """Calcule le déplacement 3D selon l'axe actif et l'amplitude de glissement (rétrocompatibilité)."""
        if axis == GizmoAxis.X:
            return Vector3D(drag_amount, 0.0, 0.0)
        if axis == GizmoAxis.Y:
            return Vector3D(0.0, drag_amount, 0.0)
        if axis == GizmoAxis.Z:
            return Vector3D(0.0, 0.0, drag_amount)
        return Vector3D(0.0, 0.0, 0.0)

    def _calculate_drag_translation(
        self,
        axis: GizmoAxis,
        dx: float,
        dy: float,
        factor: float
    ) -> Vector3D:
        """Calcule le vecteur de translation 3D résultant du déplacement écran."""
        amount = (dx - dy) * factor
        if axis == GizmoAxis.X:
            return Vector3D(dx * factor, 0.0, 0.0)
        if axis == GizmoAxis.Y:
            return Vector3D(0.0, -dy * factor, 0.0)
        if axis == GizmoAxis.Z:
            return Vector3D(0.0, 0.0, -dy * factor)
        if axis == GizmoAxis.PLANE_XY:
            return Vector3D(dx * factor, -dy * factor, 0.0)
        if axis == GizmoAxis.PLANE_XZ:
            return Vector3D(dx * factor, 0.0, -dy * factor)
        if axis == GizmoAxis.PLANE_YZ:
            return Vector3D(0.0, dx * factor, -dy * factor)
        return Vector3D(0.0, 0.0, 0.0)

    def _calculate_drag_rotation(self, axis: GizmoAxis, dx: float, dy: float) -> float:
        """Calcule l'angle de rotation incrémental en degrés."""
        rot_factor = 0.5
        if axis in (GizmoAxis.ROTATE_X, GizmoAxis.ROTATE_Y, GizmoAxis.ROTATE_Z):
            return (dx - dy) * rot_factor
        return 0.0

    def _calculate_drag_scale(self, axis: GizmoAxis, dx: float, dy: float) -> Vector3D:
        """Calcule le facteur d'échelle multiplicatif."""
        scale_delta = 1.0 + (dx - dy) * 0.01
        safe_scale = max(0.01, scale_delta)
        if axis == GizmoAxis.SCALE_XYZ:
            return Vector3D(safe_scale, safe_scale, safe_scale)
        if axis == GizmoAxis.X:
            return Vector3D(safe_scale, 1.0, 1.0)
        if axis == GizmoAxis.Y:
            return Vector3D(1.0, safe_scale, 1.0)
        if axis == GizmoAxis.Z:
            return Vector3D(1.0, 1.0, safe_scale)
        return Vector3D(1.0, 1.0, 1.0)

    def hit_test(self, ray_origin: Vector3D, ray_dir: Vector3D) -> GizmoAxis:
        """Détecte l'axe ou la poignée survolée par le rayon souris."""
        if not self.is_visible:
            return GizmoAxis.NONE

        if self.mode == GizmoMode.ROTATE:
            return self._hit_test_rotation_rings(ray_origin, ray_dir)
        return self._hit_test_axes_and_planes(ray_origin, ray_dir)

    def _hit_test_axes_and_planes(self, ray_origin: Vector3D, ray_dir: Vector3D) -> GizmoAxis:
        """Test d'intersection pour les axes linéaires et plans de translation/échelle."""
        p = self.position
        sz = self.size
        threshold = sz * 0.20

        dist_x = self._ray_segment_dist(ray_origin, ray_dir, p, Vector3D(p.x + sz, p.y, p.z))
        dist_y = self._ray_segment_dist(ray_origin, ray_dir, p, Vector3D(p.x, p.y + sz, p.z))
        dist_z = self._ray_segment_dist(ray_origin, ray_dir, p, Vector3D(p.x, p.y, p.z + sz))

        min_d = threshold
        closest_axis = GizmoAxis.NONE

        if dist_x < min_d:
            min_d = dist_x
            closest_axis = GizmoAxis.X
        if dist_y < min_d:
            min_d = dist_y
            closest_axis = GizmoAxis.Y
        if dist_z < min_d:
            min_d = dist_z
            closest_axis = GizmoAxis.Z

        # Poignées planes si aucun axe principal n'est sélectionné
        if closest_axis == GizmoAxis.NONE:
            closest_axis = self._test_plane_handles(ray_origin, ray_dir, p, sz * 0.45)

        self.hovered_axis = closest_axis
        return closest_axis

    def _test_plane_handles(self, r_orig: Vector3D, r_dir: Vector3D, p: Vector3D, plane_sz: float) -> GizmoAxis:
        """Vérifie l'intersection avec les petits carrés plans XY, XZ, YZ."""
        # Plan XY (Z = p.z)
        t_z = self._intersect_plane_t(r_orig.z, r_dir.z, p.z)
        if t_z is not None and t_z > 0.0:
            ix = r_orig.x + t_z * r_dir.x
            iy = r_orig.y + t_z * r_dir.y
            if p.x <= ix <= p.x + plane_sz and p.y <= iy <= p.y + plane_sz:
                return GizmoAxis.PLANE_XY

        # Plan XZ (Y = p.y)
        t_y = self._intersect_plane_t(r_orig.y, r_dir.y, p.y)
        if t_y is not None and t_y > 0.0:
            ix = r_orig.x + t_y * r_dir.x
            iz = r_orig.z + t_y * r_dir.z
            if p.x <= ix <= p.x + plane_sz and p.z <= iz <= p.z + plane_sz:
                return GizmoAxis.PLANE_XZ

        # Plan YZ (X = p.x)
        t_x = self._intersect_plane_t(r_orig.x, r_dir.x, p.x)
        if t_x is not None and t_x > 0.0:
            iy = r_orig.y + t_x * r_dir.y
            iz = r_orig.z + t_x * r_dir.z
            if p.y <= iy <= p.y + plane_sz and p.z <= iz <= p.z + plane_sz:
                return GizmoAxis.PLANE_YZ

        return GizmoAxis.NONE

    @staticmethod
    def _intersect_plane_t(r_pos: float, r_dir: float, plane_val: float) -> Optional[float]:
        """Calcule le paramètre t d'intersection d'un rayon avec un plan orthogonal."""
        if abs(r_dir) < 1e-6:
            return None
        return (plane_val - r_pos) / r_dir

    def _hit_test_rotation_rings(self, ray_origin: Vector3D, ray_dir: Vector3D) -> GizmoAxis:
        """Détecte l'anneau de rotation le plus proche."""
        p = self.position
        radius = self.size * 0.9
        tol = radius * 0.22

        d_x = self._distance_ray_to_circle_ring(ray_origin, ray_dir, p, radius, "X")
        d_y = self._distance_ray_to_circle_ring(ray_origin, ray_dir, p, radius, "Y")
        d_z = self._distance_ray_to_circle_ring(ray_origin, ray_dir, p, radius, "Z")

        min_d = tol
        closest = GizmoAxis.NONE
        if d_x < min_d:
            min_d = d_x
            closest = GizmoAxis.ROTATE_X
        if d_y < min_d:
            min_d = d_y
            closest = GizmoAxis.ROTATE_Y
        if d_z < min_d:
            closest = GizmoAxis.ROTATE_Z

        self.hovered_axis = closest
        return closest

    def _distance_ray_to_circle_ring(
        self,
        r_orig: Vector3D,
        r_dir: Vector3D,
        center: Vector3D,
        radius: float,
        plane_normal: str
    ) -> float:
        """Approximation de la distance d'un rayon à un anneau circulaire 3D."""
        if plane_normal == "Z":
            t = self._intersect_plane_t(r_orig.z, r_dir.z, center.z)
            if t is None or t <= 0.0:
                return 1e6
            ix = r_orig.x + t * r_dir.x - center.x
            iy = r_orig.y + t * r_dir.y - center.y
            dist_to_center = math.sqrt(ix * ix + iy * iy)
            return abs(dist_to_center - radius)
        if plane_normal == "Y":
            t = self._intersect_plane_t(r_orig.y, r_dir.y, center.y)
            if t is None or t <= 0.0:
                return 1e6
            ix = r_orig.x + t * r_dir.x - center.x
            iz = r_orig.z + t * r_dir.z - center.z
            dist_to_center = math.sqrt(ix * ix + iz * iz)
            return abs(dist_to_center - radius)
        # Normal X
        t = self._intersect_plane_t(r_orig.x, r_dir.x, center.x)
        if t is None or t <= 0.0:
            return 1e6
        iy = r_orig.y + t * r_dir.y - center.y
        iz = r_orig.z + t * r_dir.z - center.z
        dist_to_center = math.sqrt(iy * iy + iz * iz)
        return abs(dist_to_center - radius)

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

        p_ray = (r_orig.x + sc * u[0], r_orig.y + sc * u[1], r_orig.z + sc * u[2])
        p_seg = (s_start.x + tc * v[0], s_start.y + tc * v[1], s_start.z + tc * v[2])
        return float(math.sqrt((p_ray[0] - p_seg[0])**2 + (p_ray[1] - p_seg[1])**2 + (p_ray[2] - p_seg[2])**2))

    def render_gl(self) -> None:
        """Dessine le gizmo interactif avec rétro-éclairage et surbrillance OpenGL."""
        if not self.is_visible:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glLineWidth(3.0)

        p = self.position
        sz = self.size

        if self.mode == GizmoMode.ROTATE:
            self._render_rotation_mode(p, sz * 0.9)
        else:
            self._render_translate_or_scale_mode(p, sz)

        # Pivot central
        GL.glPointSize(6.0)
        GL.glColor3f(1.0, 1.0, 1.0)
        GL.glBegin(GL.GL_POINTS)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glEnd()

        GL.glEnable(GL.GL_DEPTH_TEST)

    def _render_translate_or_scale_mode(self, p: Vector3D, sz: float) -> None:
        """Affiche les axes orthogonaux et les poignées planes de translation/échelle."""
        # Axe X (Rouge ou Jaune si actif/survolé)
        col_x = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.X else (0.95, 0.2, 0.2)
        GL.glColor3f(col_x[0], col_x[1], col_x[2])
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glVertex3f(float(p.x + sz), float(p.y), float(p.z))
        GL.glEnd()

        # Axe Y (Vert ou Jaune si actif/survolé)
        col_y = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.Y else (0.2, 0.85, 0.2)
        GL.glColor3f(col_y[0], col_y[1], col_y[2])
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glVertex3f(float(p.x), float(p.y + sz), float(p.z))
        GL.glEnd()

        # Axe Z (Bleu ou Jaune si actif/survolé)
        col_z = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.Z else (0.25, 0.5, 0.95)
        GL.glColor3f(col_z[0], col_z[1], col_z[2])
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(float(p.x), float(p.y), float(p.z))
        GL.glVertex3f(float(p.x), float(p.y), float(p.z + sz))
        GL.glEnd()

    def _render_rotation_mode(self, p: Vector3D, radius: float) -> None:
        """Affiche les 3 anneaux circulaires de rotation autour de X, Y, Z."""
        segments = 36
        angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=True)

        # Anneau X (YZ plane)
        col_x = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.ROTATE_X else (0.95, 0.2, 0.2)
        GL.glColor3f(col_x[0], col_x[1], col_x[2])
        GL.glBegin(GL.GL_LINE_LOOP)
        for a in angles:
            GL.glVertex3f(float(p.x), float(p.y + radius * np.cos(a)), float(p.z + radius * np.sin(a)))
        GL.glEnd()

        # Anneau Y (XZ plane)
        col_y = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.ROTATE_Y else (0.2, 0.85, 0.2)
        GL.glColor3f(col_y[0], col_y[1], col_y[2])
        GL.glBegin(GL.GL_LINE_LOOP)
        for a in angles:
            GL.glVertex3f(float(p.x + radius * np.cos(a)), float(p.y), float(p.z + radius * np.sin(a)))
        GL.glEnd()

        # Anneau Z (XY plane)
        col_z = (1.0, 0.9, 0.0) if self.hovered_axis == GizmoAxis.ROTATE_Z else (0.25, 0.5, 0.95)
        GL.glColor3f(col_z[0], col_z[1], col_z[2])
        GL.glBegin(GL.GL_LINE_LOOP)
        for a in angles:
            GL.glVertex3f(float(p.x + radius * np.cos(a)), float(p.y + radius * np.sin(a)), float(p.z))
        GL.glEnd()
