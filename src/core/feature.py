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
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus, make_wedge, extrude_polygon
)
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

    def get_parameters(self) -> Dict[str, float]:
        """Récupère l'ensemble des paramètres géométriques sous forme de dictionnaire."""
        return dict(self.parameters)

    def set_parameters(self, new_params: Dict[str, float]) -> None:
        """Met à jour plusieurs paramètres géométriques simultanément."""
        for name, val in new_params.items():
            if name in self.parameters:
                self.parameters[name] = float(val)
                self.status = FeatureStatus.OUTDATED


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


class ConeFeature(Feature):
    """Fonctionnalité paramétrique de création de cône ou tronc de cône."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Cone",
        radius_bottom: float = 15.0,
        radius_top: float = 0.0,
        height: float = 30.0,
        segments: int = 36,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.parameters = {
            "radius_bottom": float(radius_bottom),
            "radius_top": float(radius_top),
            "height": float(height),
            "segments": float(segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le cône et applique l'opération booléenne demandée."""
        r_bot = max(0.0, self.parameters["radius_bottom"])
        r_top = max(0.0, self.parameters["radius_top"])
        h = max(0.001, self.parameters["height"])
        segs = max(12, int(self.parameters.get("segments", 36)))

        new_solid = make_cone(r_bot, r_top, h, segments=segs, name=self.name)
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class TorusFeature(Feature):
    """Fonctionnalité paramétrique de création de tore (donut)."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Torus",
        major_radius: float = 25.0,
        minor_radius: float = 6.0,
        segments: int = 36,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.parameters = {
            "major_radius": float(major_radius),
            "minor_radius": float(minor_radius),
            "segments": float(segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le tore et applique l'opération booléenne demandée."""
        r_maj = max(0.1, self.parameters["major_radius"])
        r_min = max(0.01, self.parameters["minor_radius"])
        segs = max(12, int(self.parameters.get("segments", 36)))

        new_solid = make_torus(r_maj, r_min, segments=segs, name=self.name)
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class WedgeFeature(Feature):
    """Fonctionnalité paramétrique de création de coin / prisme trapézoïdal (FreeCAD Wedge)."""

    def __init__(
        self,
        feature_id: str,
        name: str = "Wedge",
        dx: float = 30.0,
        dy: float = 20.0,
        dz: float = 15.0,
        dx_top: float = 0.0,
        dy_top: float = 0.0,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.parameters = {
            "dx": float(dx),
            "dy": float(dy),
            "dz": float(dz),
            "dx_top": float(dx_top),
            "dy_top": float(dy_top),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le prisme trapézoïdal ou coin et applique l'opération booléenne."""
        dx = max(0.001, self.parameters["dx"])
        dy = max(0.001, self.parameters["dy"])
        dz = max(0.001, self.parameters["dz"])
        dx_top = max(0.0, self.parameters.get("dx_top", 0.0))
        dy_top = max(0.0, self.parameters.get("dy_top", 0.0))

        new_solid = make_wedge(dx, dy, dz, dx_top, dy_top, name=self.name)
        return _apply_boolean_operation(existing_bodies, new_solid, self.operation, self.body_id, self.target_body_id)


class ExtrudeFeature(Feature):
    """
    Fonctionnalité maîtresse d'extrusion paramétrique d'une esquisse 2D style FreeCAD Pad.
    Consomme un profil de Sketch2D et l'extrude avec support du mode symétrique, dépouille et torsion.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Extrude",
        sketch_id: str = "",
        distance: float = 25.0,
        symmetric: bool = False,
        taper_angle: float = 0.0,
        twist_degrees: float = 0.0,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None,
        height: Optional[float] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.sketch_id = sketch_id
        actual_dist = float(height if height is not None else distance)
        self.symmetric = symmetric
        self.taper_angle = float(taper_angle)
        self.twist_degrees = float(twist_degrees)
        self.parameters = {
            "distance": actual_dist,
            "symmetric": 1.0 if symmetric else 0.0,
            "taper_angle": float(taper_angle),
            "twist_degrees": float(twist_degrees),
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
        outer_profile, holes = sketch.get_profile_with_holes()
        if not outer_profile or len(outer_profile) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        dist = float(self.parameters.get("distance", 25.0))
        if abs(dist) < 0.001:
            dist = 0.001

        sym = bool(self.parameters.get("symmetric", 0.0) > 0.5 or getattr(self, "symmetric", False))
        taper = float(self.parameters.get("taper_angle", getattr(self, "taper_angle", 0.0)))
        twist = float(self.parameters.get("twist_degrees", getattr(self, "twist_degrees", 0.0)))

        custom_frame = None
        if getattr(sketch, "is_arbitrary_plane", False):
            custom_frame = (sketch.origin, sketch.normal, sketch.u_axis, sketch.v_axis)

        new_solid = extrude_polygon(
            outer_profile,
            dist,
            plane=sketch.plane,
            plane_offset=sketch.offset_distance,
            symmetric=sym,
            taper_angle=taper,
            twist_degrees=twist,
            name=self.name,
            holes=holes if holes else None,
            custom_frame=custom_frame
        )
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
        tgt_key = resolve_target_body_id(self.target_body_id, updated)
        tool_key = resolve_target_body_id(self.tool_body_id, updated)

        if not tgt_key or not tool_key or tgt_key == tool_key:
            self.status = FeatureStatus.ERROR
            return updated

        target_solid = updated[tgt_key]
        tool_solid = updated[tool_key]

        if self.operation == BooleanOperation.JOIN:
            result = target_solid.union(tool_solid)
        elif self.operation == BooleanOperation.CUT:
            result = target_solid.difference(tool_solid)
        elif self.operation == BooleanOperation.INTERSECT:
            result = target_solid.intersection(tool_solid)
        else:
            result = target_solid

        updated[tgt_key] = result
        del updated[tool_key]  # L'outil est consommé dans l'opération
        self.status = FeatureStatus.OK
        return updated


def resolve_target_body_id(target_body_id: Optional[str], bodies: Dict[str, Solid]) -> Optional[str]:
    """
    Résout de manière tolérante l'identifiant d'un corps solide cible dans un dictionnaire.
    Prend en compte les préfixes 'body_' automatiques pour éviter les échecs silencieux.
    """
    if not target_body_id:
        return None
    if target_body_id in bodies:
        return target_body_id
    if f"body_{target_body_id}" in bodies:
        return f"body_{target_body_id}"
    if target_body_id.startswith("body_") and target_body_id[5:] in bodies:
        return target_body_id[5:]
    return None


def _apply_boolean_operation(
    current_bodies: Dict[str, Solid],
    new_solid: Solid,
    operation: BooleanOperation,
    new_body_id: str,
    target_body_id: Optional[str]
) -> Dict[str, Solid]:
    """Applique l'opération booléenne spécifiée sur la liste active des corps."""
    updated = dict(current_bodies)
    resolved_target = resolve_target_body_id(target_body_id, updated)

    if operation == BooleanOperation.NEW_BODY or not resolved_target or resolved_target not in updated:
        updated[new_body_id] = new_solid
    elif operation == BooleanOperation.JOIN:
        updated[resolved_target] = updated[resolved_target].union(new_solid)
    elif operation == BooleanOperation.CUT:
        updated[resolved_target] = updated[resolved_target].difference(new_solid)
    elif operation == BooleanOperation.INTERSECT:
        updated[resolved_target] = updated[resolved_target].intersection(new_solid)

    return updated
