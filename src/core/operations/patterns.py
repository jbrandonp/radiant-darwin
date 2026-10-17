"""
Opérations de répétition géométrique : linéaire, circulaire, miroir et multi-transformations.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
import manifold3d as m

from src.core.types import FeatureStatus, Vector3D, PlaneType
from src.core.geometry import Solid
from src.core.feature import Feature, resolve_target_body_id
from src.core.sketch import Sketch2D

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
        src_key = resolve_target_body_id(self.source_body_id, updated)
        if not src_key:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[src_key]
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
            updated[src_key] = combined
        else:
            for idx, inst in enumerate(instances):
                updated[f"{src_key}_pat_{idx}"] = inst

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
        src_key = resolve_target_body_id(self.source_body_id, updated)
        if not src_key:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[src_key]
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
            updated[src_key] = combined
        else:
            for idx, inst in enumerate(instances):
                updated[f"{src_key}_circ_{idx}"] = inst

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
        src_key = resolve_target_body_id(self.source_body_id, updated)
        if not src_key:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[src_key]
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
            updated[src_key] = base_solid.union(mirrored)
        else:
            updated[self.body_id] = mirrored

        self.status = FeatureStatus.OK
        return updated


class MultiTransformStep:
    """Étape élémentaire de transformation dans un MultiTransform (FreeCAD PartDesign)."""

    def __init__(
        self,
        transform_type: str,
        count: int = 2,
        spacing: float = 20.0,
        axis: str = "X",
        total_angle: float = 360.0,
        mirror_plane: PlaneType = PlaneType.YZ,
        scale_factor: float = 1.0
    ) -> None:
        self.transform_type: str = transform_type.lower()
        self.count: int = max(1, count)
        self.spacing: float = float(spacing)
        self.axis: str = axis.upper()
        self.total_angle: float = float(total_angle)
        self.mirror_plane: PlaneType = mirror_plane
        self.scale_factor: float = float(scale_factor)


class MultiTransformFeature(Feature):
    """
    Fonctionnalité multi-transformation chaînée (FreeCAD PartDesign MultiTransform).
    Permet d'enchaîner plusieurs répétitions et symétries (linéaire, polaire, miroir)
    sur un corps dans une seule opération cohérente.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "MultiTransform",
        source_body_id: str = "",
        steps: Optional[List[MultiTransformStep]] = None,
        join_bodies: bool = True
    ) -> None:
        super().__init__(feature_id, name)
        self.source_body_id = source_body_id
        self.steps: List[MultiTransformStep] = steps if steps is not None else []
        self.join_bodies: bool = join_bodies
        self.body_id = f"body_{feature_id}"

    def add_linear_step(self, count: int = 3, spacing: float = 30.0, axis: str = "X") -> MultiTransformStep:
        """Ajoute une étape de répétition linéaire."""
        step = MultiTransformStep("linear", count=count, spacing=spacing, axis=axis)
        self.steps.append(step)
        return step

    def add_circular_step(self, count: int = 4, total_angle: float = 360.0, axis: str = "Z") -> MultiTransformStep:
        """Ajoute une étape de répétition circulaire."""
        step = MultiTransformStep("circular", count=count, total_angle=total_angle, axis=axis)
        self.steps.append(step)
        return step

    def add_mirror_step(self, mirror_plane: PlaneType = PlaneType.YZ) -> MultiTransformStep:
        """Ajoute une étape de symétrie miroir."""
        step = MultiTransformStep("mirror", mirror_plane=mirror_plane)
        self.steps.append(step)
        return step

    @staticmethod
    def _apply_linear_step(step: MultiTransformStep, solids: List[Solid]) -> List[Solid]:
        """Applique une étape de translation linéaire répétée."""
        result: List[Solid] = []
        for s in solids:
            for i in range(step.count):
                disp = float(i) * step.spacing
                if step.axis == "Y":
                    t = [0.0, disp, 0.0]
                elif step.axis == "Z":
                    t = [0.0, 0.0, disp]
                else:
                    t = [disp, 0.0, 0.0]
                result.append(s.translate(t))
        return result

    @staticmethod
    def _apply_circular_step(step: MultiTransformStep, solids: List[Solid]) -> List[Solid]:
        """Applique une étape de rotation circulaire répétée."""
        result: List[Solid] = []
        num = step.count
        step_ang = step.total_angle / float(num) if num > 1 else 0.0
        for s in solids:
            for i in range(num):
                ang = float(i) * step_ang
                if step.axis == "X":
                    rot = [ang, 0.0, 0.0]
                elif step.axis == "Y":
                    rot = [0.0, ang, 0.0]
                else:
                    rot = [0.0, 0.0, ang]
                result.append(s.rotate(rot[0], rot[1], rot[2]))
        return result

    @staticmethod
    def _apply_mirror_step(step: MultiTransformStep, solids: List[Solid]) -> List[Solid]:
        """Applique une étape de symétrie miroir."""
        result: List[Solid] = []
        for s in solids:
            result.append(s)
            if step.mirror_plane == PlaneType.XY:
                m_solid = s.scale(1.0, 1.0, -1.0)
            elif step.mirror_plane == PlaneType.XZ:
                m_solid = s.scale(1.0, -1.0, 1.0)
            else:
                m_solid = s.scale(-1.0, 1.0, 1.0)
            result.append(m_solid)
        return result

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Applique séquentiellement toutes les transformations configurées."""
        updated = dict(existing_bodies)
        src_key = resolve_target_body_id(self.source_body_id, updated)
        if not src_key or src_key not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        base_solid = updated[src_key]
        current_solids: List[Solid] = [base_solid]

        for step in self.steps:
            if step.transform_type == "linear":
                current_solids = self._apply_linear_step(step, current_solids)
            elif step.transform_type == "circular":
                current_solids = self._apply_circular_step(step, current_solids)
            elif step.transform_type == "mirror":
                current_solids = self._apply_mirror_step(step, current_solids)

        if not current_solids:
            self.status = FeatureStatus.ERROR
            return updated

        if self.join_bodies:
            result = current_solids[0]
            for s in current_solids[1:]:
                result = result.union(s)
            result.name = self.name
            updated[self.body_id] = result
        else:
            for idx, s in enumerate(current_solids):
                s.name = f"{self.name}_{idx+1}"
                updated[f"{self.body_id}_{idx+1}"] = s

        self.status = FeatureStatus.OK
        return updated


