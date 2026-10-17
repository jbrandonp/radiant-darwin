"""
Moteur d'accrochage magnétique intelligent inspiré de Blender (Snapping Engine).
Fournit un magnétisme en temps réel sur la grille, les sommets, les milieux d'arêtes,
les centres de faces et l'origine, avec retour visuel immédiat (glyphes et repères).
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import math
import numpy as np
from OpenGL import GL

from src.core.types import Vector3D, MeshBuffer
from src.viewport.camera import CADCamera


class SnapTarget(Enum):
    """Cibles d'accrochage magnétique."""
    GRID = "grid"
    VERTEX = "vertex"
    EDGE_MIDPOINT = "edge_midpoint"
    FACE_CENTER = "face_center"
    ORIGIN = "origin"


@dataclass
class SnapResult:
    """Informations sur l'entité magnétique capturée."""
    has_snap: bool
    snapped_point: Vector3D
    target_type: SnapTarget
    distance_px: float
    description: str
    glyph: str


class MagneticSnapEngine:
    """Moteur d'accrochage géométrique 3D en temps réel."""

    def __init__(self) -> None:
        self.is_enabled: bool = True
        self.tolerance_px: float = 18.0
        self.grid_step: float = 10.0
        self.active_targets: List[SnapTarget] = [
            SnapTarget.GRID,
            SnapTarget.VERTEX,
            SnapTarget.EDGE_MIDPOINT,
            SnapTarget.FACE_CENTER,
            SnapTarget.ORIGIN
        ]

    def find_best_snap(
        self,
        cursor_x: int,
        cursor_y: int,
        viewport_w: int,
        viewport_h: int,
        camera: CADCamera,
        buffers: List[MeshBuffer]
    ) -> SnapResult:
        """Détecte la meilleure cible magnétique sous le curseur de la souris."""
        if not self.is_enabled:
            return self._empty_result()

        best_res: Optional[SnapResult] = None
        min_dist = self.tolerance_px

        # 1. Vérifier l'Origine (0, 0, 0)
        if SnapTarget.ORIGIN in self.active_targets:
            orig = Vector3D(0.0, 0.0, 0.0)
            orig_px = self._project_to_screen(orig, camera, viewport_w, viewport_h)
            if orig_px is not None:
                d = math.hypot(cursor_x - orig_px[0], cursor_y - orig_px[1])
                if d < min_dist:
                    min_dist = d
                    best_res = SnapResult(True, orig, SnapTarget.ORIGIN, d, "Origine (0,0,0)", "⭕")

        # 2. Vérifier les sommets et milieux d'arêtes des maillages
        mesh_snap = self._check_mesh_features(cursor_x, cursor_y, viewport_w, viewport_h, camera, buffers, min_dist)
        if mesh_snap is not None and mesh_snap.distance_px < min_dist:
            min_dist = mesh_snap.distance_px
            best_res = mesh_snap

        # 3. Vérifier la grille au sol XY si aucun élément proche
        if best_res is None and SnapTarget.GRID in self.active_targets:
            grid_pt = self._snap_to_ground_grid(cursor_x, cursor_y, viewport_w, viewport_h, camera)
            if grid_pt is not None:
                return SnapResult(True, grid_pt, SnapTarget.GRID, 0.0, "Grille XY", "➕")

        if best_res is not None:
            return best_res

        return self._empty_result()

    def _check_mesh_features(
        self,
        cx: int,
        cy: int,
        w: int,
        h: int,
        cam: CADCamera,
        buffers: List[MeshBuffer],
        max_dist: float
    ) -> Optional[SnapResult]:
        """Examine les sommets et milieux d'arêtes des corps présents."""
        best: Optional[SnapResult] = None
        min_d = max_dist

        for buf in buffers:
            if buf.is_empty():
                continue

            v_res, min_d = self._check_vertex_snaps(buf, cx, cy, w, h, cam, min_d)
            if v_res is not None:
                best = v_res

            e_res, min_d = self._check_edge_snaps(buf, cx, cy, w, h, cam, min_d)
            if e_res is not None:
                best = e_res

        return best

    def _check_vertex_snaps(
        self,
        buf: MeshBuffer,
        cx: int,
        cy: int,
        w: int,
        h: int,
        cam: CADCamera,
        min_d: float
    ) -> Tuple[Optional[SnapResult], float]:
        """Recherche le sommet le plus proche sous le curseur parmi 100% des sommets (vectorisé)."""
        if SnapTarget.VERTEX not in self.active_targets or len(buf.vertices) == 0:
            return None, min_d

        screen_pts, valid = self._project_points_to_screen(buf.vertices, cam, w, h)
        if not np.any(valid):
            return None, min_d

        dx = screen_pts[:, 0] - cx
        dy = screen_pts[:, 1] - cy
        dists = np.where(valid, np.hypot(dx, dy), float("inf"))

        best_idx = int(np.argmin(dists))
        best_d = float(dists[best_idx])

        if best_d < min_d:
            v = buf.vertices[best_idx]
            pt = Vector3D(float(v[0]), float(v[1]), float(v[2]))
            return SnapResult(True, pt, SnapTarget.VERTEX, best_d, "Sommet", "⏹"), best_d

        return None, min_d

    def _check_edge_snaps(
        self,
        buf: MeshBuffer,
        cx: int,
        cy: int,
        w: int,
        h: int,
        cam: CADCamera,
        min_d: float
    ) -> Tuple[Optional[SnapResult], float]:
        """Recherche le milieu d'arête le plus proche parmi 100% des arêtes (débridé et vectorisé)."""
        if SnapTarget.EDGE_MIDPOINT not in self.active_targets:
            return None, min_d
        if buf.edge_vertices is None or len(buf.edge_vertices) < 2:
            return None, min_d

        ev = buf.edge_vertices
        n_edges = len(ev) // 2
        p1 = ev[0:2 * n_edges:2]
        p2 = ev[1:2 * n_edges:2]
        midpoints = 0.5 * (p1 + p2)

        screen_pts, valid = self._project_points_to_screen(midpoints, cam, w, h)
        if not np.any(valid):
            return None, min_d

        dx = screen_pts[:, 0] - cx
        dy = screen_pts[:, 1] - cy
        dists = np.where(valid, np.hypot(dx, dy), float("inf"))

        best_idx = int(np.argmin(dists))
        best_d = float(dists[best_idx])

        if best_d < min_d:
            m = midpoints[best_idx]
            mid = Vector3D(float(m[0]), float(m[1]), float(m[2]))
            return SnapResult(True, mid, SnapTarget.EDGE_MIDPOINT, best_d, "Milieu d'arête", "▲"), best_d

        return None, min_d


    def _snap_to_ground_grid(self, cx: int, cy: int, w: int, h: int, cam: CADCamera) -> Optional[Vector3D]:
        """Projette le rayon de souris sur le plan Z=0 et arrondit au pas de grille."""
        ray_dir = cam.screen_to_ray(cx, cy, w, h)
        eye = cam.get_eye_position()

        if abs(ray_dir.z) < 1e-4:
            return None

        # Intersection t telle que eye.z + t * ray_dir.z = 0
        t = -eye.z / ray_dir.z
        if t <= 0.0:
            return None

        hit_x = eye.x + t * ray_dir.x
        hit_y = eye.y + t * ray_dir.y

        # Arrondi au pas de grille le plus proche
        step = self.grid_step
        gx = round(hit_x / step) * step
        gy = round(hit_y / step) * step

        return Vector3D(float(gx), float(gy), 0.0)

    def _project_points_to_screen(
        self,
        pts: np.ndarray,
        cam: CADCamera,
        w: int,
        h: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Projette vectoriellement un tableau de points (N, 3) en coordonnées pixels écran (N, 2)."""
        eye = cam.get_eye_position()
        target = cam.target
        fwd = np.array([target.x - eye.x, target.y - eye.y, target.z - eye.z], dtype=np.float64)
        dist = float(np.linalg.norm(fwd))
        if dist < 1e-6:
            return np.zeros((len(pts), 2), dtype=np.float64), np.zeros(len(pts), dtype=bool)
        fwd /= dist

        up_approx = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        side = np.cross(fwd, up_approx)
        side_norm = float(np.linalg.norm(side))
        side = side / side_norm if side_norm > 1e-6 else np.array([1.0, 0.0, 0.0], dtype=np.float64)
        up = np.cross(side, fwd)

        eye_arr = np.array([eye.x, eye.y, eye.z], dtype=np.float64)
        p_rel = pts - eye_arr
        z_depth = np.dot(p_rel, fwd)

        valid = z_depth > 0.1
        safe_z = np.where(valid, z_depth, 1.0)

        x_cam = np.dot(p_rel, side)
        y_cam = np.dot(p_rel, up)

        aspect = float(w) / float(max(1, h))
        tan_half = math.tan(math.radians(cam.fov_deg) / 2.0)

        ndc_x = x_cam / (safe_z * tan_half * aspect)
        ndc_y = y_cam / (safe_z * tan_half)

        screen_x = (ndc_x + 1.0) * 0.5 * w
        screen_y = (1.0 - ndc_y) * 0.5 * h

        return np.column_stack([screen_x, screen_y]), valid

    def _project_to_screen(self, pt: Vector3D, cam: CADCamera, w: int, h: int) -> Optional[Tuple[float, float]]:

        """Calcule les coordonnées 2D pixels d'un point 3D dans le viewport."""
        eye = cam.get_eye_position()
        target = cam.target

        # Vecteurs repère caméra
        fwd = np.array([target.x - eye.x, target.y - eye.y, target.z - eye.z], dtype=np.float64)
        dist = np.linalg.norm(fwd)
        if dist < 1e-6:
            return None
        fwd /= dist

        up_approx = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        side = np.cross(fwd, up_approx)
        side_norm = np.linalg.norm(side)
        if side_norm < 1e-6:
            side = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            side /= side_norm
        up = np.cross(side, fwd)

        p_rel = np.array([pt.x - eye.x, pt.y - eye.y, pt.z - eye.z], dtype=np.float64)
        z_depth = np.dot(p_rel, fwd)
        if z_depth <= 0.1:
            return None

        x_cam = np.dot(p_rel, side)
        y_cam = np.dot(p_rel, up)

        aspect = float(w) / float(max(1, h))
        fov_rad = math.radians(cam.fov_deg)
        tan_half = math.tan(fov_rad / 2.0)

        ndc_x = x_cam / (z_depth * tan_half * aspect)
        ndc_y = y_cam / (z_depth * tan_half)

        screen_x = float((ndc_x + 1.0) * 0.5 * w)
        screen_y = float((1.0 - ndc_y) * 0.5 * h)

        return (screen_x, screen_y)

    def draw_snap_feedback(self, snap: SnapResult) -> None:
        """Dessine le glyphe géométrique néon à l'emplacement magnétique capturé."""
        if not snap.has_snap:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)

        pt = snap.snapped_point
        # Couleur cyan éclatant pour le magnétisme
        GL.glColor4f(0.0, 0.95, 1.0, 1.0)
        GL.glPointSize(10.0)
        GL.glLineWidth(2.5)

        GL.glBegin(GL.GL_POINTS)
        GL.glVertex3f(float(pt.x), float(pt.y), float(pt.z))
        GL.glEnd()

        # Petit losange / carré autour du point
        s = 3.0
        GL.glBegin(GL.GL_LINE_LOOP)
        GL.glVertex3f(float(pt.x - s), float(pt.y - s), float(pt.z))
        GL.glVertex3f(float(pt.x + s), float(pt.y - s), float(pt.z))
        GL.glVertex3f(float(pt.x + s), float(pt.y + s), float(pt.z))
        GL.glVertex3f(float(pt.x - s), float(pt.y + s), float(pt.z))
        GL.glEnd()

        GL.glEnable(GL.GL_DEPTH_TEST)

    def _empty_result(self) -> SnapResult:
        """Retourne un SnapResult inactif."""
        return SnapResult(False, Vector3D(0.0, 0.0, 0.0), SnapTarget.GRID, 999.0, "Aucun accrochage", "")
