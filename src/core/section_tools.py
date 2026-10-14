"""
Atelier de Plan de Coupe & Analyse de Section 2D (FreeCAD Part_Section Parity).
Permet de trancher un solide 3D par un plan (XY, XZ, YZ), d'extraire ses contours 2D exacts
et de convertir automatiquement une coupe 3D en une nouvelle Esquisse 2D modifiable.
Calculs de coupes géométriques avec typage vectoriel strict.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Union
import numpy as np

from src.core.types import PlaneType, Point2D, Vector3D
from src.core.geometry import Solid
from src.core.sketch import Sketch2D


def slice_solid_contours(
    solid: Solid,
    axis: str = "Z",
    offset: float = 0.0,
    coordinate: Optional[float] = None
) -> List[List[Point2D]]:
    """
    Extrait la liste des contours fermés 2D résultant de la coupe du solide selon un plan donné.
    - axis : 'Z' (Plan XY), 'Y' (Plan XZ), 'X' (Plan YZ)
    - offset / coordinate : position du plan de coupe le long de l'axe
    """
    if solid.is_empty():
        return []

    cut_offset = coordinate if coordinate is not None else offset

    # Réorienter si nécessaire pour aligner l'axe de coupe sur Z
    target_solid = solid
    if axis.upper() == "X":
        # Rotation pour amener X sur Z
        target_solid = solid.rotate(0.0, 90.0, 0.0)
    elif axis.upper() == "Y":
        # Rotation pour amener Y sur Z
        target_solid = solid.rotate(-90.0, 0.0, 0.0)

    return target_solid.slice_cross_section(cut_offset)


def create_sketch_from_cross_section(
    solid_or_contours: Union[Solid, List[List[Point2D]], None] = None,
    sketch_id: str = "sketch_section",
    name: str = "Coupe de Section",
    axis: str = "Z",
    offset: float = 0.0,
    contours: Optional[List[List[Point2D]]] = None,
    plane: Optional[PlaneType] = None,
    solid: Optional[Solid] = None
) -> Optional[Sketch2D]:
    """
    Génère automatiquement une Esquisse 2D (Sketch2D) paramétrique
    à partir des contours fermés extraits lors de la coupe du solide.
    Accepte indifféremment un Solide ou une liste de contours en premier argument.
    """
    extracted_contours: Optional[List[List[Point2D]]] = None

    if isinstance(solid_or_contours, list):
        extracted_contours = solid_or_contours
    elif isinstance(solid_or_contours, Solid):
        extracted_contours = slice_solid_contours(solid_or_contours, axis=axis, offset=offset)
    elif contours is not None:
        extracted_contours = contours
    elif solid is not None:
        extracted_contours = slice_solid_contours(solid, axis=axis, offset=offset)

    if not extracted_contours:
        return None

    if plane is None:
        plane_map = {"Z": PlaneType.XY, "Y": PlaneType.XZ, "X": PlaneType.YZ}
        resolved_plane = plane_map.get(axis.upper(), PlaneType.XY)
    else:
        resolved_plane = plane

    sketch = Sketch2D(sketch_id, name, plane=resolved_plane)
    for poly in extracted_contours:
        if len(poly) >= 3:
            sketch.add_polygon(poly)

    return sketch


def create_cutaway_solid(
    solid: Solid,
    axis: str = "Z",
    offset: float = 0.0,
    keep_positive_side: bool = False,
    coordinate: Optional[float] = None,
    keep_positive: Optional[bool] = None
) -> Solid:
    """
    Crée une vue écorchée 3D (Cutaway / Section View) en coupant le solide par un demi-espace.
    Permet d'inspecter visuellement l'intérieur des pièces et les perçages cachés.
    """
    if solid.is_empty():
        return solid

    cut_offset = coordinate if coordinate is not None else offset
    positive_side = keep_positive if keep_positive is not None else keep_positive_side

    axis_up = axis.upper()
    if axis_up == "X":
        normal = Vector3D(1.0, 0.0, 0.0)
    elif axis_up == "Y":
        normal = Vector3D(0.0, 1.0, 0.0)
    else:
        normal = Vector3D(0.0, 0.0, 1.0)

    if not positive_side:
        normal = normal.scale(-1.0)
        cut_offset = -cut_offset

    return solid.trim_by_plane(normal, cut_offset)
