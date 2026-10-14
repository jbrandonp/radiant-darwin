"""
Passerelle ECAD / MCAD & Intégration de Circuits Imprimés (KiCadStepUp Parity).
Permet de concevoir des cartes électroniques (PCB) multi-couches avec composants 3D (CMS/SMD),
et de vérifier les collisions et jeux mécaniques avec les boîtiers électroniques.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np

from src.core.nexus_kernel.hybrid_solid import NexusSolid


@dataclass
class PCBComponent3D:
    """Composant électronique monté sur la carte (CMS / Traversant)."""
    designator: str = "U1"
    ref_des: str = ""
    package: str = "QFP"
    pos_x: float = 0.0
    pos_y: float = 0.0
    height_z: float = 2.0
    width_x: float = 5.0
    length_y: float = 5.0
    pos_x_mm: float = 0.0
    pos_y_mm: float = 0.0
    width_mm: float = 5.0
    length_mm: float = 5.0
    height_mm: float = 2.0
    rotation_deg: float = 0.0

    def __post_init__(self) -> None:
        if not self.ref_des:
            self.ref_des = self.designator
        if not self.designator:
            self.designator = self.ref_des

        if self.pos_x != 0.0 and self.pos_x_mm == 0.0:
            self.pos_x_mm = self.pos_x
        if self.pos_y != 0.0 and self.pos_y_mm == 0.0:
            self.pos_y_mm = self.pos_y
        if self.width_x != 5.0 and self.width_mm == 5.0:
            self.width_mm = self.width_x
        if self.length_y != 5.0 and self.length_mm == 5.0:
            self.length_mm = self.length_y
        if self.height_z != 2.0 and self.height_mm == 2.0:
            self.height_mm = self.height_z


class PCBBoard:
    """Carte de circuit imprimé (PCB) paramétrique avec composants et perçages."""

    def __init__(
        self,
        name: str = "Board",
        board_id: Optional[str] = None,
        width: float = 100.0,
        height: float = 80.0,
        thickness: float = 1.6,
        width_mm: Optional[float] = None,
        height_mm: Optional[float] = None,
        thickness_mm: Optional[float] = None,
        layer_count: int = 4,
        components: Optional[List[PCBComponent3D]] = None
    ) -> None:
        self.board_id: str = board_id or name
        self.name: str = self.board_id
        self.width_mm: float = float(width_mm if width_mm is not None else width)
        self.height_mm: float = float(height_mm if height_mm is not None else height)
        self.thickness_mm: float = float(thickness_mm if thickness_mm is not None else thickness)
        self.layer_count: int = int(layer_count)
        self.components: List[PCBComponent3D] = components or []

    def add_component(self, comp: PCBComponent3D) -> None:
        """Ajoute un composant électronique sur la face supérieure de la carte."""
        self.components.append(comp)

    def generate_3d_assembly(self) -> NexusSolid:
        """Génère l'assemblage solide volumique étanche de la carte et ses composants."""
        return self.to_solid()

    def to_solid(self) -> NexusSolid:
        """Génère le solide volumique de la carte assemblée avec ses composants."""
        board_solid = NexusSolid.make_box(
            self.width_mm, self.height_mm, self.thickness_mm,
            name=f"Substrate_{self.board_id}"
        )

        for comp in self.components:
            comp_box = NexusSolid.make_box(
                comp.width_mm, comp.length_mm, comp.height_mm,
                name=f"Comp_{comp.ref_des}"
            )
            m_comp = comp_box.internal_manifold.translate([
                comp.pos_x_mm, comp.pos_y_mm, self.thickness_mm
            ])
            comp_solid = NexusSolid(name=f"Comp_{comp.ref_des}", internal_manifold=m_comp)
            board_solid = board_solid.union(comp_solid)

        return board_solid

    def check_enclosure_clearance(
        self,
        enclosure_solid: NexusSolid,
        min_clearance_mm: float = 2.0
    ) -> List[Tuple[str, float]]:
        """
        Vérifie les interférences et jeux d'espacement minimaux entre les composants
        électroniques les plus hauts et le capot du boîtier mécanique.
        """
        conflicts: List[Tuple[str, float]] = []
        enc_min, enc_max = enclosure_solid.bounding_box()
        ceiling_z = enc_max[2]

        for comp in self.components:
            top_z = self.thickness_mm + comp.height_mm
            clearance = ceiling_z - top_z
            if clearance < min_clearance_mm:
                conflicts.append((comp.ref_des, float(clearance)))

        return conflicts


def verify_enclosure_clearance(
    board: PCBBoard,
    enclosure_max_internal_height: float
) -> bool:
    """
    Vérifie si tous les composants de la carte s'insèrent dans la hauteur interne maximale du boîtier.
    Retourne True si aucun composant ne dépasse, False en cas de collision.
    """
    for comp in board.components:
        # Hauteur totale au-dessus du plan d'appui inférieur du PCB
        top_elevation = board.thickness_mm + comp.height_mm
        if top_elevation > enclosure_max_internal_height:
            return False
    return True
