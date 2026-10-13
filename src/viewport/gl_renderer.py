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
        self.bg_color_top: Tuple[float, float, float] = (0.18, 0.20, 0.24)
        self.bg_color_bottom: Tuple[float, float, float] = (0.12, 0.13, 0.16)

    def initialize_gl(self) -> None:
        """Configure les états OpenGL initiaux (profondeur, antialiasing, éclairage)."""
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # Anti-aliasing pour des arêtes bien nettes
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glHint(GL.GL_LINE_SMOOTH_HINT, GL.GL_NICEST)

        # Éclairage de base
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_LIGHT1)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)

        # Lumière principale (orientée depuis le haut)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [100.0, 100.0, 200.0, 0.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [0.85, 0.85, 0.88, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])

        # Lumière de remplissage (douce par le dessous)
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, [-100.0, -100.0, -100.0, 0.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, [0.35, 0.35, 0.38, 1.0])

        # Couleur de fond sombre Fusion 360
        GL.glClearColor(0.15, 0.16, 0.18, 1.0)

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

    def render_scene(self, camera: CADCamera, mesh_buffers: List[MeshBuffer], width: int, height: int) -> None:
        """Effectue le rendu complet de la scène 3D."""
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
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

        # 2. Rendu des corps solides (Faces ombrées)
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
        """Dessine les faces du maillage avec éclairage et normales."""
        if buffer.is_empty():
            return

        c = buffer.color
        GL.glColor4f(c.r, c.g, c.b, c.a)

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
        """Dessine la grille au sol XY et les axes de coordonnées colorés."""
        GL.glDisable(GL.GL_LIGHTING)
        GL.glLineWidth(1.0)

        half = self.grid_size / 2.0
        step = self.grid_spacing

        # Lignes secondaires de la grille
        GL.glColor4f(0.24, 0.26, 0.30, 0.5)
        GL.glBegin(GL.GL_LINES)
        x = -half
        while x <= half:
            if abs(x) > 1e-4:  # Éviter l'axe central
                GL.glVertex3f(float(x), -half, 0.0)
                GL.glVertex3f(float(x), half, 0.0)
            x += step

        y = -half
        while y <= half:
            if abs(y) > 1e-4:
                GL.glVertex3f(-half, float(y), 0.0)
                GL.glVertex3f(half, float(y), 0.0)
            y += step
        GL.glEnd()

        # Axes principaux colorés (X = Rouge, Y = Vert, Z = Bleu)
        GL.glLineWidth(2.0)
        GL.glBegin(GL.GL_LINES)
        # Axe X (Rouge)
        GL.glColor4f(0.95, 0.25, 0.25, 0.9)
        GL.glVertex3f(-half, 0.0, 0.0)
        GL.glVertex3f(half, 0.0, 0.0)

        # Axe Y (Vert)
        GL.glColor4f(0.25, 0.85, 0.35, 0.9)
        GL.glVertex3f(0.0, -half, 0.0)
        GL.glVertex3f(0.0, half, 0.0)

        # Axe Z (Bleu - court repère d'élévation)
        GL.glColor4f(0.25, 0.55, 0.95, 0.9)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(0.0, 0.0, float(step * 3))
        GL.glEnd()

    def _draw_orientation_triad(self, camera: CADCamera, width: int, height: int) -> None:
        """Affiche le trièdre de repère 3D compact dans le coin inférieur gauche."""
        if width <= 0 or height <= 0:
            return

        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)

        # Sauvegarder les matrices actuelles
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glViewport(10, 10, 90, 90)
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
        GL.glVertex3f(1.8, 0.0, 0.0)
        # Axe Y
        GL.glColor3f(0.25, 0.85, 0.35)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(0.0, 1.8, 0.0)
        # Axe Z
        GL.glColor3f(0.25, 0.55, 0.95)
        GL.glVertex3f(0.0, 0.0, 0.0)
        GL.glVertex3f(0.0, 0.0, 1.8)
        GL.glEnd()

        # Restaurer matrices et viewport
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glViewport(0, 0, width, height)
        GL.glEnable(GL.GL_DEPTH_TEST)
