"""
Fonctionnalités volumiques 3D avancées style Autodesk Fusion 360 :
Révolution (Revolve), Répétitions linéaire et circulaire, Symétrie miroir,
Perçages/Alésages (Holes) et Évidement (Shell).
"""

from __future__ import annotations
from typing import Dict, List, Optional, Sequence
import numpy as np
import manifold3d as m

from src.core.types import BooleanOperation, FeatureStatus, Vector3D, Point2D, PlaneType
from src.core.geometry import Solid, make_cylinder, _extract_sharp_edges
from src.core.feature import Feature, _apply_boolean_operation
from src.core.sketch import Sketch2D


class RevolveFeature(Feature):
    """
    Fonctionnalité de révolution paramétrique d'un profil 2D autour d'un axe.
    Permet de créer des poulies, arbres de transmission, cônes, flacons, etc.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Revolve",
        sketch_id: str = "",
        angle_deg: float = 360.0,
        segments: int = 48,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.sketch_id = sketch_id
        self.parameters = {
            "angle": float(angle_deg),
            "segments": float(segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Exécute la révolution du profil d'esquisse autour de l'axe central."""
        if self.sketch_id not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        sketch = sketches[self.sketch_id]
        profile = sketch.get_primary_profile()
        if not profile or len(profile) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        poly_coords: List[List[float]] = [[pt.u, pt.v] for pt in profile]
        cs = m.CrossSection([poly_coords])
        angle = max(1.0, min(360.0, self.parameters["angle"]))
        segs = max(12, int(self.parameters["segments"]))

        rev_manifold = m.Manifold.revolve(cs, segs, angle)
        solid = Solid(rev_manifold, self.name)
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)


class LinearPatternFeature(Feature):
    """
    Répétition linéaire d'un corps selon une ou deux directions (matrice rectangulaire).
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Linear Pattern",
        source_body_id: str = "",
        count_x: int = 3,
        spacing_x: float = 30.0,
        count_y: int = 1,
        spacing_y: float = 30.0,
        join_bodies: bool = True
    ) -> None:
        super().__init__(feature_id, name)
        self.source_body_id = source_body_id
        self.join_bodies = join_bodies
        self.parameters = {
            "count_x": float(count_x),
            "spacing_x": float(spacing_x),
            "count_y": float(count_y),
            "spacing_y": float(spacing_y),
        }
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la matrice d'occurrences répétées."""
        updated = dict(existing_bodies)
        if self.source_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[self.source_body_id]
        nx = max(1, min(50, int(self.parameters["count_x"])))
        ny = max(1, min(50, int(self.parameters["count_y"])))
        if nx * ny > 500:
            nx = min(nx, 25)
            ny = min(ny, 20)
        dx = float(self.parameters["spacing_x"])
        dy = float(self.parameters["spacing_y"])

        instances: List[Solid] = []
        for ix in range(nx):
            for iy in range(ny):
                offset = Vector3D(ix * dx, iy * dy, 0.0)
                instances.append(base_solid.translate(offset))

        if self.join_bodies and instances:
            combined = instances[0]
            for inst in instances[1:]:
                combined = combined.union(inst)
            updated[self.source_body_id] = combined
        else:
            for idx, inst in enumerate(instances):
                updated[f"{self.source_body_id}_pat_{idx}"] = inst

        self.status = FeatureStatus.OK
        return updated


class CircularPatternFeature(Feature):
    """
    Répétition polaire / circulaire d'un corps solide autour de l'axe Z.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Circular Pattern",
        source_body_id: str = "",
        count: int = 6,
        total_angle_deg: float = 360.0,
        join_bodies: bool = True
    ) -> None:
        super().__init__(feature_id, name)
        self.source_body_id = source_body_id
        self.join_bodies = join_bodies
        self.parameters = {
            "count": float(count),
            "total_angle": float(total_angle_deg),
        }
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère les répétitions réparties angulairement."""
        updated = dict(existing_bodies)
        if self.source_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[self.source_body_id]
        n = max(1, min(360, int(self.parameters["count"])))
        total_ang = float(self.parameters["total_angle"])
        step = total_ang / n if n > 0 else 0.0

        instances: List[Solid] = []
        for i in range(n):
            angle = i * step
            instances.append(base_solid.rotate(0.0, 0.0, angle))

        if self.join_bodies and instances:
            combined = instances[0]
            for inst in instances[1:]:
                combined = combined.union(inst)
            updated[self.source_body_id] = combined
        else:
            for idx, inst in enumerate(instances):
                updated[f"{self.source_body_id}_circ_{idx}"] = inst

        self.status = FeatureStatus.OK
        return updated


class MirrorFeature(Feature):
    """
    Symétrie miroir d'un corps par rapport à un plan cartésien (XY, XZ ou YZ).
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Mirror",
        source_body_id: str = "",
        mirror_plane: PlaneType = PlaneType.YZ,
        join_with_source: bool = True
    ) -> None:
        super().__init__(feature_id, name)
        self.source_body_id = source_body_id
        self.mirror_plane = mirror_plane
        self.join_with_source = join_with_source
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Applique l'inversion de coordonnées selon le plan miroir."""
        updated = dict(existing_bodies)
        if self.source_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[self.source_body_id]
        # Inversion selon l'axe normal au plan
        if self.mirror_plane == PlaneType.YZ:
            # Plan X = 0 -> Inversion de l'axe X
            mirrored = base_solid.scale(-1.0, 1.0, 1.0)
        elif self.mirror_plane == PlaneType.XZ:
            # Plan Y = 0 -> Inversion de l'axe Y
            mirrored = base_solid.scale(1.0, -1.0, 1.0)
        else:
            # Plan Z = 0 -> Inversion de l'axe Z
            mirrored = base_solid.scale(1.0, 1.0, -1.0)

        if self.join_with_source:
            updated[self.source_body_id] = base_solid.union(mirrored)
        else:
            updated[self.body_id] = mirrored

        self.status = FeatureStatus.OK
        return updated


class HoleFeature(Feature):
    """
    Outil de perçage paramétrique (Alésage, trou traversant ou borgne).
    Soustrait automatiquement un cylindre à la position (X, Y) spécifiée.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Hole",
        target_body_id: str = "",
        pos_x: float = 0.0,
        pos_y: float = 0.0,
        diameter: float = 6.0,
        depth: float = 50.0,
        segments: int = 36
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.parameters = {
            "pos_x": float(pos_x),
            "pos_y": float(pos_y),
            "diameter": float(diameter),
            "depth": float(depth),
            "segments": float(segments),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Perce la pièce cible à la coordonnée demandée."""
        updated = dict(existing_bodies)
        if self.target_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[self.target_body_id]
        rad = max(0.01, self.parameters["diameter"] / 2.0)
        dep = max(0.01, self.parameters["depth"])
        segs = max(16, int(self.parameters["segments"]))
        px = self.parameters["pos_x"]
        py = self.parameters["pos_y"]

        # Créer le cylindre de découpe centré et le positionner
        cutter = make_cylinder(rad, dep, segments=segs, center=True).translate(Vector3D(px, py, 0.0))
        updated[self.target_body_id] = target.difference(cutter)
        self.status = FeatureStatus.OK
        return updated


class ShellFeature(Feature):
    """
    Évidement volumique (Shell) créant une coque mince avec épaisseur constante.
    Idéal pour la conception de boîtiers électroniques et pièces injectées.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Shell",
        target_body_id: str = "",
        wall_thickness: float = 2.0
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.parameters = {
            "wall_thickness": float(wall_thickness)
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Évide le solide en soustrayant une copie réduite de l'épaisseur."""
        updated = dict(existing_bodies)
        if self.target_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[self.target_body_id]
        b_min, b_max = target.bounding_box()
        dx = b_max.x - b_min.x
        dy = b_max.y - b_min.y
        dz = b_max.z - b_min.z
        t = self.parameters.get("wall_thickness", 2.0)

        # Vérification de sécurité géométrique
        if t <= 0.001 or dx <= 2.0 * t or dy <= 2.0 * t or dz <= 2.0 * t or dx <= 0.01 or dy <= 0.01 or dz <= 0.01:
            self.status = FeatureStatus.ERROR
            return updated

        # Calculer les facteurs de réduction homothétique
        sx = max(0.01, (dx - 2.0 * t) / dx)
        sy = max(0.01, (dy - 2.0 * t) / dy)
        sz = max(0.01, (dz - 2.0 * t) / dz)

        center = Vector3D((b_min.x + b_max.x) * 0.5, (b_min.y + b_max.y) * 0.5, (b_min.z + b_max.z) * 0.5)
        # Déplacer à l'origine, mettre à l'échelle, replacer
        inner = target.translate(center.scale(-1.0)).scale(sx, sy, sz).translate(center)
        updated[self.target_body_id] = target.difference(inner)
        self.status = FeatureStatus.OK
        return updated
