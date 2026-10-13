"""
Tests unitaires pour le moteur d'assemblage mécanique et la détection d'interférences.
"""

import pytest
from src.core.geometry import make_box
from src.core.types import Vector3D
from src.assembly.assembly_manager import AssemblyManager, JointType


def test_assembly_joints_and_animation() -> None:
    """Vérifie la création d'une liaison pivot et sa transformation cinématique."""
    mgr = AssemblyManager()
    joint = mgr.add_joint("j_piv", "Pivot", JointType.REVOLUTE, "base", "rotor", axis=Vector3D(0.0, 0.0, 1.0))
    assert joint.joint_type == JointType.REVOLUTE

    rotor = make_box(20.0, 10.0, 10.0)
    bodies = {"base": make_box(30.0, 30.0, 10.0), "rotor": rotor}

    updated = mgr.animate_joint("j_piv", bodies, new_value=90.0)
    assert "rotor" in updated
    assert updated["rotor"].volume() == rotor.volume()


def test_interference_detection() -> None:
    """Vérifie la détection de collision physique entre deux solides."""
    b1 = make_box(20.0, 20.0, 20.0, center=True)
    # b2 chevauche b1
    b2 = make_box(20.0, 20.0, 20.0, center=True).translate(Vector3D(10.0, 0.0, 0.0))
    # b3 ne touche pas b1
    b3 = make_box(20.0, 20.0, 20.0, center=True).translate(Vector3D(100.0, 0.0, 0.0))

    res_overlap = AssemblyManager.check_interference(b1, b2)
    assert res_overlap.has_collision
    assert res_overlap.overlap_volume_mm3 > 0.0

    res_no_overlap = AssemblyManager.check_interference(b1, b3)
    assert not res_no_overlap.has_collision
    assert res_no_overlap.overlap_volume_mm3 == 0.0
