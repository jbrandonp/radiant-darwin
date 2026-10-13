"""
Modèle de fonctionnalités paramétriques (Features) style Autodesk Fusion 360.
Chaque feature stocke ses paramètres éditables et sait comment recalculer
sa géométrie dans le contexte du document.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field

from src.core.types import BooleanOperation, FeatureStatus, Vector3D, Point2D, PlaneType
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere, extrude_polygon
from src.core.sketch import Sketch2D


class Feature(ABC):
    """
    Classe abstraite représentant une opération paramétrique dans l'arbre d'historique.
    Possède un identifiant unique, un nom affichable, et des paramètres modifiables.
    """

    def __init__(self, feature_id: str, name: str) -> None:
        """Initialise la feature avec un ID et un libellé."""
        self.feature_id: str = feature_id
        self.name: str = name
        self.status: FeatureStatus = FeatureStatus.OK
        self.is_suppressed: bool = False
        self.parameters: Dict[str, float] = {}

    @abstractmethod
    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """
        Recalcule la géométrie selon les paramètres actuels.
        Prend les corps et esquisses existants et retourne le dictionnaire mis à jour des corps.
        """
        raise NotImplementedError

    def set_parameter(self, param_name: str, value: float) -> None:
        """Modifie la valeur d'un paramètre géométrique."""
        if param_name in self.parameters:
            self.parameters[param_name] = float(value)
            self.status = FeatureStatus.OUTDATED

    def get_parameter(self, param_name: str, default: float = 0.0) -> float:
        """Récupère la valeur d'un paramètre."""
        return self.parameters.get(param_name, default)


class BoxFeature(Feature):
    """Fonctionnalité paramétrique de création de boîte (parallélépipède)."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Box",
        width: float = 20.0,
        height: float = 20.0,
        depth: float = 20.0,
        center: bool = False,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.parameters = {
            "width": float(width),
            "height": float(height),
            "depth": float(depth),
            "center": 1.0 if center else 0.0,
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la boîte et applique l'opération booléenne demandée."""
        w = max(0.001, self.parameters["width"])
        h = max(0.001, self.parameters["height"])
        d = max(0.001, self.parameters["depth"])
        center = bool(self.parameters.get("center", 0.0) > 0.5)

        new_solid = make_box(w, h, d, center=center, name=self.name)
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class CylinderFeature(Feature):
    """Fonctionnalité paramétrique de création de cylindre."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Cylinder",
        radius: float = 10.0,
        height: float = 30.0,
        segments: int = 36,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.parameters = {
            "radius": float(radius),
            "height": float(height),
            "segments": float(segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le cylindre et applique l'opération booléenne demandée."""
        rad = max(0.001, self.parameters["radius"])
        h = max(0.001, self.parameters["height"])
        segs = max(12, int(self.parameters.get("segments", 36)))

        new_solid = make_cylinder(rad, h, segments=segs, center=False, name=self.name)
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class SphereFeature(Feature):
    """Fonctionnalité paramétrique de création de sphère."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Sphere",
        radius: float = 15.0,
        segments: int = 36,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.parameters = {
            "radius": float(radius),
            "segments": float(segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la sphère et applique l'opération booléenne demandée."""
        rad = max(0.001, self.parameters["radius"])
        segs = max(12, int(self.parameters.get("segments", 36)))

        new_solid = make_sphere(rad, segments=segs, name=self.name)
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class ExtrudeFeature(Feature):
    """
    Fonctionnalité maîtresse d'extrusion paramétrique d'une esquisse 2D.
    Consomme un profil de Sketch2D et l'extrude sur une distance donnée.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Extrude",
        sketch_id: str = "",
        distance: float = 25.0,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.sketch_id = sketch_id
        self.parameters = {
            "distance": float(distance),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Extrude le profil de l'esquisse référencée et applique l'opération booléenne."""
        if self.sketch_id not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        sketch = sketches[self.sketch_id]
        profile = sketch.get_primary_profile()
        if not profile or len(profile) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        dist = max(0.001, self.parameters["distance"])
        new_solid = extrude_polygon(profile, dist, plane=sketch.plane, name=self.name)
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class BooleanFeature(Feature):
    """Fonctionnalité booléenne explicite entre deux corps existants."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Combine",
        target_body_id: str = "",
        tool_body_id: str = "",
        operation: BooleanOperation = BooleanOperation.JOIN
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.tool_body_id = tool_body_id
        self.operation = operation

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Exécute l'opération booléenne entre le corps cible et l'outil."""
        updated = dict(existing_bodies)
        if self.target_body_id not in updated or self.tool_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target_solid = updated[self.target_body_id]
        tool_solid = updated[self.tool_body_id]

        if self.operation == BooleanOperation.JOIN:
            result = target_solid.union(tool_solid)
        elif self.operation == BooleanOperation.CUT:
            result = target_solid.difference(tool_solid)
        elif self.operation == BooleanOperation.INTERSECT:
            result = target_solid.intersection(tool_solid)
        else:
            result = target_solid

        updated[self.target_body_id] = result
        del updated[self.tool_body_id]  # L'outil est consommé dans l'opération
        self.status = FeatureStatus.OK
        return updated


def _apply_boolean_operation(
    current_bodies: Dict[str, Solid],
    new_solid: Solid,
    operation: BooleanOperation,
    new_body_id: str,
    target_body_id: Optional[str]
) -> Dict[str, Solid]:
    """Applique l'opération booléenne spécifiée sur la liste active des corps."""
    updated = dict(current_bodies)

    if operation == BooleanOperation.NEW_BODY or not target_body_id or target_body_id not in updated:
        updated[new_body_id] = new_solid
    elif operation == BooleanOperation.JOIN:
        updated[target_body_id] = updated[target_body_id].union(new_solid)
    elif operation == BooleanOperation.CUT:
        updated[target_body_id] = updated[target_body_id].difference(new_solid)
    elif operation == BooleanOperation.INTERSECT:
        updated[target_body_id] = updated[target_body_id].intersection(new_solid)

    return updated
