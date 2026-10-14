"""
Contrôleur de périphérique 3D 6 Degrés de Liberté (3Dconnexion SpaceMouse).
Traite les flux HID multi-axes avec filtrage par zone morte (Deadzone),
courbe exponentielle de sensibilité et amortissement inertiel pour la caméra CAO.
"""

from __future__ import annotations
from dataclasses import dataclass
import math
import struct
from typing import Optional, Tuple

from src.viewport.camera import CADCamera


@dataclass
class SpaceMouseConfig:
    """Configuration des sensibilités et inversions d'axes de la souris 3D."""
    sensitivity_orbit: float = 45.0      # Degrés par seconde à déflexion max
    sensitivity_pan: float = 12.0        # Unités de translation écran
    sensitivity_zoom: float = 1.8        # Taux de zoom relatif
    deadzone: float = 0.06               # Seuil minimal sous lequel l'entrée est ignorée (drift)
    power_curve: float = 1.8             # Exposant de réponse non-linéaire (précision fine)
    damping_factor: float = 0.82         # Amortissement inertiel (Apple-like fluidity)
    invert_orbit_x: bool = False
    invert_orbit_y: bool = False
    invert_pan_x: bool = False
    invert_pan_y: bool = False
    invert_zoom: bool = False


@dataclass
class SpaceMouseState:
    """État instantané des 6 axes normalisés [-1.0, 1.0]."""
    trans_x: float = 0.0
    trans_y: float = 0.0
    trans_z: float = 0.0
    rot_x: float = 0.0
    rot_y: float = 0.0
    rot_z: float = 0.0


class SpaceMouseController:
    """
    Contrôleur matériel et simulateur de souris 3D 6-DoF (3Dconnexion).
    Convertit les mouvements de translation et rotation simultanés en navigation caméra 3D.
    """

    def __init__(self, config: Optional[SpaceMouseConfig] = None) -> None:
        """Initialise le contrôleur avec sa configuration de sensibilité."""
        self.config = config or SpaceMouseConfig()
        self.current_state = SpaceMouseState()
        self.filtered_state = SpaceMouseState()
        self.is_connected: bool = False
        self.zero_offsets = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def calibrate_zero(self, raw_readings: Tuple[float, float, float, float, float, float]) -> None:
        """Enregistre le décalage au repos pour éliminer le drift matériel."""
        self.zero_offsets = raw_readings

    def _apply_deadzone_and_curve(self, raw_val: float, offset: float) -> float:
        """Applique le centrage, la zone morte et la réponse non-linéaire."""
        val = raw_val - offset
        val = max(-1.0, min(1.0, val))

        abs_val = abs(val)
        if abs_val <= self.config.deadzone:
            return 0.0

        # Normalisation au-delà de la zone morte
        normalized = (abs_val - self.config.deadzone) / (1.0 - self.config.deadzone)
        curved = math.pow(normalized, self.config.power_curve)
        return math.copysign(curved, val)

    def update_axes(
        self,
        raw_tx: float,
        raw_ty: float,
        raw_tz: float,
        raw_rx: float,
        raw_ry: float,
        raw_rz: float,
        dt: float = 0.016
    ) -> SpaceMouseState:
        """
        Traite les 6 axes normalisés bruts, applique le lissage et retourne l'état filtré.
        """
        self.is_connected = True

        tx = self._apply_deadzone_and_curve(raw_tx, self.zero_offsets[0])
        ty = self._apply_deadzone_and_curve(raw_ty, self.zero_offsets[1])
        tz = self._apply_deadzone_and_curve(raw_tz, self.zero_offsets[2])
        rx = self._apply_deadzone_and_curve(raw_rx, self.zero_offsets[3])
        ry = self._apply_deadzone_and_curve(raw_ry, self.zero_offsets[4])
        rz = self._apply_deadzone_and_curve(raw_rz, self.zero_offsets[5])

        if self.config.invert_pan_x:
            tx = -tx
        if self.config.invert_pan_y:
            ty = -ty
        if self.config.invert_zoom:
            tz = -tz
        if self.config.invert_orbit_x:
            rx = -rx
        if self.config.invert_orbit_y:
            rz = -rz

        # Filtre passe-bas IIR (Inertial Damping)
        alpha = 1.0 - math.pow(self.config.damping_factor, max(0.001, dt * 60.0))
        self.filtered_state.trans_x += alpha * (tx - self.filtered_state.trans_x)
        self.filtered_state.trans_y += alpha * (ty - self.filtered_state.trans_y)
        self.filtered_state.trans_z += alpha * (tz - self.filtered_state.trans_z)
        self.filtered_state.rot_x += alpha * (rx - self.filtered_state.rot_x)
        self.filtered_state.rot_y += alpha * (ry - self.filtered_state.rot_y)
        self.filtered_state.rot_z += alpha * (rz - self.filtered_state.rot_z)

        self.current_state = SpaceMouseState(tx, ty, tz, rx, ry, rz)
        return self.filtered_state

    def parse_hid_packet(self, packet_bytes: bytes) -> Optional[Tuple[str, float, float, float]]:
        """
        Décode un paquet USB HID 3Dconnexion standard (Report ID 1 = Translation, Report ID 2 = Rotation).
        Les valeurs sont des entiers 16 bits signés normalisés de -350..+350 à -1.0..+1.0.
        """
        if len(packet_bytes) < 7:
            return None

        report_id = packet_bytes[0]
        try:
            val_x, val_y, val_z = struct.unpack("<hhh", packet_bytes[1:7])
        except struct.error:
            return None

        scale_hid = 1.0 / 350.0
        norm_x = max(-1.0, min(1.0, float(val_x) * scale_hid))
        norm_y = max(-1.0, min(1.0, float(val_y) * scale_hid))
        norm_z = max(-1.0, min(1.0, float(val_z) * scale_hid))

        if report_id == 1:
            return ("TRANS", norm_x, norm_y, norm_z)
        elif report_id == 2:
            return ("ROT", norm_x, norm_y, norm_z)
        return None

    def apply_to_camera(self, camera: CADCamera, dt: float = 0.016) -> bool:
        """
        Applique les déflexions 6-DoF directement sur une caméra CADCamera.
        Retourne True si un mouvement significatif a eu lieu (nécessitant un redessin OpenGL).
        """
        state = self.filtered_state

        has_orbit = (abs(state.rot_x) > 1e-4 or abs(state.rot_z) > 1e-4)
        has_pan = (abs(state.trans_x) > 1e-4 or abs(state.trans_y) > 1e-4)
        has_zoom = (abs(state.trans_z) > 1e-4)

        if not (has_orbit or has_pan or has_zoom):
            return False

        # Orbite (Rotation caméra)
        if has_orbit:
            delta_yaw = state.rot_z * self.config.sensitivity_orbit * dt
            delta_pitch = state.rot_x * self.config.sensitivity_orbit * dt
            camera.orbit(delta_yaw, delta_pitch)

        # Panoramique (Translation écran)
        if has_pan:
            delta_screen_x = state.trans_x * self.config.sensitivity_pan * dt * 50.0
            delta_screen_y = state.trans_y * self.config.sensitivity_pan * dt * 50.0
            camera.pan(delta_screen_x, delta_screen_y, 600)

        # Zoom continu
        if has_zoom:
            zoom_multiplier = 1.0 - (state.trans_z * self.config.sensitivity_zoom * dt)
            camera.distance = max(1.0, min(10000.0, camera.distance * zoom_multiplier))

        return True
