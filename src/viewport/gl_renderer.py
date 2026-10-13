"""
Moteur de rendu OpenGL pour l'affichage de modèles CAO 3D style Autodesk Fusion 360.
Prend en charge le maillage ombré, les arêtes noires vives, la grille de référence,
et le trièdre des axes orthonormés (X=rouge, Y=vert, Z=bleu).
"""

from __future__ import annotations
from typing import List, Tuple
import numpy as np
from OpenGL import GL
from OpenGL.GLU import gluPerspective, gluLookAt

from src.core.types import MeshBuffer, Vector3D, ColorRGBA
from src.viewport.camera import CADCamera


class GLRenderer:
    """Rendu graphique OpenGL haute fidélité pour scène de CAO."""

    def __init__(self) -> None:
        """Initialise les options par défaut de rendu."""
        self.grid_size: float = 200.0
        self.grid_spacing: float = 10.0
        self.show_grid: bool = True
        self.show_edges: bool = True
        self.bg_color_top: Tuple[float, float, float] = (0.22, 0.24, 0.28)    # Ardoise studio claire
        self.bg_color_bottom: Tuple[float, float, float] = (0.12, 0.13, 0.16) # Graphite sombre profond
        self._grid_minor_pts: Optional[np.ndarray] = None
        self._grid_major_pts: Optional[np.ndarray] = None
        self._rebuild_grid_geometry()

    def _rebuild_grid_geometry(self) -> None:
        """Précalcule les coordonnées 3D de la grille sous forme de tampons NumPy optimisés."""
        half = self.grid_size / 2.0
        step_minor = self.grid_spacing          # 10 mm
        step_major = self.grid_spacing * 5.0    # 50 mm

        minor_lines: List[float] = []
        major_lines: List[float] = []

        # Lignes le long de X (parallèles à Y)
        x = -half
        while x <= half:
            is_center = abs(x) < 1e-4
            is_major = abs(x % step_major) < 1e-4 or is_center
            target_list = major_lines if is_major else minor_lines
            if not is_center:
                target_list.extend([float(x), -half, 0.0, float(x), half, 0.0])
            x += step_minor

        # Lignes le long de Y (parallèles à X)
        y = -half
        while y <= half:
            is_center = abs(y) < 1e-4
            is_major = abs(y % step_major) < 1e-4 or is_center
            target_list = major_lines if is_major else minor_lines
            if not is_center:
                target_list.extend([-half, float(y), 0.0, half, float(y), 0.0])
            y += step_minor

        self._grid_minor_pts = np.array(minor_lines, dtype=np.float32).reshape(-1, 3) if minor_lines else np.zeros((0, 3), dtype=np.float32)
        self._grid_major_pts = np.array(major_lines, dtype=np.float32).reshape(-1, 3) if major_lines else np.zeros((0, 3), dtype=np.float32)

    def initialize_gl(self) -> None:
        """Configure les états OpenGL initiaux (profondeur, antialiasing, éclairage)."""
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # Anti-aliasing pour des arêtes bien nettes
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glHint(GL.GL_LINE_SMOOTH_HINT, GL.GL_NICEST)

        # Éclairage métallique Fusion 360
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_LIGHT1)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)

        # Lumière clé principale (orientée depuis le haut droit)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [150.0, 150.0, 250.0, 0.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [0.90, 0.90, 0.92, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, [0.45, 0.45, 0.50, 1.0])

        # Lumière de débouchage (douce par le dessous)
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, [-120.0, -120.0, -80.0, 0.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, [0.40, 0.40, 0.45, 1.0])

        GL.glClearColor(self.bg_color_bottom[0], self.bg_color_bottom[1], self.bg_color_bottom[2], 1.0)

    def resize_gl(self, width: int, height: int, camera: CADCamera) -> None:
        """Met à jour la matrice de projection lors d'un redimensionnement."""
        if height == 0:
            height = 1
        GL.glViewport(0, 0, width, height)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        aspect = float(width) / float(height)
        gluPerspective(camera.fov_deg, aspect, camera.near_plane, camera.far_plane)
        GL.glMatrixMode(GL.GL_MODELVIEW)

    def _draw_gradient_background(self, width: int, height: int) -> None:
        """Dessine un dégradé de fond vertical studio CAO élégant (style Fusion 360)."""
        if width <= 0 or height <= 0:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_FALSE)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glOrtho(0.0, float(width), float(height), 0.0, -1.0, 1.0)

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()

        GL.glBegin(GL.GL_QUADS)
        # Haut
        GL.glColor3f(self.bg_color_top[0], self.bg_color_top[1], self.bg_color_top[2])
        GL.glVertex2f(0.0, 0.0)
        GL.glVertex2f(float(width), 0.0)
        # Bas
        GL.glColor3f(self.bg_color_bottom[0], self.bg_color_bottom[1], self.bg_color_bottom[2])
        GL.glVertex2f(float(width), float(height))
        GL.glVertex2f(0.0, float(height))
        GL.glEnd()

        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)

        GL.glDepthMask(GL.GL_TRUE)
        GL.glEnable(GL.GL_DEPTH_TEST)

    def render_scene(self, camera: CADCamera, mesh_buffers: List[MeshBuffer], width: int, height: int) -> None:
        """Effectue le rendu complet de la scène 3D."""
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        # 0. Fond d'écran dégradé studio
        self._draw_gradient_background(width, height)

        GL.glLoadIdentity()

        # Positionner la vue caméra
        eye = camera.get_eye_position()
        target = camera.target
        gluLookAt(
            eye.x, eye.y, eye.z,
            target.x, target.y, target.z,
            0.0, 0.0, 1.0
        )

        # 1. Rendu de la grille et des axes
        if self.show_grid:
            self._draw_grid_and_axes()

        # 2. Rendu des corps solides (Faces ombrées avec brillance métallique)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(1.0, 1.0)  # Évite le z-fighting avec les arêtes

        for buffer in mesh_buffers:
            self._draw_shaded_mesh(buffer)

        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

        # 3. Rendu des arêtes nettes (Lignes CAD contrastées)
        if self.show_edges:
            GL.glDisable(GL.GL_LIGHTING)
            for buffer in mesh_buffers:
                self._draw_mesh_edges(buffer)
            GL.glEnable(GL.GL_LIGHTING)

        # 4. Rendu du repère d'orientation (Trièdre X, Y, Z) en bas à gauche
        self._draw_orientation_triad(camera, width, height)

    def _draw_shaded_mesh(self, buffer: MeshBuffer) -> None:
        """Dessine les faces du maillage avec éclairage, normales et reflet spéculaire."""
        if buffer.is_empty():
            return

        has_v_colors = bool(buffer.vertex_colors is not None and len(buffer.vertex_colors) == len(buffer.vertices))
        if has_v_colors:
            GL.glEnableClientState(GL.GL_COLOR_ARRAY)
            GL.glColorPointer(4, GL.GL_FLOAT, 0, buffer.vertex_colors)
            GL.glEnable(GL.GL_COLOR_MATERIAL)
            GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        else:
            c = buffer.color
            GL.glColor4f(c.r, c.g, c.b, c.a)

        # Brillance métallique satinée type usinage CAO
        GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, [0.35, 0.35, 0.40, 1.0])
        GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 32.0)

        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)

        GL.glVertexPointer(3, GL.GL_FLOAT, 0, buffer.vertices)
        GL.glNormalPointer(GL.GL_FLOAT, 0, buffer.normals)

        GL.glDrawElements(
            GL.GL_TRIANGLES,
            len(buffer.faces) * 3,
            GL.GL_UNSIGNED_INT,
            buffer.faces.flatten()
        )

        GL.glDisableClientState(GL.GL_NORMAL_ARRAY)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        if has_v_colors:
            GL.glDisableClientState(GL.GL_COLOR_ARRAY)
            GL.glDisable(GL.GL_COLOR_MATERIAL)

    def _draw_mesh_edges(self, buffer: MeshBuffer) -> None:
        """Dessine les lignes de contour vives du solide."""
        if buffer.is_empty():
            return

        GL.glColor4f(0.12, 0.12, 0.15, 0.90)  # Noir / Gris très sombre contrasté
        GL.glLineWidth(1.5)

        # Tracé via edge_vertices directs (paires de points 3D pour chaque arête)
        if buffer.edge_vertices is not None and len(buffer.edge_vertices) > 0:
            GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, buffer.edge_vertices)
            GL.glDrawArrays(GL.GL_LINES, 0, len(buffer.edge_vertices))
            GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
            return

        if len(buffer.edges) == 0:
            return

        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glVertexPointer(3, GL.GL_FLOAT, 0, buffer.vertices)

        GL.glDrawElements(
            GL.GL_LINES,
            len(buffer.edges) * 2,
            GL.GL_UNSIGNED_INT,
            buffer.edges.flatten()
        )

        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

    def _draw_grid_and_axes(self) -> None:
        """Dessine la grille au sol XY avec tracé de tampons précalculés (Zéro boucle par frame)."""
        GL.glDisable(GL.GL_LIGHTING)

        if self._grid_minor_pts is None or self._grid_major_pts is None:
            self._rebuild_grid_geometry()

        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)

        # 1. Lignes secondaires (fines et discrètes)
        if self._grid_minor_pts is not None and len(self._grid_minor_pts) > 0:
            GL.glLineWidth(1.0)
            GL.glColor4f(0.25, 0.27, 0.32, 0.35)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, self._grid_minor_pts)
            GL.glDrawArrays(GL.GL_LINES, 0, len(self._grid_minor_pts))

        # 2. Lignes majeures tous les 50 mm
        if self._grid_major_pts is not None and len(self._grid_major_pts) > 0:
            GL.glLineWidth(1.2)
            GL.glColor4f(0.32, 0.35, 0.42, 0.65)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, self._grid_major_pts)
            GL.glDrawArrays(GL.GL_LINES, 0, len(self._grid_major_pts))

        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

        # 3. Axes principaux colorés (X = Rouge, Y = Vert, Z = Bleu)
        half = self.grid_size / 2.0
        step_minor = self.grid_spacing
        GL.glLineWidth(2.2)
        GL.glBegin(GL.GL_LINES)
        # Axe X (Rouge éclatant)
        GL.glColor4f(0.95, 0.25, 0.25, 0.95)
        GL.glVertex3f(-half, 0.0, 0.0)
        GL.glVertex3f(half, 0.0, 0.0)

        # Axe Y (Vert forêt)
        GL.glColor4f(0.25, 0.85, 0.35, 0.95)
        GL.glVertex3f(0.0, -half, 0.0)
        GL.glVertex3f(0.0, half, 0.0)

        # Axe Z (Bleu - repère d'élévation vertical)
        GL.glColor4f(0.25, 0.55, 0.95, 0.95)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(0.0, 0.0, float(step_minor * 3))
        GL.glEnd()

        # 4. Point d'origine central (0, 0, 0)
        GL.glPointSize(5.0)
        GL.glColor4f(1.0, 0.85, 0.2, 1.0)
        GL.glBegin(GL.GL_POINTS)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glEnd()

    def _draw_orientation_triad(self, camera: CADCamera, width: int, height: int) -> None:
        """Affiche le trièdre de repère 3D avec flèches et libellés vectoriels X, Y, Z."""
        if width <= 0 or height <= 0:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)

        # Sauvegarder les matrices actuelles
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glViewport(12, 12, 95, 95)
        gluPerspective(45.0, 1.0, 0.1, 100.0)

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()

        # Positionner avec la même orientation que la caméra
        yaw_rad = np.radians(camera.yaw_deg)
        pitch_rad = np.radians(camera.pitch_deg)
        eye_x = float(5.0 * np.cos(pitch_rad) * np.sin(yaw_rad))
        eye_y = float(5.0 * np.cos(pitch_rad) * np.cos(yaw_rad))
        eye_z = float(5.0 * np.sin(pitch_rad))

        gluLookAt(eye_x, eye_y, eye_z, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)

        # Dessiner les 3 branches X, Y, Z
        GL.glLineWidth(2.5)
        GL.glBegin(GL.GL_LINES)
        # Axe X
        GL.glColor3f(0.95, 0.25, 0.25)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(1.7, 0.0, 0.0)
        # Axe Y
        GL.glColor3f(0.25, 0.85, 0.35)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(0.0, 1.7, 0.0)
        # Axe Z
        GL.glColor3f(0.25, 0.55, 0.95)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(0.0, 0.0, 1.7)
        GL.glEnd()

        # Marqueurs aux extrémités
        GL.glPointSize(6.0)
        GL.glBegin(GL.GL_POINTS)
        GL.glColor3f(0.95, 0.25, 0.25)
        GL.glVertex3f(1.7, 0.0, 0.0)
        GL.glColor3f(0.25, 0.85, 0.35)
        GL.glVertex3f(0.0, 1.7, 0.0)
        GL.glColor3f(0.25, 0.55, 0.95)
        GL.glVertex3f(0.0, 0.0, 1.7)
        GL.glEnd()

        # Tracé des lettres vectorielles X, Y, Z
        GL.glLineWidth(1.8)
        GL.glBegin(GL.GL_LINES)
        # X
        GL.glColor3f(1.0, 0.45, 0.45)
        GL.glVertex3f(2.0, -0.12, -0.12)
        GL.glVertex3f(2.0, 0.12, 0.12)
        GL.glVertex3f(2.0, -0.12, 0.12)
        GL.glVertex3f(2.0, 0.12, -0.12)

        # Y
        GL.glColor3f(0.45, 1.0, 0.55)
        GL.glVertex3f(-0.12, 2.0, 0.12)
        GL.glVertex3f(0.0, 2.0, 0.0)
        GL.glVertex3f(0.12, 2.0, 0.12)
        GL.glVertex3f(0.0, 2.0, 0.0)
        GL.glVertex3f(0.0, 2.0, 0.0)
        GL.glVertex3f(0.0, 2.0, -0.12)

        # Z
        GL.glColor3f(0.45, 0.75, 1.0)
        GL.glVertex3f(-0.12, 0.0, 2.0)
        GL.glVertex3f(0.12, 0.0, 2.0)
        GL.glVertex3f(0.12, 0.0, 2.0)
        GL.glVertex3f(-0.12, 0.0, 1.8)
        GL.glVertex3f(-0.12, 0.0, 1.8)
        GL.glVertex3f(0.12, 0.0, 1.8)
        GL.glEnd()

        # Restaurer matrices et viewport
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glViewport(0, 0, width, height)
        GL.glEnable(GL.GL_DEPTH_TEST)
