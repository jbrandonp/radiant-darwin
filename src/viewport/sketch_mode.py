"""
Mode d'esquisse interactif 2D dans le Viewport 3D (Interactive Sketcher).
Permet le tracé direct à la souris de lignes, rectangles et cercles
avec accrochage (Snapping) sur la grille et prévisualisation dynamique.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Tuple
import numpy as np

from src.core.types import Point2D, PlaneType, Vector3D
from src.core.sketch import Sketch2D


class InteractiveTool(Enum):
    """Outil de dessin actif en mode esquisse."""
    NONE = auto()
    LINE = auto()
    RECTANGLE = auto()
    CIRCLE = auto()


@dataclass
class SketchInteractionState:
    """État actuel de l'interaction de dessin en cours."""
    is_active: bool = False
    active_plane: PlaneType = PlaneType.XY
    tool: InteractiveTool = InteractiveTool.NONE
    start_point: Optional[Point2D] = None
    current_hover_point: Optional[Point2D] = None
    snap_grid_step_mm: float = 5.0  # Accrochage tous les 5 mm


class ViewportSketchController:
    """
    Contrôleur de dessin interactif 2D superposé dans le Viewport 3D.
    """

    def __init__(self) -> None:
        """Initialise l'état d'esquisse."""
        self.state = SketchInteractionState()

    def start_sketch(self, plane: PlaneType = PlaneType.XY) -> None:
        """Active le mode esquisse sur le plan choisi."""
        self.state.is_active = True
        self.state.active_plane = plane
        self.state.tool = InteractiveTool.RECTANGLE
        self.state.start_point = None
        self.state.current_hover_point = None

    def finish_sketch(self) -> None:
        """Quitte le mode esquisse."""
        self.state.is_active = False
        self.state.tool = InteractiveTool.NONE
        self.state.start_point = None
        self.state.current_hover_point = None

    def snap_coordinate(self, val: float) -> float:
        """Aimante une coordonnée sur la grille la plus proche."""
        step = self.state.snap_grid_step_mm
        return round(val / step) * step

    def handle_mouse_click(self, local_u: float, local_v: float, sketch: Sketch2D) -> bool:
        """
        Gère le clic de la souris en mode esquisse.
        Retourne True si une entité géométrique a été complétée et ajoutée à l'esquisse.
        """
        if not self.state.is_active or self.state.tool == InteractiveTool.NONE:
            return False

        snapped_u = self.snap_coordinate(local_u)
        snapped_v = self.snap_coordinate(local_v)
        pt = Point2D(snapped_u, snapped_v)

        if self.state.start_point is None:
            # Premier clic : Définir le point d'origine du tracé
            self.state.start_point = pt
            return False
        else:
            # Deuxième clic : Finaliser l'entité géométrique
            p0 = self.state.start_point
            self.state.start_point = None

            if self.state.tool == InteractiveTool.RECTANGLE:
                w = pt.u - p0.u
                h = pt.v - p0.v
                if abs(w) > 1e-3 and abs(h) > 1e-3:
                    origin = Point2D(min(p0.u, pt.u), min(p0.v, pt.v))
                    sketch.add_rectangle(origin, abs(w), abs(h))
                    return True

            elif self.state.tool == InteractiveTool.CIRCLE:
                radius = p0.distance_to(pt)
                if radius > 1e-3:
                    sketch.add_circle(p0, radius)
                    return True

            elif self.state.tool == InteractiveTool.LINE:
                sketch.add_polygon([p0, pt])
                return True

            return False

    def handle_mouse_move(self, local_u: float, local_v: float) -> None:
        """Met à jour le point de survol aimanté pour l'aperçu du tracé."""
        if not self.state.is_active:
            return
        snapped_u = self.snap_coordinate(local_u)
        snapped_v = self.snap_coordinate(local_v)
        self.state.current_hover_point = Point2D(snapped_u, snapped_v)
