"""
Moteur de styles d'affichage et d'analyse de surface inspiré de Blender et Fusion 360.
Fournit les MatCaps studio (Clay, Red Wax, Chrome) et les analyses industrielles de surface :
- Bandes zébrées de réflexion (Fusion 360 Zebra Analysis pour continuité G0/G1/G2)
- Analyse d'angle de dépouille pour moules d'injection plastique (Draft Angle Analysis)
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Tuple, Optional
import math
import numpy as np

from src.core.types import MeshBuffer, Vector3D, ColorRGBA


class ShadingMode(Enum):
    """Modes d'affichage du viewport inspirés de Blender et Autodesk Fusion 360."""
    SHADED_EDGES = "shaded_edges"        # Rendu CAO métallique avec arêtes noires vives
    WIREFRAME = "wireframe"              # Filaire intégral
    MATCAP_CLAY = "matcap_clay"          # MatCap Argile studio (Blender Clay)
    MATCAP_RED_WAX = "matcap_red_wax"    # MatCap Cire rouge (Blender / ZBrush Red Wax)
    MATCAP_CHROME = "matcap_chrome"      # MatCap Chrome miroir haute brillance
    ZEBRA_STRIPES = "zebra_stripes"      # Bandes de réflexion zébrées (Fusion 360 Zebra Stripes)
    DRAFT_ANGLE = "draft_angle"          # Analyse d'angle de dépouille pour plasturgie (Draft Angle)


class ViewportShadingManager:
    """Gestionnaire de calcul des shaders et textures de surface pour le viewport OpenGL."""

    def __init__(self) -> None:
        self.active_mode: ShadingMode = ShadingMode.SHADED_EDGES
        self.zebra_frequency: float = 24.0
        self.draft_pull_direction: Vector3D = Vector3D(0.0, 0.0, 1.0)
        self.draft_threshold_deg: float = 1.0

    def set_shading_mode(self, mode: ShadingMode) -> None:
        """Change le mode d'ombrage actif."""
        self.active_mode = mode

    def apply_shading_to_buffer(self, buffer: MeshBuffer, camera_eye: Vector3D) -> MeshBuffer:
        """
        Calcule les couleurs de sommets (vertex_colors) adaptées au mode de shading actif.
        Retourne un MeshBuffer prêt à être affiché par le moteur OpenGL.
        """
        if buffer.is_empty() or buffer.normals is None or len(buffer.normals) == 0:
            return buffer

        if self.active_mode == ShadingMode.SHADED_EDGES:
            # Réinitialiser aux couleurs de matière par défaut
            res = MeshBuffer(
                vertices=buffer.vertices,
                faces=buffer.faces,
                normals=buffer.normals,
                edges=buffer.edges,
                edge_vertices=buffer.edge_vertices,
                color=buffer.color,
                vertex_colors=None
            )
            return res

        num_verts = len(buffer.vertices)
        v_colors = np.zeros((num_verts, 4), dtype=np.float32)

        if self.active_mode == ShadingMode.MATCAP_CLAY:
            v_colors = self._compute_clay_matcap(buffer.normals)
        elif self.active_mode == ShadingMode.MATCAP_RED_WAX:
            v_colors = self._compute_red_wax_matcap(buffer.normals, buffer.vertices, camera_eye)
        elif self.active_mode == ShadingMode.MATCAP_CHROME:
            v_colors = self._compute_chrome_matcap(buffer.normals, buffer.vertices, camera_eye)
        elif self.active_mode == ShadingMode.ZEBRA_STRIPES:
            v_colors = self._compute_zebra_stripes(buffer.normals, buffer.vertices, camera_eye)
        elif self.active_mode == ShadingMode.DRAFT_ANGLE:
            v_colors = self._compute_draft_angle(buffer.normals)
        else:
            return buffer

        res = MeshBuffer(
            vertices=buffer.vertices,
            faces=buffer.faces,
            normals=buffer.normals,
            edges=buffer.edges,
            edge_vertices=buffer.edge_vertices,
            color=buffer.color,
            vertex_colors=v_colors
        )
        return res

    def _compute_clay_matcap(self, normals: np.ndarray) -> np.ndarray:
        """Simule la MatCap Argile studio de Blender (lumière douce et tons chauds)."""
        light_dir = np.array([0.4, 0.4, 0.82], dtype=np.float32)
        light_dir /= np.linalg.norm(light_dir)

        dots = np.clip(np.dot(normals, light_dir), 0.0, 1.0)
        n_verts = len(normals)
        colors = np.zeros((n_verts, 4), dtype=np.float32)

        base_r, base_g, base_b = 0.72, 0.58, 0.48
        amb_r, amb_g, amb_b = 0.28, 0.22, 0.20

        for i in range(n_verts):
            d = float(dots[i])
            colors[i, 0] = amb_r + base_r * d
            colors[i, 1] = amb_g + base_g * d
            colors[i, 2] = amb_b + base_b * d
            colors[i, 3] = 1.0

        return colors

    def _compute_red_wax_matcap(self, normals: np.ndarray, vertices: np.ndarray, eye: Vector3D) -> np.ndarray:
        """Simule la MatCap Cire Rouge légendaire de ZBrush et Blender."""
        n_verts = len(normals)
        colors = np.zeros((n_verts, 4), dtype=np.float32)
        eye_arr = np.array([eye.x, eye.y, eye.z], dtype=np.float32)

        for i in range(n_verts):
            n = normals[i]
            v = eye_arr - vertices[i]
            dist = float(np.linalg.norm(v))
            v_dir = v / (dist if dist > 1e-6 else 1.0)

            dot = max(0.0, float(np.dot(n, v_dir)))
            rim = math.pow(1.0 - dot, 2.5)

            # Couleur rouge rubis avec halo ambre sur la bordure (Rim Light)
            colors[i, 0] = min(1.0, 0.65 * dot + 0.95 * rim)
            colors[i, 1] = min(1.0, 0.18 * dot + 0.45 * rim)
            colors[i, 2] = min(1.0, 0.18 * dot + 0.15 * rim)
            colors[i, 3] = 1.0

        return colors

    def _compute_chrome_matcap(self, normals: np.ndarray, vertices: np.ndarray, eye: Vector3D) -> np.ndarray:
        """Simule un miroir chromé ultra-réfléchissant."""
        n_verts = len(normals)
        colors = np.zeros((n_verts, 4), dtype=np.float32)
        eye_arr = np.array([eye.x, eye.y, eye.z], dtype=np.float32)

        for i in range(n_verts):
            n = normals[i]
            v = eye_arr - vertices[i]
            dist = float(np.linalg.norm(v))
            v_dir = v / (dist if dist > 1e-6 else 1.0)

            # Vecteur de réflexion spéculaire R = 2*(N.V)*N - V
            dot = float(np.dot(n, v_dir))
            rx = 2.0 * dot * n[0] - v_dir[0]
            ry = 2.0 * dot * n[1] - v_dir[1]
            rz = 2.0 * dot * n[2] - v_dir[2]

            # Horizon chromé avec gradient métallique
            val = 0.5 + 0.5 * rz
            colors[i, 0] = float(val * 0.90)
            colors[i, 1] = float(val * 0.92)
            colors[i, 2] = float(val * 0.98)
            colors[i, 3] = 1.0

        return colors

    def _compute_zebra_stripes(self, normals: np.ndarray, vertices: np.ndarray, eye: Vector3D) -> np.ndarray:
        """
        Génère les bandes zébrées de réflexion (Fusion 360 / Alias Zebra Analysis).
        Permet le contrôle visuel instantané de la continuité de courbure (G0, G1, G2).
        """
        n_verts = len(normals)
        colors = np.zeros((n_verts, 4), dtype=np.float32)
        eye_arr = np.array([eye.x, eye.y, eye.z], dtype=np.float32)
        freq = self.zebra_frequency

        for i in range(n_verts):
            n = normals[i]
            v = eye_arr - vertices[i]
            dist = float(np.linalg.norm(v))
            v_dir = v / (dist if dist > 1e-6 else 1.0)

            dot = float(np.dot(n, v_dir))
            rz = 2.0 * dot * n[2] - v_dir[2]

            # Fonction sinusoïdale de rayure zébrée
            stripe_val = 0.5 * (1.0 + math.sin(freq * rz))
            shade = 0.12 if stripe_val < 0.5 else 0.92

            colors[i, 0] = shade
            colors[i, 1] = shade
            colors[i, 2] = shade
            colors[i, 3] = 1.0

        return colors

    def _compute_draft_angle(self, normals: np.ndarray) -> np.ndarray:
        """
        Analyse d'angle de dépouille pour plasturgie et fonderie (Fusion 360 Draft Analysis).
        - Vert : Dépouille positive (> 1°) - démoulage parfait
        - Jaune : Mur vertical (-0.5° à 1°) - frottement au démoulage
        - Rouge : Contre-dépouille (< -0.5°) - pièce coincée dans le moule
        """
        pull = np.array([
            self.draft_pull_direction.x,
            self.draft_pull_direction.y,
            self.draft_pull_direction.z
        ], dtype=np.float32)
        pull /= np.linalg.norm(pull)

        n_verts = len(normals)
        colors = np.zeros((n_verts, 4), dtype=np.float32)

        for i in range(n_verts):
            n = normals[i]
            cos_theta = float(np.dot(n, pull))
            cos_theta = max(-1.0, min(1.0, cos_theta))
            angle_from_plane_deg = 90.0 - math.degrees(math.acos(cos_theta))

            if angle_from_plane_deg > self.draft_threshold_deg:
                # Vert émeraude (Dépouille positive conforme)
                colors[i, 0] = 0.15
                colors[i, 1] = 0.85
                colors[i, 2] = 0.35
            elif angle_from_plane_deg >= -0.5:
                # Jaune alerte (Mur vertical / critique)
                colors[i, 0] = 0.95
                colors[i, 1] = 0.85
                colors[i, 2] = 0.15
            else:
                # Rouge danger (Contre-dépouille bloquante)
                colors[i, 0] = 0.92
                colors[i, 1] = 0.20
                colors[i, 2] = 0.20
            colors[i, 3] = 1.0

        return colors
