"""
Types fondamentaux et structures de données pour le moteur de CAO paramétrique.
Définit les vecteurs, maillages, plans de travail et statuts de fonctionnalités.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple, Optional
import numpy as np


class PlaneType(Enum):
    """Types de plans cartésiens et de référence pour les esquisses."""
    XY = "XY"
    XZ = "XZ"
    YZ = "YZ"
    CUSTOM = "CUSTOM"


class BooleanOperation(Enum):
    """Opérations booléennes volumiques inspirées d'Autodesk Fusion 360."""
    NEW_BODY = "new_body"       # Crée un nouveau corps indépendant
    JOIN = "join"               # Union booléenne (fusionne avec le corps existant)
    CUT = "cut"                 # Différence booléenne (soustrait de la matière)
    INTERSECT = "intersect"     # Intersection booléenne (conserve le volume commun)


class FeatureStatus(Enum):
    """Statut d'évaluation d'une fonctionnalité dans l'arbre d'historique."""
    OK = auto()
    ERROR = auto()
    OUTDATED = auto()
    SUPPRESSED = auto()


@dataclass(frozen=True)
class Vector3D:
    """
    Représente un vecteur ou un point dans l'espace tridimensionnel (X, Y, Z).
    Fournit les opérations vectorielles mathématiques courantes.
    """
    x: float
    y: float
    z: float

    def to_array(self) -> np.ndarray:
        """Convertit le vecteur en tableau NumPy 1D de float64."""
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    def add(self, other: Vector3D) -> Vector3D:
        """Additionne deux vecteurs 3D."""
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def subtract(self, other: Vector3D) -> Vector3D:
        """Soustrait un vecteur 3D d'un autre."""
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def scale(self, factor: float) -> Vector3D:
        """Multiplie le vecteur par un scalaire."""
        return Vector3D(self.x * factor, self.y * factor, self.z * factor)

    def length(self) -> float:
        """Calcule la norme euclidienne du vecteur."""
        return float(np.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2))

    def normalized(self) -> Vector3D:
        """Retourne le vecteur unitaire colinéaire."""
        dist = self.length()
        if dist < 1e-9:
            return Vector3D(0.0, 0.0, 0.0)
        return Vector3D(self.x / dist, self.y / dist, self.z / dist)

    def normalize(self) -> Vector3D:
        """Alias retournant le vecteur unitaire colinéaire."""
        return self.normalized()

    def dot(self, other: Vector3D) -> float:
        """Calcule le produit scalaire entre deux vecteurs."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector3D) -> Vector3D:
        """Calcule le produit vectoriel entre deux vecteurs."""
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )


@dataclass(frozen=True)
class Point2D:
    """Point 2D sur un plan d'esquisse paramétrique."""
    u: float
    v: float

    @property
    def x(self) -> float:
        """Alias cartésien X pour la coordonnée U."""
        return self.u

    @property
    def y(self) -> float:
        """Alias cartésien Y pour la coordonnée V."""
        return self.v

    def to_array(self) -> np.ndarray:
        """Convertit le point 2D en tableau NumPy."""
        return np.array([self.u, self.v], dtype=np.float64)

    def distance_to(self, other: Point2D) -> float:
        """Calcule la distance euclidienne vers un autre point 2D."""
        return float(np.hypot(self.u - other.u, self.v - other.v))


@dataclass(frozen=True)
class ColorRGBA:
    """Couleur RGBA normalisée [0.0 - 1.0]."""
    r: float = 0.8
    g: float = 0.8
    b: float = 0.8
    a: float = 1.0


@dataclass
class MeshBuffer:
    """
    Conteneur de géométrie 3D pour l'affichage OpenGL et l'exportation.
    Contient les sommets, triangles, normales et arêtes topologiques.
    """
    vertices: np.ndarray      # Shape: (N, 3), dtype=float32
    faces: np.ndarray         # Shape: (M, 3), dtype=uint32
    normals: np.ndarray       # Shape: (N, 3), dtype=float32
    edges: np.ndarray         # Shape: (K, 2), dtype=uint32 (pour le contour style CAD)
    color: ColorRGBA = field(default_factory=ColorRGBA)
    edge_vertices: Optional[np.ndarray] = None  # Shape: (2K, 3), sommets 3D des lignes d'arêtes
    vertex_colors: Optional[np.ndarray] = None  # Shape: (N, 4), dtype=float32 (couleurs par sommet ex. FEA)

    def is_empty(self) -> bool:
        """Vérifie si le maillage ne contient aucune géométrie."""
        return len(self.vertices) == 0 or len(self.faces) == 0

    @classmethod
    def empty(cls) -> MeshBuffer:
        """Génère un maillage vide sécurisé."""
        return cls(
            vertices=np.zeros((0, 3), dtype=np.float32),
            faces=np.zeros((0, 3), dtype=np.uint32),
            normals=np.zeros((0, 3), dtype=np.float32),
            edges=np.zeros((0, 2), dtype=np.uint32),
            edge_vertices=np.zeros((0, 3), dtype=np.float32)
        )
