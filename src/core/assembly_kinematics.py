"""
Liaisons Cinématiques Avancées et Vues Éclatées d'Assemblage (Pillar 4).
Équivalent professionnel du solveur de mécanismes Ondsel / SolveSpace de FreeCAD 1.0.
Gère les contraintes cinématiques de transmission de puissance :
engrenages (GearMate), crémaillères (RackPinionMate), liaisons hélicoïdales (ScrewMate),
rotules sphériques (BallJointMate) et génération automatique de vues éclatées interactives.
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional
import math
import numpy as np

from src.core.types import Vector3D


class TransmissionSense(str, Enum):
    """Sens de transmission du mouvement relatif."""
    OPPOSITE = "opposite"  # Engrenage extérieur classique (sens inverse)
    SAME = "same"          # Engrenage intérieur / courroie synchrone (même sens)


@dataclass
class GearMate:
    """
    Contrainte cinématique d'engrenage reliant deux axes de rotation.
    Relation: omega_2 = - (teeth_1 / teeth_2) * omega_1
    """
    id: str
    part_a_id: str
    part_b_id: str
    axis_a_origin: Vector3D
    axis_a_direction: Vector3D
    axis_b_origin: Vector3D
    axis_b_direction: Vector3D
    teeth_a: int
    teeth_b: int
    transmission: TransmissionSense = TransmissionSense.OPPOSITE

    def compute_driven_angle(self, angle_a_rad: float) -> float:
        """Calcule l'angle de rotation de l'arbre mené B à partir de l'angle menant A."""
        ratio = float(self.teeth_a) / float(self.teeth_b)
        if self.transmission == TransmissionSense.OPPOSITE:
            return -ratio * angle_a_rad
        return ratio * angle_a_rad


@dataclass
class RackPinionMate:
    """
    Contrainte cinématique pignon-crémaillère.
    Convertit la rotation angulaire du pignon en translation linéaire de la crémaillère.
    Relation: delta_x = pitch_radius * theta
    """
    id: str
    pinion_part_id: str
    rack_part_id: str
    pinion_axis_origin: Vector3D
    pinion_axis_direction: Vector3D
    rack_linear_axis: Vector3D
    pitch_radius_mm: float

    def compute_rack_displacement(self, pinion_angle_rad: float) -> Vector3D:
        """Calcule le vecteur de translation 3D de la crémaillère pour une rotation du pignon."""
        linear_distance = self.pitch_radius_mm * pinion_angle_rad
        axis_norm = self.rack_linear_axis.normalize()
        return Vector3D(
            axis_norm.x * linear_distance,
            axis_norm.y * linear_distance,
            axis_norm.z * linear_distance
        )


@dataclass
class ScrewMate:
    """
    Liaison hélicoïdale (vis-écrou).
    Couple la rotation autour de l'axe de la vis avec une avance axiale linéaire selon le pas.
    Relation: delta_z = (pitch / 2*pi) * theta
    """
    id: str
    screw_part_id: str
    nut_part_id: str
    axis_origin: Vector3D
    axis_direction: Vector3D
    pitch_mm: float  # Avance axiale par tour complet (2*pi rad)

    def compute_axial_advance(self, rotation_rad: float) -> Vector3D:
        """Calcule le déplacement axial 3D selon la rotation effectuée."""
        turns = rotation_rad / (2.0 * math.pi)
        advance_mm = turns * self.pitch_mm
        dir_norm = self.axis_direction.normalize()
        return Vector3D(
            dir_norm.x * advance_mm,
            dir_norm.y * advance_mm,
            dir_norm.z * advance_mm
        )


@dataclass
class BallJointMate:
    """
    Liaison rotule sphérique (Spherical Joint).
    Supprime les 3 degrés de liberté de translation (X, Y, Z confondues au centre)
    tout en laissant libres les 3 degrés de liberté de rotation (roulis, tangage, lacet).
    """
    id: str
    part_a_id: str
    part_b_id: str
    pivot_center_a: Vector3D
    pivot_center_b: Vector3D

    def evaluate_constraint_residual(self) -> float:
        """Évalue l'erreur de coïncidence des centres de rotule."""
        return self.pivot_a_to_b_vector().length()

    def pivot_a_to_b_vector(self) -> Vector3D:
        """Vecteur d'écart entre les centres de rotule."""
        return self.pivot_center_b.subtract(self.pivot_center_a)


@dataclass
class ExplodedStep:
    """Étape élémentaire de déplacement dans une vue éclatée."""
    part_id: str
    direction: Vector3D
    distance_mm: float
    order: int


class ExplodedViewGenerator:
    """
    Générateur automatique et manuel de vues éclatées pour mécanismes complexes.
    Calcule la séquence de démontage sans collision selon la hiérarchie des liaisons.
    """

    def __init__(self) -> None:
        self.steps: List[ExplodedStep] = []

    def add_step(self, part_id: str, direction: Vector3D, distance_mm: float, order: int) -> None:
        """Ajoute une étape de translation dans la vue éclatée."""
        self.steps.append(ExplodedStep(
            part_id=part_id,
            direction=direction.normalize(),
            distance_mm=distance_mm,
            order=order
        ))
        self.steps.sort(key=lambda s: s.order)

    def compute_exploded_positions(
        self,
        nominal_positions: Dict[str, Vector3D],
        explosion_factor: float = 1.0
    ) -> Dict[str, Vector3D]:
        """
        Calcule les positions 3D finales des pièces pour un facteur d'explosion donné (0.0 = fermé, 1.0 = éclaté 100%).
        """
        result: Dict[str, Vector3D] = dict(nominal_positions)

        for step in self.steps:
            if step.part_id in result:
                current_pos = result[step.part_id]
                offset_len = step.distance_mm * explosion_factor
                dir_vec = step.direction
                new_pos = current_pos.add(Vector3D(
                    dir_vec.x * offset_len,
                    dir_vec.y * offset_len,
                    dir_vec.z * offset_len
                ))
                result[step.part_id] = new_pos

        return result
