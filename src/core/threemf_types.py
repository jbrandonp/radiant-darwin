"""
Types et structures de données pour le format 3MF (3D Manufacturing Format).
Définit les composants du Beam Lattice Extension et les spécifications de fabrication additive.
Conforme aux standards de typage statique strict (Zero Any).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional
import numpy as np

from src.core.types import Vector3D, ColorRGBA


class BeamCapMode(str, Enum):
    """Modes de calotte d'extrémité pour les poutres réticulaires (3MF Beam Lattice)."""
    SPHERE = "sphere"
    HEMISPHERE = "hemisphere"
    BUTT = "butt"


class BeamBallMode(str, Enum):
    """Modes de gestion des rotules sphériques aux nœuds."""
    NONE = "none"
    MIXED = "mixed"
    ALL = "all"


@dataclass
class LatticeBeam:
    """Poutre unitaire reliant deux nœuds dans un treillis 3D."""
    node_idx_1: int
    node_idx_2: int
    radius_1: float
    radius_2: float
    cap_mode: BeamCapMode = BeamCapMode.SPHERE
    tag: str = ""


@dataclass
class LatticeBall:
    """Rotule sphérique unitaire positionnée sur un nœud de treillis."""
    node_idx: int
    radius: float


@dataclass
class BeamLatticeTopology:
    """Topologie réticulaire complète (graphe de nœuds et poutres)."""
    nodes: List[Vector3D] = field(default_factory=list)
    beams: List[LatticeBeam] = field(default_factory=list)
    balls: List[LatticeBall] = field(default_factory=list)
    min_length: float = 0.001
    ball_mode: BeamBallMode = BeamBallMode.NONE

    def add_node(self, x: float, y: float, z: float) -> int:
        """Ajoute un nœud au treillis et retourne son indice."""
        idx = len(self.nodes)
        self.nodes.append(Vector3D(float(x), float(y), float(z)))
        return idx

    def add_beam(
        self,
        node_1: int,
        node_2: int,
        radius: float,
        cap_mode: BeamCapMode = BeamCapMode.SPHERE
    ) -> int:
        """Ajoute une poutre cylindrique d'épaisseur constante."""
        idx = len(self.beams)
        self.beams.append(LatticeBeam(
            node_idx_1=node_1,
            node_idx_2=node_2,
            radius_1=float(radius),
            radius_2=float(radius),
            cap_mode=cap_mode
        ))
        return idx

    def is_empty(self) -> bool:
        """Vérifie si le treillis ne comporte aucune poutre."""
        return len(self.beams) == 0


@dataclass
class ThreeMFMaterial:
    """Propriétés de matériau pour l'impression 3D."""
    name: str = "Default_Polyamide_PA12"
    color: ColorRGBA = field(default_factory=ColorRGBA)
    density_g_cm3: float = 1.01
    tensile_strength_mpa: float = 48.0
