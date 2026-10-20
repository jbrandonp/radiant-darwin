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


def test_assembly_arbitrary_axis_rodrigues_rotation() -> None:
    """Vérifie la cinématique de rotation exacte autour d'un axe 3D oblique non-cartésien (1, 1, 0)."""
    from src.assembly.kinematics.rodrigues import (
        compute_rodrigues_rotation_matrix,
        apply_rodrigues_rotation
    )
    # Rotation 90° autour de l'axe diagonal (1, 1, 0)
    axis = Vector3D(1.0, 1.0, 0.0)
    R = compute_rodrigues_rotation_matrix(axis, 90.0)
    # R doit être strictement orthonormale : R * R.T = I
    import numpy as np
    assert np.allclose(R @ R.T, np.eye(3), atol=1e-6)
    assert pytest.approx(float(np.linalg.det(R)), 1e-6) == 1.0

    # Application à un solide
    box = make_box(10.0, 10.0, 10.0)
    rotated = apply_rodrigues_rotation(box, axis, 90.0)
    assert pytest.approx(rotated.volume(), 1e-3) == box.volume()


def test_assembly_manager_revolute_with_origin_anchor() -> None:
    """Vérifie qu'une liaison pivot avec point d'ancrage décentré pivote autour du centre défini."""
    mgr = AssemblyManager()
    joint = mgr.add_joint(
        "j_anchor", "PivotAnchor", JointType.REVOLUTE, "base", "arm",
        axis=Vector3D(0.0, 0.0, 1.0),
        origin=Vector3D(50.0, 50.0, 0.0)
    )
    arm = make_box(10.0, 10.0, 10.0)
    bodies = {"base": make_box(100.0, 100.0, 10.0), "arm": arm}
    updated = mgr.animate_joint("j_anchor", bodies, new_value=180.0)
    assert "arm" in updated
    assert pytest.approx(updated["arm"].volume(), 1e-3) == arm.volume()


def test_assembly_link_zero_copy_and_instancing() -> None:
    """
    Vérifie la parité industrielle FreeCAD App::Link :
    - Partage zéro-copie du solide maître unique en mémoire vive
    - Cache paresseux mémoïsé (lazy evaluation) des solides transformés
    - Extraction matricielle par lot (N, 4, 4) pour rendu GPU instancié
    - Calcul du ratio d'économie de mémoire
    """
    import numpy as np
    from src.core.assembly import AssemblyLink, AssemblyLinkManager

    master_bolt = make_box(5.0, 5.0, 20.0)
    link_mgr = AssemblyLinkManager()
    link_mgr.register_master_solid("bolt_m5", master_bolt)

    # Création de 10 instances liées
    num_instances = 10
    for i in range(num_instances):
        t_mat = np.eye(4, dtype=np.float64)
        t_mat[0, 3] = float(i * 15.0)  # Décalage en X
        link = link_mgr.create_link(f"bolt_inst_{i}", "bolt_m5", placement_matrix=t_mat)
        # Vérification zéro-copie : pointe exactement sur le même objet Python
        assert link.solid is master_bolt

    assert len(link_mgr.links) == 10
    assert pytest.approx(link_mgr.calculate_memory_savings_ratio(), 1e-4) == 10.0

    # Vérification extraction de matrices GPU (10, 4, 4)
    gpu_matrices = link_mgr.get_instance_matrices_for_master("bolt_m5")
    assert gpu_matrices.shape == (10, 4, 4)
    assert gpu_matrices[3, 0, 3] == 45.0  # 3 * 15.0

    # Vérification du cache paresseux
    link_0 = link_mgr.links["bolt_inst_0"]
    # Matrice identité au début pour test de lazy cache
    link_0.set_transform(np.eye(4, dtype=np.float64))
    assert link_0.get_transformed_solid() is master_bolt

    new_mat = np.eye(4, dtype=np.float64)
    new_mat[2, 3] = 100.0
    link_0.set_transform(new_mat)
    transformed_1 = link_0.get_transformed_solid()
    assert transformed_1 is not master_bolt
    assert pytest.approx(transformed_1.volume(), 1e-3) == master_bolt.volume()

    # Second appel : doit retourner l'instance en cache sans re-calcul
    transformed_2 = link_0.get_transformed_solid()
    assert transformed_1 is transformed_2


