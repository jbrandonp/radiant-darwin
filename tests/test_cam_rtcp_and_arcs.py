"""
Tests unitaires pour la cinématique RTCP 5 axes et l'interpolation d'arcs G02/G03.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.types import Vector3D
from src.cam.five_axis_cam import (
    MachineKinematics5Axis,
    ToolHolderGeometry,
    FiveAxisToolPoint,
    RTCPKinematicsEngine,
    GCodeArcInterpolator,
)


def test_rtcp_forward_and_inverse_kinematics():
    """Vérifie la cohérence géométrique bidirectionnelle de la cinématique RTCP."""
    engine = RTCPKinematicsEngine(
        kinematics_type=MachineKinematics5Axis.TABLE_TABLE_AC,
        pivot_offset_xyz=(0.0, 0.0, 200.0),
        tool_length_gage_mm=100.0
    )

    work_pos = Vector3D(50.0, 30.0, 20.0)
    # Vecteur incliné à 30 degrés autour de X
    tool_vec = Vector3D(0.0, math.sin(math.radians(30.0)), math.cos(math.radians(30.0))).normalized()

    # Cinématique inverse : repère pièce -> coordonnées machine
    mach_pos, rot1, rot2 = engine.workpiece_to_machine(work_pos, tool_vec)
    assert rot1 == pytest.approx(30.0, abs=1e-2)

    # Cinématique directe : coordonnées machine -> repère pièce
    reconstructed_pos, reconstructed_vec = engine.machine_to_workpiece(mach_pos, rot1, rot2)

    assert reconstructed_pos.x == pytest.approx(work_pos.x, abs=1e-2)
    assert reconstructed_pos.y == pytest.approx(work_pos.y, abs=1e-2)
    assert reconstructed_pos.z == pytest.approx(work_pos.z, abs=1e-2)

    assert reconstructed_vec.x == pytest.approx(tool_vec.x, abs=1e-2)
    assert reconstructed_vec.y == pytest.approx(tool_vec.y, abs=1e-2)
    assert reconstructed_vec.z == pytest.approx(tool_vec.z, abs=1e-2)


def test_arc_interpolator_chordal_tolerance():
    """Vérifie la discrétisation d'un arc de cercle sous contrainte de flèche géométrique."""
    interpolator = GCodeArcInterpolator(chordal_tolerance_mm=0.005)

    start = (100.0, 0.0)
    end = (0.0, 100.0)
    center_offset = (-100.0, 0.0)  # Centre en (0, 0), rayon = 100 mm

    points = interpolator.interpolate_arc_2d(start, end, center_offset, is_clockwise=False)
    assert len(points) >= 4
    assert points[0] == pytest.approx(start, abs=1e-3)
    assert points[-1] == pytest.approx(end, abs=1e-3)

    # Vérification que tous les points sont sur le cercle de rayon 100 mm
    for px, py in points:
        dist = math.hypot(px, py)
        assert dist == pytest.approx(100.0, abs=1e-3)


def test_helical_gcode_generation():
    """Vérifie la génération de blocs G-code hélicoïdaux G02."""
    interpolator = GCodeArcInterpolator()
    p0 = Vector3D(50.0, 0.0, 10.0)
    p1 = Vector3D(50.0, 0.0, 8.0)
    gcode = interpolator.generate_helical_gcode(p0, p1, center_ij=(-50.0, 0.0), pitch_mm=2.0, is_clockwise=True)

    assert "G02" in gcode
    assert "X50.0000" in gcode
    assert "Z8.0000" in gcode
    assert "I-50.0000" in gcode
    assert "P2.000" in gcode
