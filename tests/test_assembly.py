"""
Tests unitaires pour le moteur d'assemblage mécanique et la détection d'interférences.
"""

import math
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


def test_assembly_facade_reexports() -> None:
    """Vérifie que la façade src.assembly ré-exporte tous les composants de manière intègre."""
    import src.assembly as asm

    expected_symbols = [
        "JointType", "MechanicalJoint", "InterferenceResult", "AssemblyManager",
        "MateType", "AssemblyMate", "AssemblyInstance", "AssemblySolver",
        "TransmissionSense", "GearMate", "RackPinionMate", "ScrewMate", "BallJointMate",
        "ExplodedStep", "ExplodedViewGenerator", "ExplodedViewStep", "ExplodedViewEngine",
        "FusionJointType", "JointLimit", "JointAnchor", "AssemblyJoint", "JointKinematicSolver",
        "ClosedLoopDynamicsResult", "ClosedLoopKinematicEngine", "ClosedLoopKinematicSolver",
    ]
    for sym in expected_symbols:
        assert hasattr(asm, sym), f"Le symbole {sym} doit être exposé par src.assembly"
        assert getattr(asm, sym) is not None


def test_assembly_kinematic_transmission_mates() -> None:
    """Vérifie la cinématique des liaisons engrenage et vis-écrou via la façade."""
    from src.assembly import GearMate, ScrewMate, TransmissionSense
    from src.core.types import Vector3D

    gear = GearMate(
        id="gear_pair_1",
        part_a_id="pinion",
        part_b_id="wheel",
        axis_a_origin=Vector3D(0.0, 0.0, 0.0),
        axis_a_direction=Vector3D(0.0, 0.0, 1.0),
        axis_b_origin=Vector3D(50.0, 0.0, 0.0),
        axis_b_direction=Vector3D(0.0, 0.0, 1.0),
        teeth_a=20,
        teeth_b=50,
        transmission=TransmissionSense.OPPOSITE
    )
    assert gear.teeth_a == 20
    assert gear.teeth_b == 50
    assert gear.transmission == TransmissionSense.OPPOSITE
    driven_angle = gear.compute_driven_angle(math.pi)
    assert abs(driven_angle - (-0.4 * math.pi)) < 1e-9

    screw = ScrewMate(
        id="lead_screw_1",
        screw_part_id="lead_screw",
        nut_part_id="carriage",
        axis_origin=Vector3D(0.0, 0.0, 0.0),
        axis_direction=Vector3D(0.0, 0.0, 1.0),
        pitch_mm=5.0
    )
    assert screw.pitch_mm == 5.0
    advance = screw.compute_axial_advance(2.0 * math.pi)
    assert abs(advance.z - 5.0) < 1e-9
