"""
Tests unitaires pour la caméra 3D orbitale de CAO (CADCamera).
"""

import pytest
from src.viewport.camera import CADCamera
from src.core.types import Vector3D


def test_camera_initial_state() -> None:
    """Vérifie l'état initial de la caméra."""
    cam = CADCamera()
    assert cam.target == Vector3D(0.0, 0.0, 0.0)
    assert cam.distance == 120.0
    assert cam.yaw_deg == 45.0
    assert cam.pitch_deg == 30.0


def test_camera_orbit() -> None:
    """Vérifie la rotation azimutale et l'élévation."""
    cam = CADCamera()
    cam.orbit(10.0, 15.0)
    assert cam.yaw_deg == 55.0
    assert cam.pitch_deg == 45.0

    # Test clamping du pitch
    cam.orbit(0.0, 100.0)
    assert cam.pitch_deg <= 89.9


def test_camera_zoom() -> None:
    """Vérifie le zoom avant et arrière."""
    cam = CADCamera()
    d0 = cam.distance
    cam.zoom(120.0)
    assert cam.distance < d0  # Zoom in = distance réduite

    cam.zoom(-120.0)
    assert cam.distance > 0.0


def test_camera_presets() -> None:
    """Vérifie les presets du ViewCube (TOP, FRONT, RIGHT, HOME)."""
    cam = CADCamera()

    cam.set_preset_view("TOP")
    assert cam.yaw_deg == 0.0
    assert cam.pitch_deg == 89.9

    cam.set_preset_view("FRONT")
    assert cam.yaw_deg == 0.0
    assert cam.pitch_deg == 0.0

    cam.set_preset_view("RIGHT")
    assert cam.yaw_deg == 90.0
    assert cam.pitch_deg == 0.0

    cam.set_preset_view("HOME")
    assert cam.yaw_deg == 45.0
    assert cam.pitch_deg == 30.0


def test_camera_fit_all() -> None:
    """Vérifie l'ajustement automatique de la vue sur une boîte englobante."""
    cam = CADCamera()
    b_min = Vector3D(-10.0, -10.0, -10.0)
    b_max = Vector3D(10.0, 10.0, 10.0)
    cam.fit_all(b_min, b_max)

    assert cam.target == Vector3D(0.0, 0.0, 0.0)
    assert cam.distance > 20.0


def test_camera_pan_and_eye() -> None:
    """Vérifie le panoramique (pan) et la position de l'œil (eye)."""
    cam = CADCamera()
    t0 = cam.target
    cam.pan(10.0, 20.0, 600)
    assert cam.target != t0

    eye = cam.get_eye_position()
    assert eye.length() > 0.0
