"""
Contrôleur de caméra 3D orbitale pour la navigation CAO style Fusion 360.
Fournit les modes Orbite, Panoramique (Pan), Zoom et orientations prédéfinies.
"""

from __future__ import annotations
from typing import Tuple
import numpy as np

from src.core.types import Vector3D


class CADCamera:
    """
    Caméra 3D orbitale centrée sur une cible d'intérêt (Pivot / Target).
    Contrôles :
    - Orbite : rotation azimut et élévation autour de la cible
    - Pan : translation de la cible dans le plan de l'écran
    - Zoom : rapprochement/éloignement exponentiel fluide
    """

    def __init__(self) -> None:
        """Initialise la caméra dans la vue isométrique par défaut de Fusion 360."""
        self.target: Vector3D = Vector3D(0.0, 0.0, 0.0)
        self.distance: float = 120.0
        self.yaw_deg: float = 45.0      # Azimut
        self.pitch_deg: float = 30.0    # Élévation isométrique standard (Fusion 360)
        self.fov_deg: float = 45.0
        self.near_plane: float = 0.5
        self.far_plane: float = 5000.0
        self.is_orthographic: bool = False

    def get_ortho_height(self) -> float:
        """Calcule la hauteur du volume de vue orthographique en unités monde."""
        half_fov_rad = np.radians(self.fov_deg * 0.5)
        return float(2.0 * self.distance * np.tan(half_fov_rad))

    def get_ortho_width(self, aspect_ratio: float) -> float:
        """Calcule la largeur du volume de vue orthographique en unités monde."""
        return self.get_ortho_height() * max(1e-4, float(aspect_ratio))

    def toggle_projection_mode(self) -> bool:
        """Bascule entre la vue perspective et la vue orthographique."""
        self.is_orthographic = not self.is_orthographic
        return self.is_orthographic

    def toggle_orthographic(self) -> bool:
        """Alias de commodité pour toggle_projection_mode."""
        return self.toggle_projection_mode()

    def orbit(self, delta_yaw: float, delta_pitch: float) -> None:
        """Fait tourner la caméra autour de la cible."""
        self.yaw_deg = (self.yaw_deg + delta_yaw) % 360.0
        self.pitch_deg = max(-89.9, min(89.9, self.pitch_deg + delta_pitch))

    def pan(self, delta_screen_x: float, delta_screen_y: float, viewport_height: int) -> None:
        """Décale la cible et la caméra parallèlement à l'écran."""
        if viewport_height <= 0:
            return

        scale = (self.distance * 0.002) * (600.0 / max(100.0, float(viewport_height)))
        _forward, right, up = self.get_camera_axes()

        offset_x = right.scale(-delta_screen_x * scale * 25.0)
        offset_y = up.scale(delta_screen_y * scale * 25.0)

        self.target = self.target.add(offset_x).add(offset_y)

    def zoom(self, delta_scroll: float) -> None:
        """Zoome en avant ou en arrière vers la cible."""
        factor = 0.9 if delta_scroll > 0 else 1.1
        self.distance = max(1.0, min(10000.0, self.distance * factor))

    def get_eye_position(self) -> Vector3D:
        """Calcule la position globale (Eye) de la caméra."""
        yaw_rad = np.radians(self.yaw_deg)
        pitch_rad = np.radians(self.pitch_deg)

        eye_offset = Vector3D(
            float(self.distance * np.cos(pitch_rad) * np.sin(yaw_rad)),
            float(self.distance * np.cos(pitch_rad) * np.cos(yaw_rad)),
            float(self.distance * np.sin(pitch_rad))
        )
        return self.target.add(eye_offset)

    _PRESET_VIEWS: Dict[str, Tuple[float, float]] = {
        "TOP": (0.0, 89.9),
        "HAUT": (0.0, 89.9),
        "BOTTOM": (0.0, -89.9),
        "BAS": (0.0, -89.9),
        "FRONT": (0.0, 0.0),
        "FACE": (0.0, 0.0),
        "BACK": (180.0, 0.0),
        "ARRIERE": (180.0, 0.0),
        "RIGHT": (90.0, 0.0),
        "DROITE": (90.0, 0.0),
        "LEFT": (270.0, 0.0),
        "GAUCHE": (270.0, 0.0),
        "ISOMETRIC": (45.0, 30.0),
        "HOME": (45.0, 30.0),
    }

    def set_preset_view(self, preset_name: str) -> None:
        """Positionne la caméra selon un angle prédéfini du ViewCube."""
        angles = self._PRESET_VIEWS.get(preset_name.upper())
        if angles is not None:
            self.yaw_deg, self.pitch_deg = angles

    def fit_all(self, bounding_min: Vector3D, bounding_max: Vector3D) -> None:
        """Recentre et ajuste la distance pour englober toute la géométrie."""
        center = Vector3D(
            (bounding_min.x + bounding_max.x) * 0.5,
            (bounding_min.y + bounding_max.y) * 0.5,
            (bounding_min.z + bounding_max.z) * 0.5
        )
        diagonal = bounding_max.subtract(bounding_min).length()
        self.target = center
        self.distance = max(40.0, diagonal * 1.8)

    def get_camera_axes(self) -> Tuple[Vector3D, Vector3D, Vector3D]:
        """
        Calcule les trois vecteurs unitaires du repère caméra dans le monde :
        (forward_dir, right_dir, up_dir).
        forward_dir pointe de l'œil vers la cible.
        Garantit une continuité géométrique sans singularité ni saut d'Euler.
        """
        eye = self.get_eye_position()
        forward = self.target.subtract(eye).normalized()

        yaw_rad = np.radians(self.yaw_deg)
        # Vecteur droit horizontal continu orthogonal à la ligne de visée
        right = Vector3D(float(np.cos(yaw_rad)), float(-np.sin(yaw_rad)), 0.0).normalized()
        up = forward.cross(right).normalized()
        return (forward, right, up)

    def unproject_ray(
        self,
        screen_x: float,
        screen_y: float,
        viewport_width: int,
        viewport_height: int
    ) -> Tuple[Vector3D, Vector3D]:
        """
        Convertit un clic écran 2D en rayon spatial 3D (Origine, Direction unitaire).
        Gère à la fois la perspective (rayons coniques) et l'orthographique (rayons parallèles).
        """
        w = max(1.0, float(viewport_width))
        h = max(1.0, float(viewport_height))

        # Coordonnées normalisées [-1.0, +1.0]
        x_ndc = (2.0 * screen_x / w) - 1.0
        y_ndc = 1.0 - (2.0 * screen_y / h)
        aspect_ratio = w / h

        forward, right, up = self.get_camera_axes()

        if self.is_orthographic:
            ortho_h = self.get_ortho_height()
            ortho_w = self.get_ortho_width(aspect_ratio)
            x_world = x_ndc * (ortho_w * 0.5)
            y_world = y_ndc * (ortho_h * 0.5)
            ray_origin = self.get_eye_position().add(right.scale(x_world)).add(up.scale(y_world))
            ray_dir = forward
            return (ray_origin, ray_dir)

        half_fov_rad = np.radians(self.fov_deg * 0.5)
        tan_half_fov = float(np.tan(half_fov_rad))

        x_cam = x_ndc * aspect_ratio * tan_half_fov
        y_cam = y_ndc * tan_half_fov

        ray_dir = forward.add(right.scale(x_cam)).add(up.scale(y_cam)).normalized()
        ray_origin = self.get_eye_position()

        return (ray_origin, ray_dir)

