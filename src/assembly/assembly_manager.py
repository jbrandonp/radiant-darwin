"""
Moteur d'assemblage mécanique et détection d'interférences (Assembly & Collision Detection).
Gère les liaisons cinématiques (Rigide, Pivot, Glissière) et calcule les collisions physiques entre composants.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from src.core.types import Vector3D
from src.core.geometry import Solid


class JointType(Enum):
    """Types de liaisons cinématiques mécaniques normalisées."""
    RIGID = "rigid"              # Encastrement (0 DDL)
    REVOLUTE = "revolute"        # Pivot (1 DDL rotation)
    SLIDER = "slider"            # Glissière (1 DDL translation)
    CYLINDRICAL = "cylindrical"  # Pivot-glissant (2 DDL)
    BALL = "ball"                # Rotule (3 DDL rotation)


@dataclass
class MechanicalJoint:
    """Liaison cinématique reliant deux composants de l'assemblage."""
    joint_id: str
    name: str
    joint_type: JointType
    parent_body_id: str
    child_body_id: str
    axis: Vector3D = field(default_factory=lambda: Vector3D(0.0, 0.0, 1.0))
    current_value: float = 0.0  # Angle (deg) ou Déplacement (mm)
    min_limit: Optional[float] = None
    max_limit: Optional[float] = None


@dataclass
class InterferenceResult:
    """Résultat de détection d'interférence entre deux pièces."""
    body_a_id: str
    body_b_id: str
    has_collision: bool
    overlap_volume_mm3: float


class AssemblyManager:
    """
    Gestionnaire d'assemblage multi-composants et contrôleur cinématique.
    """

    def __init__(self) -> None:
        """Initialise le gestionnaire avec un registre de liaisons vide."""
        self.joints: Dict[str, MechanicalJoint] = {}

    def add_joint(
        self,
        joint_id: str,
        name: str,
        joint_type: JointType,
        parent_id: str,
        child_id: str,
        axis: Vector3D = Vector3D(0.0, 0.0, 1.0)
    ) -> MechanicalJoint:
        """Enregistre une nouvelle liaison cinématique."""
        j = MechanicalJoint(
            joint_id=joint_id,
            name=name,
            joint_type=joint_type,
            parent_body_id=parent_id,
            child_body_id=child_id,
            axis=axis
        )
        self.joints[joint_id] = j
        return j

    def animate_joint(
        self,
        joint_id: str,
        bodies: Dict[str, Solid],
        new_value: float
    ) -> Dict[str, Solid]:
        """
        Déplace le composant enfant selon la cinématique de la liaison.
        Retourne la liste des solides avec la nouvelle position du composant enfant.
        """
        if joint_id not in self.joints:
            return dict(bodies)

        joint = self.joints[joint_id]
        child_id = joint.child_body_id
        if child_id not in bodies:
            return dict(bodies)

        updated = dict(bodies)
        child_solid = updated[child_id]
        val = new_value
        if joint.min_limit is not None:
            val = max(joint.min_limit, val)
        if joint.max_limit is not None:
            val = min(joint.max_limit, val)
        delta = val - joint.current_value
        joint.current_value = val

        if joint.joint_type in (JointType.REVOLUTE, JointType.CYLINDRICAL):
            # Rotation autour de l'axe spécifié (avec prise en compte du signe de l'axe)
            if abs(joint.axis.z) > 0.5:
                sign = 1.0 if joint.axis.z > 0 else -1.0
                transformed = child_solid.rotate(0.0, 0.0, delta * sign)
            elif abs(joint.axis.x) > 0.5:
                sign = 1.0 if joint.axis.x > 0 else -1.0
                transformed = child_solid.rotate(delta * sign, 0.0, 0.0)
            else:
                sign = 1.0 if joint.axis.y > 0 else -1.0
                transformed = child_solid.rotate(0.0, delta * sign, 0.0)
            updated[child_id] = transformed

        elif joint.joint_type == JointType.SLIDER:
            # Translation le long de l'axe spécifié
            offset = joint.axis.normalized().scale(delta)
            updated[child_id] = child_solid.translate(offset)

        return updated

    @staticmethod
    def check_interference(solid_a: Solid, solid_b: Solid, id_a: str = "A", id_b: str = "B") -> InterferenceResult:
        """
        Calcule l'interférence exacte entre deux corps via intersection booléenne CSG.
        Si le volume d'intersection > 1e-4 mm³, il y a collision physique.
        """
        if solid_a.is_empty() or solid_b.is_empty():
            return InterferenceResult(id_a, id_b, False, 0.0)

        # Vérification préliminaire rapide par AABB (Boîtes englobantes)
        min_a, max_a = solid_a.bounding_box()
        min_b, max_b = solid_b.bounding_box()

        # Si les boîtes ne se chevauchent pas, aucune collision possible (O(1))
        if (max_a.x < min_b.x or min_a.x > max_b.x or
            max_a.y < min_b.y or min_a.y > max_b.y or
            max_a.z < min_b.z or min_a.z > max_b.z):
            return InterferenceResult(id_a, id_b, False, 0.0)

        # Calcul exact d'intersection volumique
        intersection_solid = solid_a.intersection(solid_b)
        overlap_vol = intersection_solid.volume()
        has_col = bool(overlap_vol > 1e-3)

        return InterferenceResult(id_a, id_b, has_col, overlap_vol)
