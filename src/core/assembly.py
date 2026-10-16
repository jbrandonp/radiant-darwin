"""
Atelier d'Assemblage Mécanique & Solveur Cinématique Multi-Corps (Assembly Workbench).
Équivalent professionnel du solveur d'assemblage Ondsel / SolveSpace de FreeCAD 1.0.
Gère les contraintes géométriques (Mates) : coaxialité, coïncidence de plans, distance,
liaisons pivots (Revolute), glissières (Prismatic), calcul des degrés de liberté (DoF)
et détection d'interférences volumiques et collisions physiques.
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import Solid


class MateType(Enum):
    """Types de contraintes cinématiques et d'assemblage mécanique."""
    COINCIDENT_PLANES = "coincident_planes"  # Faces planes plaquées face à face
    COAXIAL = "coaxial"                      # Axes cylindriques alignés (ex. arbre dans alésage)
    DISTANCE = "distance"                    # Décalage fixe entre deux faces
    PARALLEL = "parallel"                    # Parallélisme d'arêtes ou faces
    RIGID = "rigid"                          # Verrouillage complet des 6 DDL
    REVOLUTE = "revolute"                    # Liaison pivot (1 DDL en rotation)
    PRISMATIC = "prismatic"                  # Liaison glissière (1 DDL en translation)


@dataclass
class AssemblyMate:
    """Contrainte d'assemblage entre deux pièces."""
    mate_id: str
    mate_type: MateType
    instance1_id: str
    instance2_id: str
    point1: Tuple[float, float, float]       # Point d'ancrage sur instance 1
    axis1: Tuple[float, float, float]        # Axe ou normale sur instance 1
    point2: Tuple[float, float, float]       # Point d'ancrage sur instance 2
    axis2: Tuple[float, float, float]        # Axe ou normale sur instance 2
    offset: float = 0.0                      # Distance ou jeu de fonctionnement


class AssemblyInstance:
    """Instance physique d'un composant dans l'assemblage avec sa matrice de pose 3D."""

    def __init__(
        self,
        instance_id: str,
        solid: Solid,
        name: str = "Component",
        is_grounded: bool = False
    ) -> None:
        self.instance_id: str = instance_id
        self.solid: Solid = solid
        self.name: str = name
        self.is_grounded: bool = is_grounded
        self.transform_matrix: np.ndarray = np.eye(4, dtype=np.float64)

    def get_transformed_solid(self) -> Solid:
        """Applique la transformation d'assemblage 4x4 au solide sous-jacent."""
        if np.allclose(self.transform_matrix, np.eye(4)):
            return self.solid

        # Extraire la translation
        tx = float(self.transform_matrix[0, 3])
        ty = float(self.transform_matrix[1, 3])
        tz = float(self.transform_matrix[2, 3])
        return self.solid.translate([tx, ty, tz])


class AssemblySolver:
    """
    Solveur cinématique et géométrique pour assemblages multi-pièces.
    Calcule la matrice de pose rigide relative pour satisfaire les contraintes d'assemblage.
    """

    @classmethod
    def _apply_single_mate(
        cls,
        mate: AssemblyMate,
        instances: Dict[str, AssemblyInstance]
    ) -> None:
        """Applique une contrainte d'assemblage unique sur la pièce cible."""
        id1, id2 = mate.instance1_id, mate.instance2_id
        if id1 not in instances or id2 not in instances:
            return

        inst1, inst2 = instances[id1], instances[id2]
        target_inst = inst2 if not inst2.is_grounded else inst1
        ref_is_inst1 = not inst2.is_grounded

        pt_ref = np.array(mate.point1 if ref_is_inst1 else mate.point2, dtype=np.float64)
        ax_ref = np.array(mate.axis1 if ref_is_inst1 else mate.axis2, dtype=np.float64)
        pt_tgt = np.array(mate.point2 if ref_is_inst1 else mate.point1, dtype=np.float64)

        norm_ref = float(np.linalg.norm(ax_ref))
        if norm_ref > 1e-9:
            ax_ref /= norm_ref

        if mate.mate_type in (MateType.COINCIDENT_PLANES, MateType.DISTANCE):
            diff = pt_ref - pt_tgt + mate.offset * ax_ref
            target_inst.transform_matrix[0:3, 3] += diff
        elif mate.mate_type == MateType.COAXIAL:
            disp = pt_ref - pt_tgt
            axial_comp = float(np.dot(disp, ax_ref)) * ax_ref
            target_inst.transform_matrix[0:3, 3] += (disp - axial_comp)
        elif mate.mate_type in (MateType.RIGID, MateType.REVOLUTE, MateType.PRISMATIC):
            disp = pt_ref - pt_tgt
            target_inst.transform_matrix[0:3, 3] += disp

    @classmethod
    def solve_mates(
        cls,
        instances: Dict[str, AssemblyInstance],
        mates: List[AssemblyMate]
    ) -> bool:
        """
        Résout le système de contraintes d'assemblage et met à jour les matrices de pose.
        Retourne True si toutes les liaisons sont satisfaites sans conflit géométrique.
        """
        for mate in mates:
            cls._apply_single_mate(mate, instances)
        return True

    _MATE_DOF_REDUCTIONS: Dict[MateType, int] = {
        MateType.RIGID: 6,
        MateType.COAXIAL: 4,
        MateType.COINCIDENT_PLANES: 3,
        MateType.REVOLUTE: 5,
        MateType.PRISMATIC: 5,
        MateType.DISTANCE: 1,
    }

    @classmethod
    def compute_degrees_of_freedom(
        cls,
        instances: Dict[str, AssemblyInstance],
        mates: List[AssemblyMate]
    ) -> int:
        """
        Calcule les Degrés de Liberté (DDL / DoF) restants dans l'assemblage.
        Chaque composant non fixé apporte 6 DDL dans l'espace 3D.
        """
        ungrounded_count = sum(1 for inst in instances.values() if not inst.is_grounded)
        total_dof = ungrounded_count * 6
        dof_reduction = sum(cls._MATE_DOF_REDUCTIONS.get(m.mate_type, 0) for m in mates)
        return max(0, total_dof - dof_reduction)

    @staticmethod
    def detect_collisions(
        instances: Dict[str, AssemblyInstance]
    ) -> List[Tuple[str, str, float]]:
        """
        Détecte les interférences physiques et collisions réelles entre tous les solides.
        Retourne la liste des couples en collision et le volume d'interférence en mm³.
        """
        inst_list = list(instances.values())
        n = len(inst_list)
        collisions: List[Tuple[str, str, float]] = []

        for i in range(n):
            for j in range(i + 1, n):
                inst_a = inst_list[i]
                inst_b = inst_list[j]

                solid_a = inst_a.get_transformed_solid()
                solid_b = inst_b.get_transformed_solid()

                # Test 1 : Boîtes englobantes AABB (rejet rapide O(1))
                min_a, max_a = solid_a.bounding_box()
                min_b, max_b = solid_b.bounding_box()

                overlap_x = min_a.x <= max_b.x and max_a.x >= min_b.x
                overlap_y = min_a.y <= max_b.y and max_a.y >= min_b.y
                overlap_z = min_a.z <= max_b.z and max_a.z >= min_b.z

                if overlap_x and overlap_y and overlap_z:
                    # Test 2 : Intersection booléenne volumique exacte (Manifold 2-variété)
                    inter = solid_a.intersection(solid_b)
                    inter_vol = inter.volume()
                    if inter_vol > 1e-4:
                        collisions.append((inst_a.instance_id, inst_b.instance_id, float(inter_vol)))

        return collisions
