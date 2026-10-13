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
    SLOT = "slot"
    REGULAR_POLYGON = "regular_polygon"
    ELLIPSE = "ellipse"


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


@dataclass
class SketchSlot(SketchEntity):
    """Rainure oblongue 2D (FreeCAD Sketcher Slot) définie par deux centres et un rayon."""
    p1: Point2D
    p2: Point2D
    radius: float
    segments: int = 16

    def __init__(self, entity_id: str, p1: Point2D, p2: Point2D, radius: float, segments: int = 16) -> None:
        super().__init__(entity_id, EntityType.SLOT)
        self.p1 = p1
        self.p2 = p2
        self.radius = max(0.01, radius)
        self.segments = max(8, segments)

    def get_points(self) -> List[Point2D]:
        """Génère le contour fermé composé de deux demi-cercles et deux segments parallèles."""
        du = self.p2.u - self.p1.u
        dv = self.p2.v - self.p1.v
        dist = float(np.hypot(du, dv))
        if dist < 1e-6:
            angles = np.linspace(0.0, 2.0 * np.pi, self.segments * 2, endpoint=False)
            return [Point2D(self.p1.u + self.radius * float(np.cos(a)), self.p1.v + self.radius * float(np.sin(a))) for a in angles]

        angle_base = float(np.arctan2(dv, du))
        pts: List[Point2D] = []
        # Premier arc autour de p2
        angles_p2 = np.linspace(angle_base - np.pi / 2.0, angle_base + np.pi / 2.0, self.segments)
        for a in angles_p2:
            pts.append(Point2D(self.p2.u + self.radius * float(np.cos(a)), self.p2.v + self.radius * float(np.sin(a))))

        # Deuxième arc autour de p1
        angles_p1 = np.linspace(angle_base + np.pi / 2.0, angle_base + 3.0 * np.pi / 2.0, self.segments)
        for a in angles_p1:
            pts.append(Point2D(self.p1.u + self.radius * float(np.cos(a)), self.p1.v + self.radius * float(np.sin(a))))

        return pts

    def to_profile_points(self, num_segments: Optional[int] = None) -> List[Point2D]:
        """Génère les points du profil fermé."""
        if num_segments is not None:
            self.segments = max(4, num_segments)
        return self.get_points()


@dataclass
class SketchRegularPolygon(SketchEntity):
    """Polygone régulier 2D inscrit (FreeCAD Regular Polygon) à N côtés."""
    center: Point2D
    radius: float
    sides: int = 6

    def __init__(self, entity_id: str, center: Point2D, radius: float, sides: int = 6) -> None:
        super().__init__(entity_id, EntityType.REGULAR_POLYGON)
        self.center = center
        self.radius = max(0.01, radius)
        self.sides = max(3, sides)

    def get_points(self) -> List[Point2D]:
        """Génère les N sommets réguliers."""
        pts: List[Point2D] = []
        angles = np.linspace(0.0, 2.0 * np.pi, self.sides, endpoint=False)
        for a in angles:
            pts.append(Point2D(self.center.u + self.radius * float(np.cos(a)), self.center.v + self.radius * float(np.sin(a))))
        return pts

    def to_profile_points(self) -> List[Point2D]:
        """Génère les sommets du polygone régulier."""
        return self.get_points()


@dataclass
class SketchEllipse(SketchEntity):
    """Ellipse 2D paramétrique (FreeCAD Sketcher Ellipse)."""
    center: Point2D
    radius_u: float
    radius_v: float
    segments: int = 36

    def __init__(self, entity_id: str, center: Point2D, radius_u: float, radius_v: float, segments: int = 36) -> None:
        super().__init__(entity_id, EntityType.ELLIPSE)
        self.center = center
        self.radius_u = max(0.01, radius_u)
        self.radius_v = max(0.01, radius_v)
        self.segments = max(12, segments)

    def get_points(self) -> List[Point2D]:
        """Génère les sommets discrétisés de l'ellipse."""
        pts: List[Point2D] = []
        angles = np.linspace(0.0, 2.0 * np.pi, self.segments, endpoint=False)
        for a in angles:
            pts.append(Point2D(self.center.u + self.radius_u * float(np.cos(a)), self.center.v + self.radius_v * float(np.sin(a))))
        return pts

    def to_profile_points(self, num_segments: Optional[int] = None) -> List[Point2D]:
        """Génère les sommets discrétisés de l'ellipse."""
        if num_segments is not None:
            self.segments = max(4, num_segments)
        return self.get_points()


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

    def add_slot(self, p1: Point2D, p2: Point2D, radius: float, segments: int = 16) -> SketchSlot:
        """Ajoute une rainure oblongue (slot) paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"slot_{self._counter}"
        slot = SketchSlot(entity_id, p1, p2, radius, segments)
        self.entities.append(slot)
        return slot

    def add_regular_polygon(self, center: Point2D, radius: float, sides: int = 6) -> SketchRegularPolygon:
        """Ajoute un polygone régulier (hexagone, octogone, etc.) à l'esquisse."""
        self._counter += 1
        entity_id = f"regpoly_{self._counter}"
        reg_poly = SketchRegularPolygon(entity_id, center, radius, sides)
        self.entities.append(reg_poly)
        return reg_poly

    def add_ellipse(
        self,
        center: Point2D,
        radius_u: float = 10.0,
        radius_v: float = 5.0,
        segments: int = 36,
        radius_x: Optional[float] = None,
        radius_y: Optional[float] = None
    ) -> SketchEllipse:
        """Ajoute une ellipse paramétrique à l'esquisse."""
        ru = radius_x if radius_x is not None else radius_u
        rv = radius_y if radius_y is not None else radius_v
        self._counter += 1
        entity_id = f"ellipse_{self._counter}"
        ellipse = SketchEllipse(entity_id, center, ru, rv, segments)
        self.entities.append(ellipse)
        return ellipse

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
