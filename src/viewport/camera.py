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

    def orbit(self, delta_yaw: float, delta_pitch: float) -> None:
        """Fait tourner la caméra autour de la cible."""
        self.yaw_deg = (self.yaw_deg + delta_yaw) % 360.0
        self.pitch_deg = max(-89.9, min(89.9, self.pitch_deg + delta_pitch))

    def pan(self, delta_screen_x: float, delta_screen_y: float, viewport_height: int) -> None:
        """Décale la cible et la caméra parallèlement à l'écran."""
        if viewport_height <= 0:
            return

        # Ajuster l'échelle selon la distance et la taille de la fenêtre
        scale = (self.distance * 0.002) * (600.0 / max(100.0, float(viewport_height)))

        # Calculer les vecteurs droit et haut dans le repère de la caméra
        yaw_rad = np.radians(self.yaw_deg)
        pitch_rad = np.radians(self.pitch_deg)

        forward = Vector3D(
            float(np.cos(pitch_rad) * np.sin(yaw_rad)),
            float(np.cos(pitch_rad) * np.cos(yaw_rad)),
            float(np.sin(pitch_rad))
        )
        # Éviter la singularité du produit vectoriel au zénith/nadir (vues TOP et BOTTOM)
        if abs(self.pitch_deg) > 85.0:
            world_up = Vector3D(0.0, 1.0, 0.0) if self.pitch_deg > 0 else Vector3D(0.0, -1.0, 0.0)
        else:
            world_up = Vector3D(0.0, 0.0, 1.0)
        right = forward.cross(world_up).normalized()
        up = right.cross(forward).normalized()

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
        """
        eye = self.get_eye_position()
        forward = self.target.subtract(eye).normalized()

        if abs(self.pitch_deg) > 85.0:
            world_up = Vector3D(0.0, 1.0, 0.0) if self.pitch_deg > 0 else Vector3D(0.0, -1.0, 0.0)
        else:
            world_up = Vector3D(0.0, 0.0, 1.0)

        right = forward.cross(world_up).normalized()
        up = right.cross(forward).normalized()
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
        Permet le picking 3D interactif des faces, arêtes et sommets à la souris.
        """
        w = max(1.0, float(viewport_width))
        h = max(1.0, float(viewport_height))

        # Coordonnées normalisées [-1.0, +1.0]
        x_ndc = (2.0 * screen_x / w) - 1.0
        y_ndc = 1.0 - (2.0 * screen_y / h)

        aspect_ratio = w / h
        half_fov_rad = np.radians(self.fov_deg * 0.5)
        tan_half_fov = float(np.tan(half_fov_rad))

        x_cam = x_ndc * aspect_ratio * tan_half_fov
        y_cam = y_ndc * tan_half_fov

        forward, right, up = self.get_camera_axes()
        ray_dir = forward.add(right.scale(x_cam)).add(up.scale(y_cam)).normalized()
        ray_origin = self.get_eye_position()

        return (ray_origin, ray_dir)

