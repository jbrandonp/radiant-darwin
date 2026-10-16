"""
Moteur d'esquisse 2D (Sketcher) paramétrique.
Permet de tracer des profils géométriques 2D fermés sur des plans cartésiens
afin de servir de base aux opérations d'extrusion et de révolution 3D.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional, Union
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
    BSPLINE = "bspline"
    BEZIER = "bezier"
    EXTERNAL_REFERENCE = "external_reference"
    ARC = "arc"


class SketchEntity:
    """Classe de base pour une entité d'esquisse (FreeCAD Sketcher Entity)."""

    def __init__(self, entity_id: str, entity_type: EntityType, is_construction: bool = False) -> None:
        self.entity_id: str = entity_id
        self.entity_type: EntityType = entity_type
        self.is_construction: bool = is_construction

    def get_points(self) -> List[Point2D]:
        """Retourne la liste des points ordonnés constituant l'entité."""
        raise NotImplementedError


class SketchLine(SketchEntity):
    """Segment de droite 2D (FreeCAD Sketcher Line)."""

    def __init__(self, entity_id: str, p1: Point2D, p2: Point2D, is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.LINE, is_construction=is_construction)
        self.p1: Point2D = p1
        self.p2: Point2D = p2

    def get_points(self) -> List[Point2D]:
        """Retourne les extrémités du segment."""
        return [self.p1, self.p2]


class SketchExternalReference(SketchEntity):
    """
    Projection 2D d'une géométrie 3D externe (FreeCAD Sketcher External Geometry).
    Génère un trait de référence passif violet sur lequel les contraintes peuvent s'accrocher.
    """

    def __init__(
        self,
        entity_id: str,
        p1: Point2D,
        p2: Point2D,
        source_body_id: str = "",
        source_edge_id: str = "",
        color: str = "#8A2BE2"
    ) -> None:
        super().__init__(entity_id, EntityType.EXTERNAL_REFERENCE, is_construction=True)
        self.p1: Point2D = p1
        self.p2: Point2D = p2
        self.source_body_id: str = source_body_id
        self.source_edge_id: str = source_edge_id
        self.color: str = color

    def get_points(self) -> List[Point2D]:
        """Retourne les deux extrémités du segment de référence projeté."""
        return [self.p1, self.p2]


class SketchArc(SketchEntity):
    """Arc de cercle 2D défini par un centre, un rayon et deux angles angulaires."""

    def __init__(
        self,
        entity_id: str,
        center: Point2D,
        radius: float,
        start_angle_rad: float,
        end_angle_rad: float,
        segments: int = 24,
        is_construction: bool = False
    ) -> None:
        super().__init__(entity_id, EntityType.ARC, is_construction=is_construction)
        self.center: Point2D = center
        self.radius: float = max(0.01, float(radius))
        self.start_angle_rad: float = float(start_angle_rad)
        self.end_angle_rad: float = float(end_angle_rad)
        self.segments: int = max(6, segments)

    def get_points(self) -> List[Point2D]:
        """Discrétise l'arc le long de son étendue angulaire."""
        angles = np.linspace(self.start_angle_rad, self.end_angle_rad, self.segments, endpoint=True)
        return [
            Point2D(self.center.u + self.radius * float(np.cos(a)), self.center.v + self.radius * float(np.sin(a)))
            for a in angles
        ]


class DimensionType(Enum):
    """Types de cotes géométriques d'esquisse."""
    DISTANCE = "distance"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    RADIUS = "radius"
    DIAMETER = "diameter"
    ANGLE = "angle"


class SketchDimension:
    """
    Cote paramétrique d'esquisse.
    Supporte les cotes pilotantes (driving) qui imposent une contrainte au solveur,
    et les cotes pilotées / référence (driven) qui mesurent passivement sans sur-contraindre.
    """

    def __init__(
        self,
        dimension_id: str,
        dim_type: DimensionType,
        entity1_id: str,
        entity2_id: Optional[str] = None,
        value: float = 0.0,
        is_driven: bool = False
    ) -> None:
        self.dimension_id: str = dimension_id
        self.dim_type: DimensionType = dim_type
        self.entity1_id: str = entity1_id
        self.entity2_id: Optional[str] = entity2_id
        self.value: float = float(value)
        self.is_driven: bool = is_driven


class SketchRectangle(SketchEntity):
    """Rectangle 2D défini par son coin inférieur gauche et ses dimensions."""

    def __init__(self, entity_id: str, origin: Point2D, width: float, height: float, is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.RECTANGLE, is_construction=is_construction)
        self.origin: Point2D = origin
        self.width: float = width
        self.height: float = height

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


class SketchCircle(SketchEntity):
    """Cercle 2D discrétisé en polygone régulier pour l'extrusion."""

    def __init__(self, entity_id: str, center: Point2D, radius: float, segments: int = 36, is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.CIRCLE, is_construction=is_construction)
        self.center: Point2D = center
        self.radius: float = radius
        self.segments: int = max(12, segments)

    def get_points(self) -> List[Point2D]:
        """Génère les sommets du contour circulaire discret."""
        pts: List[Point2D] = []
        angles = np.linspace(0.0, 2.0 * np.pi, self.segments, endpoint=False)
        for theta in angles:
            u = self.center.u + self.radius * float(np.cos(theta))
            v = self.center.v + self.radius * float(np.sin(theta))
            pts.append(Point2D(u, v))
        return pts


class SketchPolygon(SketchEntity):
    """Polygone 2D libre défini par une suite de sommets ordonnés."""

    def __init__(self, entity_id: str, points: List[Point2D], is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.POLYGON, is_construction=is_construction)
        self.points: List[Point2D] = points

    def get_points(self) -> List[Point2D]:
        """Retourne la séquence des points du polygone."""
        return self.points


class SketchSlot(SketchEntity):
    """Rainure oblongue 2D (FreeCAD Sketcher Slot) définie par deux centres et un rayon."""

    def __init__(self, entity_id: str, p1: Point2D, p2: Point2D, radius: float, segments: int = 16, is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.SLOT, is_construction=is_construction)
        self.p1: Point2D = p1
        self.p2: Point2D = p2
        self.radius: float = max(0.01, radius)
        self.segments: int = max(8, segments)

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


class SketchRegularPolygon(SketchEntity):
    """Polygone régulier 2D inscrit (FreeCAD Regular Polygon) à N côtés."""

    def __init__(self, entity_id: str, center: Point2D, radius: float, sides: int = 6, is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.REGULAR_POLYGON, is_construction=is_construction)
        self.center: Point2D = center
        self.radius: float = max(0.01, radius)
        self.sides: int = max(3, sides)

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


class SketchEllipse(SketchEntity):
    """Ellipse 2D paramétrique (FreeCAD Sketcher Ellipse)."""

    def __init__(self, entity_id: str, center: Point2D, radius_u: float, radius_v: float, segments: int = 36, is_construction: bool = False) -> None:
        super().__init__(entity_id, EntityType.ELLIPSE, is_construction=is_construction)
        self.center: Point2D = center
        self.radius_u: float = max(0.01, radius_u)
        self.radius_v: float = max(0.01, radius_v)
        self.segments: int = max(12, segments)

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


class SketchBSpline(SketchEntity):
    """
    Courbe B-Spline 2D paramétrique de degré p (FreeCAD Sketcher B-Spline).
    Définie par une liste de points de contrôle (pôles) et évaluée par l'algorithme de De Boor.
    """

    def __init__(
        self,
        entity_id: str,
        control_points: List[Point2D],
        degree: int = 3,
        closed: bool = False,
        segments: int = 40,
        is_construction: bool = False
    ) -> None:
        super().__init__(entity_id, EntityType.BSPLINE, is_construction=is_construction)
        self.control_points: List[Point2D] = list(control_points)
        self.closed: bool = closed
        self.degree: int = max(1, min(degree, len(control_points) - 1)) if len(control_points) > 1 else 1
        self.segments: int = max(10, segments)

    @staticmethod
    def _de_boor_eval(
        ctrl_u: List[float],
        ctrl_v: List[float],
        knots: np.ndarray,
        t: float,
        p: int,
        k: int
    ) -> Point2D:
        """Exécute l'algorithme triangulaire de De Boor pour un paramètre t."""
        d_u = list(ctrl_u)
        d_v = list(ctrl_v)
        for r in range(1, p + 1):
            for j in range(k, k - p + r - 1, -1):
                denom = float(knots[j + p + 1 - r] - knots[j])
                alpha = (t - knots[j]) / denom if abs(denom) > 1e-9 else 0.0
                d_u[j] = (1.0 - alpha) * d_u[j - 1] + alpha * d_u[j]
                d_v[j] = (1.0 - alpha) * d_v[j - 1] + alpha * d_v[j]
        return Point2D(float(d_u[k]), float(d_v[k]))

    def _eval_closed_bspline(self, pts: List[Point2D], p: int) -> List[Point2D]:
        ctrl_pts_ext = list(pts) + list(pts[:p])
        n_ext = len(ctrl_pts_ext)
        m = n_ext + p + 1
        knots = np.linspace(0.0, 1.0, m)
        t_eval = np.linspace(knots[p], knots[n_ext], self.segments, endpoint=False)
        ctrl_u = [pt.u for pt in ctrl_pts_ext]
        ctrl_v = [pt.v for pt in ctrl_pts_ext]
        evaluated: List[Point2D] = []
        for t in t_eval:
            k = int(np.searchsorted(knots, t, side="right") - 1)
            k = max(p, min(k, n_ext - 1))
            evaluated.append(self._de_boor_eval(ctrl_u, ctrl_v, knots, float(t), p, k))
        if evaluated:
            evaluated.append(evaluated[0])
        return evaluated

    def _eval_open_bspline(self, pts: List[Point2D], p: int) -> List[Point2D]:
        n = len(pts)
        m = n + p + 1
        knots = np.zeros(m, dtype=np.float64)
        knots[p:m - p] = np.linspace(0.0, 1.0, m - 2 * p)
        knots[m - p:] = 1.0
        t_eval = np.linspace(0.0, 1.0, self.segments, endpoint=True)
        ctrl_u = [pt.u for pt in pts]
        ctrl_v = [pt.v for pt in pts]
        evaluated: List[Point2D] = []
        for t in t_eval:
            if t >= 1.0:
                evaluated.append(pts[-1])
                continue
            k = int(np.searchsorted(knots, t, side="right") - 1)
            k = max(p, min(k, n - 1))
            evaluated.append(self._de_boor_eval(ctrl_u, ctrl_v, knots, float(t), p, k))
        return evaluated

    def get_points(self) -> List[Point2D]:
        """Évalue la B-spline sur self.segments échantillons via l'algorithme De Boor."""
        pts = self.control_points
        n = len(pts)
        if n <= 2:
            return list(pts)

        if self.closed:
            return self._eval_closed_bspline(pts, self.degree)
        return self._eval_open_bspline(pts, self.degree)

    def to_profile_points(self, num_segments: Optional[int] = None) -> List[Point2D]:
        """Génère les points ordonnés du profil pour extrusion ou révolution."""
        if num_segments is not None:
            self.segments = max(6, num_segments)
        return self.get_points()


class SketchBezier(SketchEntity):
    """
    Courbe de Bézier 2D paramétrique de degré N (FreeCAD Sketcher Bézier).
    Définie par ses points de contrôle et évaluée par les polynômes de Bernstein.
    """

    def __init__(
        self,
        entity_id: str,
        control_points: List[Point2D],
        closed: bool = False,
        segments: int = 40,
        is_construction: bool = False
    ) -> None:
        super().__init__(entity_id, EntityType.BEZIER, is_construction=is_construction)
        self.control_points: List[Point2D] = list(control_points)
        self.closed: bool = closed
        self.segments: int = max(10, segments)

    def get_points(self) -> List[Point2D]:
        """Évalue la courbe de Bézier via l'algorithme polynomial de De Casteljau."""
        pts = self.control_points
        n = len(pts)
        if n == 0:
            return []
        if n <= 2:
            return pts

        t_steps = np.linspace(0.0, 1.0, self.segments, endpoint=not self.closed)
        u_pts = np.array([p.u for p in pts], dtype=np.float64)
        v_pts = np.array([p.v for p in pts], dtype=np.float64)

        evaluated: List[Point2D] = []
        for t in t_steps:
            curr_u = u_pts.copy()
            curr_v = v_pts.copy()
            for r in range(1, n):
                curr_u = (1.0 - t) * curr_u[:-1] + t * curr_u[1:]
                curr_v = (1.0 - t) * curr_v[:-1] + t * curr_v[1:]
            evaluated.append(Point2D(float(curr_u[0]), float(curr_v[0])))

        if self.closed and len(evaluated) > 0:
            evaluated.append(evaluated[0])

        return evaluated

    def to_profile_points(self, num_segments: Optional[int] = None) -> List[Point2D]:
        """Génère les sommets du contour."""
        if num_segments is not None:
            self.segments = max(6, num_segments)
        return self.get_points()


class Sketch2D:
    """
    Conteneur d'esquisse 2D positionnée sur un plan de référence.
    Permet d'ajouter des formes et d'extraire des profils pour la CAO 3D.
    """

    def __init__(
        self,
        sketch_id: str,
        name: Union[str, PlaneType] = "Sketch",
        plane: PlaneType = PlaneType.XY,
        offset_distance: float = 0.0
    ) -> None:
        """Initialise une nouvelle esquisse sur le plan indiqué avec un éventuel décalage normal."""
        self.sketch_id: str = sketch_id
        if isinstance(name, PlaneType):
            self.plane: PlaneType = name
            self.name: str = f"Sketch_{sketch_id}"
        else:
            self.name = str(name)
            self.plane = plane
        self.offset_distance: float = float(offset_distance)
        self.entities: List[SketchEntity] = []
        self.dimensions: List[SketchDimension] = []
        self._counter: int = 0

    def add_line(self, p1: Point2D, p2: Point2D, is_construction: bool = False) -> SketchLine:
        """Ajoute un segment de ligne à l'esquisse (FreeCAD Sketcher Line)."""
        self._counter += 1
        entity_id = f"line_{self._counter}"
        line = SketchLine(entity_id, p1, p2, is_construction=is_construction)
        self.entities.append(line)
        return line

    def add_rectangle(self, origin: Point2D, width: float, height: float, is_construction: bool = False) -> SketchRectangle:
        """Ajoute un rectangle paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"rect_{self._counter}"
        rect = SketchRectangle(entity_id, origin, width, height, is_construction=is_construction)
        self.entities.append(rect)
        return rect

    def add_circle(self, center: Point2D, radius: float, segments: int = 36, is_construction: bool = False) -> SketchCircle:
        """Ajoute un cercle paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"circle_{self._counter}"
        circle = SketchCircle(entity_id, center, radius, segments, is_construction=is_construction)
        self.entities.append(circle)
        return circle

    def add_polygon(self, points: List[Point2D], is_construction: bool = False) -> SketchPolygon:
        """Ajoute un polygone libre à l'esquisse."""
        self._counter += 1
        entity_id = f"poly_{self._counter}"
        poly = SketchPolygon(entity_id, points, is_construction=is_construction)
        self.entities.append(poly)
        return poly

    def add_slot(self, p1: Point2D, p2: Point2D, radius: float, segments: int = 16, is_construction: bool = False) -> SketchSlot:
        """Ajoute une rainure oblongue (slot) paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"slot_{self._counter}"
        slot = SketchSlot(entity_id, p1, p2, radius, segments, is_construction=is_construction)
        self.entities.append(slot)
        return slot

    def add_regular_polygon(self, center: Point2D, radius: float, sides: int = 6, is_construction: bool = False) -> SketchRegularPolygon:
        """Ajoute un polygone régulier (hexagone, octogone, etc.) à l'esquisse."""
        self._counter += 1
        entity_id = f"regpoly_{self._counter}"
        reg_poly = SketchRegularPolygon(entity_id, center, radius, sides, is_construction=is_construction)
        self.entities.append(reg_poly)
        return reg_poly

    def add_ellipse(
        self,
        center: Point2D,
        radius_u: float = 10.0,
        radius_v: float = 5.0,
        segments: int = 36,
        radius_x: Optional[float] = None,
        radius_y: Optional[float] = None,
        is_construction: bool = False
    ) -> SketchEllipse:
        """Ajoute une ellipse paramétrique à l'esquisse."""
        ru = radius_x if radius_x is not None else radius_u
        rv = radius_y if radius_y is not None else radius_v
        self._counter += 1
        entity_id = f"ellipse_{self._counter}"
        ellipse = SketchEllipse(entity_id, center, ru, rv, segments, is_construction=is_construction)
        self.entities.append(ellipse)
        return ellipse

    def add_bspline(
        self,
        control_points: List[Point2D],
        degree: int = 3,
        closed: bool = False,
        segments: int = 40,
        is_construction: bool = False
    ) -> SketchBSpline:
        """Ajoute une courbe B-Spline paramétrique (FreeCAD Sketcher B-Spline)."""
        self._counter += 1
        entity_id = f"bspline_{self._counter}"
        bspline = SketchBSpline(entity_id, control_points, degree, closed, segments, is_construction=is_construction)
        self.entities.append(bspline)
        return bspline

    def add_bezier(
        self,
        control_points: List[Point2D],
        closed: bool = False,
        segments: int = 40,
        is_construction: bool = False
    ) -> SketchBezier:
        """Ajoute une courbe de Bézier paramétrique (FreeCAD Sketcher Bézier)."""
        self._counter += 1
        entity_id = f"bezier_{self._counter}"
        bezier = SketchBezier(entity_id, control_points, closed, segments, is_construction=is_construction)
        self.entities.append(bezier)
        return bezier


    def get_solid_entities(self) -> List[SketchEntity]:
        """Retourne uniquement les entités réelles (non construction) destinées à générer de la matière 3D."""
        return [e for e in self.entities if not e.is_construction]

    def get_construction_entities(self) -> List[SketchEntity]:
        """Retourne uniquement les entités de construction (d'aide/référence) ignorées par les opérations solides."""
        return [e for e in self.entities if e.is_construction]

    def get_primary_profile(self) -> Optional[List[Point2D]]:
        """
        Extrait le premier profil fermé réel (non de construction) valide pour l'extrusion 3D.
        Retourne None si l'esquisse ne contient aucun profil valide.
        """
        solids = self.get_solid_entities()
        if not solids:
            return None
        for entity in solids:
            points = entity.get_points()
            if len(points) >= 3:
                return points
        return None

    def is_closed_profile(self) -> bool:
        """Indique si l'esquisse possède au moins un contour fermé valide pour extrusion/révolution."""
        return self.get_primary_profile() is not None

    def to_3d_coordinates(self, pt2d: Point2D) -> Vector3D:
        """Projette un point 2D local d'esquisse dans le repère 3D global selon le plan et le décalage normal."""
        if self.plane == PlaneType.XY:
            return Vector3D(pt2d.u, pt2d.v, self.offset_distance)
        elif self.plane == PlaneType.XZ:
            return Vector3D(pt2d.u, self.offset_distance, pt2d.v)
        elif self.plane == PlaneType.YZ:
            return Vector3D(self.offset_distance, pt2d.u, pt2d.v)
        return Vector3D(pt2d.u, pt2d.v, self.offset_distance)

    def add_arc(
        self,
        center: Point2D,
        radius: float,
        start_angle_rad: float,
        end_angle_rad: float,
        segments: int = 24,
        is_construction: bool = False
    ) -> SketchArc:
        """Ajoute un arc de cercle paramétrique à l'esquisse."""
        self._counter += 1
        entity_id = f"arc_{self._counter}"
        arc = SketchArc(entity_id, center, radius, start_angle_rad, end_angle_rad, segments, is_construction=is_construction)
        self.entities.append(arc)
        return arc

    def add_external_reference(
        self,
        edge_start: Tuple[float, float, float],
        edge_end: Tuple[float, float, float],
        source_body_id: str = "",
        source_edge_id: str = ""
    ) -> SketchExternalReference:
        """
        Projette une arête 3D externe sur le plan d'esquisse actif (Sketcher External Geometry).
        Crée un trait violet de référence passif pour y contraindre ou coter l'esquisse.
        """
        from src.solver.constraints_2d import project_3d_edge_to_sketch_plane

        if self.plane == PlaneType.XY:
            origin = (0.0, 0.0, self.offset_distance)
            normal = (0.0, 0.0, 1.0)
            u_axis = (1.0, 0.0, 0.0)
        elif self.plane == PlaneType.XZ:
            origin = (0.0, self.offset_distance, 0.0)
            normal = (0.0, 1.0, 0.0)
            u_axis = (1.0, 0.0, 0.0)
        elif self.plane == PlaneType.YZ:
            origin = (self.offset_distance, 0.0, 0.0)
            normal = (1.0, 0.0, 0.0)
            u_axis = (0.0, 1.0, 0.0)
        else:
            origin = (0.0, 0.0, self.offset_distance)
            normal = (0.0, 0.0, 1.0)
            u_axis = (1.0, 0.0, 0.0)

        p1_2d, p2_2d = project_3d_edge_to_sketch_plane(
            edge_start, edge_end, plane_origin=origin, plane_normal=normal, plane_u_axis=u_axis
        )

        self._counter += 1
        entity_id = f"ext_ref_{self._counter}"
        ref_entity = SketchExternalReference(
            entity_id=entity_id,
            p1=p1_2d,
            p2=p2_2d,
            source_body_id=source_body_id,
            source_edge_id=source_edge_id
        )
        self.entities.append(ref_entity)
        return ref_entity

    @staticmethod
    def _calculate_linear_dim(pts: List[Point2D], dim_type: DimensionType) -> float:
        """Calcule la composante linéaire (distance, horizontale, verticale) entre deux points."""
        u0 = pts[0].u if hasattr(pts[0], 'u') else float(pts[0][0])
        v0 = pts[0].v if hasattr(pts[0], 'v') else float(pts[0][1])
        u1 = pts[1].u if hasattr(pts[1], 'u') else float(pts[1][0])
        v1 = pts[1].v if hasattr(pts[1], 'v') else float(pts[1][1])
        if dim_type == DimensionType.DISTANCE:
            return float(np.hypot(u1 - u0, v1 - v0))
        if dim_type == DimensionType.HORIZONTAL:
            return float(abs(u1 - u0))
        if dim_type == DimensionType.VERTICAL:
            return float(abs(v1 - v0))
        return 0.0

    def _calculate_default_dimension_value(self, dim_type: DimensionType, entity1_id: str) -> float:
        """Calcule la valeur par défaut d'une cote à partir des entités référencées."""
        ent1 = next((e for e in self.entities if e.entity_id == entity1_id), None)
        if ent1 is None:
            return 0.0
        pts1 = ent1.get_points()
        if len(pts1) >= 2 and dim_type in (DimensionType.DISTANCE, DimensionType.HORIZONTAL, DimensionType.VERTICAL):
            return self._calculate_linear_dim(pts1, dim_type)
        if dim_type in (DimensionType.RADIUS, DimensionType.DIAMETER) and isinstance(ent1, SketchCircle):
            return ent1.radius if dim_type == DimensionType.RADIUS else ent1.radius * 2.0
        return 0.0

    def add_dimension(
        self,
        dim_type: DimensionType,
        entity1_id: str,
        entity2_id: Optional[str] = None,
        value: Optional[float] = None,
        is_driven: bool = False
    ) -> SketchDimension:
        """
        Ajoute une cote paramétrique à l'esquisse (distance, horizontale, verticale, angle, rayon).
        Si is_driven=True, il s'agit d'une cote pilotée (Driven Dimension) de référence passive.
        """
        self._counter += 1
        dim_id = f"dim_{self._counter}"

        calculated_val = float(value) if value is not None else self._calculate_default_dimension_value(dim_type, entity1_id)

        dim = SketchDimension(
            dimension_id=dim_id,
            dim_type=dim_type,
            entity1_id=entity1_id,
            entity2_id=entity2_id,
            value=calculated_val,
            is_driven=is_driven
        )
        self.dimensions.append(dim)
        return dim

    def get_driven_dimensions(self) -> List[SketchDimension]:
        """Retourne toutes les cotes de référence passives (Driven Dimensions)."""
        return [d for d in self.dimensions if d.is_driven]

    def get_driving_dimensions(self) -> List[SketchDimension]:
        """Retourne toutes les cotes actives imposant des contraintes aux géométries."""
        return [d for d in self.dimensions if not d.is_driven]

    def trim_segment(
        self,
        target_line_id: str,
        cutting_line_id: str,
        keep_side: str = "start"
    ) -> Optional[SketchLine]:
        """
        Découpe/Ajuste un segment de ligne (Trim) à son intersection avec une ligne de coupe.
        Conserve le côté 'start' ou le côté 'end'.
        """
        from src.solver.constraints_2d import trim_intersection_2d

        target = next((e for e in self.entities if e.entity_id == target_line_id and isinstance(e, SketchLine)), None)
        cutter = next((e for e in self.entities if e.entity_id == cutting_line_id and isinstance(e, SketchLine)), None)

        if not target or not cutter:
            return None

        inter_pt = trim_intersection_2d(target.p1, target.p2, cutter.p1, cutter.p2)
        if not inter_pt:
            return None

        if keep_side == "start":
            target.p2 = inter_pt
        else:
            target.p1 = inter_pt
        return target

    def extend_segment(
        self,
        target_line_id: str,
        boundary_line_id: str
    ) -> Optional[SketchLine]:
        """
        Prolonge un segment de droite (Extend) jusqu'à son intersection avec une frontière.
        """
        from src.solver.constraints_2d import trim_intersection_2d

        target = next((e for e in self.entities if e.entity_id == target_line_id and isinstance(e, SketchLine)), None)
        boundary = next((e for e in self.entities if e.entity_id == boundary_line_id and isinstance(e, SketchLine)), None)

        if not target or not boundary:
            return None

        inter_pt = trim_intersection_2d(target.p1, target.p2, boundary.p1, boundary.p2)
        if not inter_pt:
            return None

        d1 = float(np.hypot(target.p1.u - inter_pt.u, target.p1.v - inter_pt.v))
        d2 = float(np.hypot(target.p2.u - inter_pt.u, target.p2.v - inter_pt.v))

        if d2 <= d1:
            target.p2 = inter_pt
        else:
            target.p1 = inter_pt
        return target

    def fillet_2d_lines(
        self,
        line1_id: str,
        line2_id: str,
        radius: float
    ) -> Optional[Tuple[SketchLine, SketchLine, SketchCircle]]:
        """
        Applique un congé d'angle 2D (Fillet) entre deux segments de droite sécants.
        Raccourcit les lignes jusqu'aux points de tangence et insère un cercle/arc tangent.
        """
        from src.solver.constraints_2d import fillet_2d

        l1 = next((e for e in self.entities if e.entity_id == line1_id and isinstance(e, SketchLine)), None)
        l2 = next((e for e in self.entities if e.entity_id == line2_id and isinstance(e, SketchLine)), None)

        if not l1 or not l2 or radius <= 0.0:
            return None

        eps = 1e-4
        if np.hypot(l1.p2.u - l2.p1.u, l1.p2.v - l2.p1.v) < eps:
            corner, p0, p1 = l1.p2, l1.p1, l2.p2
            is_l1_end, is_l2_start = True, True
        elif np.hypot(l1.p1.u - l2.p1.u, l1.p1.v - l2.p1.v) < eps:
            corner, p0, p1 = l1.p1, l1.p2, l2.p2
            is_l1_end, is_l2_start = False, True
        elif np.hypot(l1.p2.u - l2.p2.u, l1.p2.v - l2.p2.v) < eps:
            corner, p0, p1 = l1.p2, l1.p1, l2.p1
            is_l1_end, is_l2_start = True, False
        elif np.hypot(l1.p1.u - l2.p2.u, l1.p1.v - l2.p2.v) < eps:
            corner, p0, p1 = l1.p1, l1.p2, l2.p1
            is_l1_end, is_l2_start = False, False
        else:
            return None

        t0, t1, center, eff_rad = fillet_2d(p0, corner, p1, radius)
        if eff_rad <= 0.0:
            return None

        if is_l1_end:
            l1.p2 = t0
        else:
            l1.p1 = t0

        if is_l2_start:
            l2.p1 = t1
        else:
            l2.p2 = t1

        self._counter += 1
        fillet_circle = SketchCircle(f"fillet_{self._counter}", center, eff_rad, segments=24)
        self.entities.append(fillet_circle)

        return (l1, l2, fillet_circle)

    def chamfer_2d_lines(
        self,
        line1_id: str,
        line2_id: str,
        distance: float
    ) -> Optional[Tuple[SketchLine, SketchLine, SketchLine]]:
        """
        Applique un chanfrein 2D (Chamfer) entre deux lignes sécantes.
        Recule de la distance spécifiée le long des deux branches et ajoute le segment de biseau.
        """
        l1 = next((e for e in self.entities if e.entity_id == line1_id and isinstance(e, SketchLine)), None)
        l2 = next((e for e in self.entities if e.entity_id == line2_id and isinstance(e, SketchLine)), None)

        if not l1 or not l2 or distance <= 0.0:
            return None

        eps = 1e-4
        if np.hypot(l1.p2.u - l2.p1.u, l1.p2.v - l2.p1.v) < eps:
            corner, p0, p1 = l1.p2, l1.p1, l2.p2
            is_l1_end, is_l2_start = True, True
        elif np.hypot(l1.p1.u - l2.p1.u, l1.p1.v - l2.p1.v) < eps:
            corner, p0, p1 = l1.p1, l1.p2, l2.p2
            is_l1_end, is_l2_start = False, True
        elif np.hypot(l1.p2.u - l2.p2.u, l1.p2.v - l2.p2.v) < eps:
            corner, p0, p1 = l1.p2, l1.p1, l2.p1
            is_l1_end, is_l2_start = True, False
        elif np.hypot(l1.p1.u - l2.p2.u, l1.p1.v - l2.p2.v) < eps:
            corner, p0, p1 = l1.p1, l1.p2, l2.p1
            is_l1_end, is_l2_start = False, False
        else:
            return None

        v0 = np.array([p0.u - corner.u, p0.v - corner.v], dtype=np.float64)
        v1 = np.array([p1.u - corner.u, p1.v - corner.v], dtype=np.float64)
        norm0, norm1 = float(np.linalg.norm(v0)), float(np.linalg.norm(v1))
        if distance <= 1e-9 or norm0 < distance or norm1 < distance:
            return None

        d0 = distance * (v0 / max(norm0, 1e-12))
        d1 = distance * (v1 / max(norm1, 1e-12))

        c0 = Point2D(corner.u + float(d0[0]), corner.v + float(d0[1]))
        c1 = Point2D(corner.u + float(d1[0]), corner.v + float(d1[1]))

        if is_l1_end:
            l1.p2 = c0
        else:
            l1.p1 = c0

        if is_l2_start:
            l2.p1 = c1
        else:
            l2.p2 = c1

        self._counter += 1
        chamfer_line = SketchLine(f"chamfer_{self._counter}", c0, c1)
        self.entities.append(chamfer_line)

        return (l1, l2, chamfer_line)

    def generate_porcupine_comb_2d(
        self,
        spline_entity_id: str,
        num_samples: int = 24,
        scale: float = 10.0
    ) -> List[Tuple[Point2D, Point2D]]:
        """
        Génère le peigne de courbure (Porcupine Curvature Comb) d'une spline 2D.
        Retourne une liste de segments [(racine, pointe)] orientés selon la normale locale
        avec une longueur proportionnelle à la courbure kappa(t).
        """
        ent = next((e for e in self.entities if e.entity_id == spline_entity_id), None)
        if not ent:
            return []

        pts = ent.get_points()
        if len(pts) < 3:
            return []

        comb: List[Tuple[Point2D, Point2D]] = []
        n = len(pts)
        step = max(1, n // max(1, num_samples))

        for i in range(1, n - 1, step):
            p_prev = pts[i - 1]
            p_curr = pts[i]
            p_next = pts[i + 1]

            du = (p_next.u - p_prev.u) * 0.5
            dv = (p_next.v - p_prev.v) * 0.5
            d2u = p_next.u - 2.0 * p_curr.u + p_prev.u
            d2v = p_next.v - 2.0 * p_curr.v + p_prev.v

            speed_sq = du ** 2 + dv ** 2
            if speed_sq < 1e-9:
                continue

            speed = float(np.sqrt(speed_sq))
            kappa = abs(du * d2v - dv * d2u) / (speed_sq * speed)

            norm_u = -dv / speed
            norm_v = du / speed

            tip = Point2D(p_curr.u + norm_u * kappa * scale, p_curr.v + norm_v * kappa * scale)
            comb.append((p_curr, tip))

        return comb

