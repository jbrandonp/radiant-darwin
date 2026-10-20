"""
Package unifié d'Assemblage, Liaisons Mécaniques et Cinématique Industrielle (CAD Studio Assembly Layer).
Regroupe et expose l'ensemble des capacités d'assemblage, de détection d'interférences
et de résolution cinématique (boucles ouvertes et fermées).

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

# 1. Gestionnaire d'assemblage et détection d'interférences
from src.assembly.assembly_manager import (
    JointType,
    MechanicalJoint,
    InterferenceResult,
    AssemblyManager,
)

# 2. Modèle d'assemblage hiérarchique, contraintes (Mates) et solveur d'assemblage
from src.core.assembly import (
    MateType,
    AssemblyMate,
    AssemblyInstance,
    AssemblySolver,
    AssemblyLink,
    AssemblyLinkManager,
)

# 3. Liaisons cinématiques de transmission (engrenages, crémaillères, rotules) et vue éclatée
from src.core.assembly_kinematics import (
    TransmissionSense,
    GearMate,
    RackPinionMate,
    ScrewMate,
    BallJointMate,
    ExplodedStep,
    ExplodedViewGenerator,
)

# 4. Liaisons cinématiques de type Fusion 360 et solveur de joints
from src.core.joint_solver import (
    FusionJointType,
    JointLimit,
    JointAnchor,
    AssemblyJoint,
    JointKinematicSolver,
)

# 5. Résolveur cinématique en boucle fermée
from src.core.nexus_kernel.closed_loop_kinematics import (
    ClosedLoopDynamicsResult,
    ClosedLoopKinematicEngine,
)

# Alias ergonomiques
ExplodedViewStep = ExplodedStep
ExplodedViewEngine = ExplodedViewGenerator
ClosedLoopKinematicSolver = ClosedLoopKinematicEngine

__all__ = [
    # Gestionnaire & Interférences
    "JointType",
    "MechanicalJoint",
    "InterferenceResult",
    "AssemblyManager",
    # Modèle CAO, Mates & Solveur
    "MateType",
    "AssemblyMate",
    "AssemblyInstance",
    "AssemblySolver",
    "AssemblyLink",
    "AssemblyLinkManager",
    # Cinématique de transmission & Vue éclatée
    "TransmissionSense",
    "GearMate",
    "RackPinionMate",
    "ScrewMate",
    "BallJointMate",
    "ExplodedStep",
    "ExplodedViewGenerator",
    "ExplodedViewStep",
    "ExplodedViewEngine",
    # Joints Fusion
    "FusionJointType",
    "JointLimit",
    "JointAnchor",
    "AssemblyJoint",
    "JointKinematicSolver",
    # Boucle fermée
    "ClosedLoopDynamicsResult",
    "ClosedLoopKinematicEngine",
    "ClosedLoopKinematicSolver",
]
