"""
Moteur d'esquisse 2D (Sketcher) paramétrique.
Permet de tracer des profils géométriques 2D fermés sur des plans cartésiens
afin de servir de base aux opérations d'extrusion et de révolution 3D.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
import numpy as np

from src.core.types import Point2D, PlaneType, Vector3D


class EntityType(Enum):
    """Type d'élément géométrique dans l'esquisse 2D."""
    LINE = "line"
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    POLYGON = "polygon"


@dataclass
class SketchEntity:
    """Classe de base pour une entité d'esquisse."""
    entity_id: str
    entity_type: EntityType

    def get_points(self) -> List[Point2D]:
        """Retourne la liste des points ordonnés constituant l'entité."""
        raise NotImplementedError


@dataclass
class SketchRectangle(SketchEntity):
    """Rectangle 2D défini par son coin inférieur gauche et ses dimensions."""
    origin: Point2D
    width: float
    height: float

    def __init__(self, entity_id: str, origin: Point2D, width: float, height: float) -> None:
        super().__init__(entity_id, EntityType.RECTANGLE)
        self.origin = origin
        self.width = width
        self.height = height

    def get_points(self) -> List[Point2D]:
        """Retourne les 4 sommets ordonnés dans le sens trigonométrique."""
        u0, v0 = self.origin.u, self.origin.v
        w, h = self.width, self.height
        return [
            Point2D(u0, v0),
            Point2D(u0 + w, v0),
            Point2D(u0 + w, v0 + h),
            Point2D(u0, v0 + h),
        ]


@dataclass
class SketchCircle(SketchEntity):
    """Cercle 2D discrétisé en polygone régulier pour l'extrusion."""
    center: Point2D
    radius: float
    segments: int = 36

    def __init__(self, entity_id: str, center: Point2D, radius: float, segments: int = 36) -> None:
        super().__init__(entity_id, EntityType.CIRCLE)
        self.center = center
        self.radius = radius
        self.segments = max(12, segments)

    def get_points(self) -> List[Point2D]:
        """Génère les sommets du contour circulaire discret."""
        pts: List[Point2D] = []
        angles = np.linspace(0.0, 2.0 * np.pi, self.segments, endpoint=False)
        for theta in angles:
            u = self.center.u + self.radius * float(np.cos(theta))
            v = self.center.v + self.radius * float(np.sin(theta))
            pts.append(Point2D(u, v))
        return pts


@dataclass
class SketchPolygon(SketchEntity):
    """Polygone 2D libre défini par une suite de sommets ordonnés."""
    points: List[Point2D]

    def __init__(self, entity_id: str, points: List[Point2D]) -> None:
        super().__init__(entity_id, EntityType.POLYGON)
        self.points = points

    def get_points(self) -> List[Point2D]:
        """Retourne la séquence des points du polygone."""
        return self.points


class Sketch2D:
    """
    Conteneur d'esquisse 2D positionnée sur un plan de référence.
    Permet d'ajouter des formes et d'extraire des profils pour la CAO 3D.
    """

    def __init__(self, sketch_id: str, name: str = "Sketch", plane: PlaneType = PlaneType.XY) -> None:
        """Initialise une nouvelle esquisse sur le plan indiqué."""
        self.sketch_id: str = sketch_id
        self.name: str = name
        self.plane: PlaneType = plane
        self.entities: List[SketchEntity] = []
        self._counter: int = 0

    def add_rectangle(self, origin: Point2D, width: float, height: float) -> SketchRectangle:
        """Ajoute un rectangle paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"rect_{self._counter}"
        rect = SketchRectangle(entity_id, origin, width, height)
        self.entities.append(rect)
        return rect

    def add_circle(self, center: Point2D, radius: float, segments: int = 36) -> SketchCircle:
        """Ajoute un cercle paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"circle_{self._counter}"
        circle = SketchCircle(entity_id, center, radius, segments)
        self.entities.append(circle)
        return circle

    def add_polygon(self, points: List[Point2D]) -> SketchPolygon:
        """Ajoute un polygone libre à l'esquisse."""
        self._counter += 1
        entity_id = f"poly_{self._counter}"
        poly = SketchPolygon(entity_id, points)
        self.entities.append(poly)
        return poly

    def get_primary_profile(self) -> Optional[List[Point2D]]:
        """
        Extrait le premier profil fermé valide pour l'extrusion 3D.
        Retourne None si l'esquisse ne contient aucun profil.
        """
        if not self.entities:
            return None
        # On extrait la première entité fermée
        first_entity = self.entities[0]
        points = first_entity.get_points()
        if len(points) >= 3:
            return points
        return None

    def is_closed_profile(self) -> bool:
        """Indique si l'esquisse possède au moins un contour fermé valide pour extrusion/révolution."""
        return self.get_primary_profile() is not None

    def to_3d_coordinates(self, pt2d: Point2D) -> Vector3D:
        """Projette un point 2D local d'esquisse dans le repère 3D global selon le plan."""
        if self.plane == PlaneType.XY:
            return Vector3D(pt2d.u, pt2d.v, 0.0)
        elif self.plane == PlaneType.XZ:
            return Vector3D(pt2d.u, 0.0, pt2d.v)
        elif self.plane == PlaneType.YZ:
            return Vector3D(0.0, pt2d.u, pt2d.v)
        return Vector3D(pt2d.u, pt2d.v, 0.0)
