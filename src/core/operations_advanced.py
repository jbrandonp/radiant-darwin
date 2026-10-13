"""
Fonctionnalités volumiques 3D avancées style Autodesk Fusion 360 :
Révolution (Revolve), Répétitions linéaire et circulaire, Symétrie miroir,
Perçages/Alésages (Holes) et Évidement (Shell).
"""

from __future__ import annotations
from typing import Dict, List, Optional, Sequence, Tuple, Callable
import numpy as np
import manifold3d as m
from scipy.interpolate import interp1d

from src.core.types import BooleanOperation, FeatureStatus, Vector3D, Point2D, PlaneType
from src.core.geometry import Solid, make_cylinder, make_sphere, make_box, make_cone, _extract_sharp_edges
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
    Outil de perçage paramétrique avancé (FreeCAD PartDesign Hole).
    Prend en charge :
    - Perçage simple (simple cylindrical hole)
    - Lamage / Chambrage pour tête cylindrique CHC (Counterbore)
    - Fraisage conique pour tête fraisée FHC (Countersink)
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
        segments: int = 36,
        hole_type: str = "simple",
        cbore_dia: float = 10.0,
        cbore_depth: float = 6.0,
        csink_dia: float = 12.0,
        csink_angle: float = 90.0,
        x: Optional[float] = None,
        y: Optional[float] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.hole_type = str(hole_type).lower()
        actual_x = float(x if x is not None else pos_x)
        actual_y = float(y if y is not None else pos_y)
        self.pos_x = actual_x
        self.pos_y = actual_y
        self.diameter = float(diameter)
        self.depth = float(depth)
        self.cbore_dia = float(cbore_dia)
        self.cbore_depth = float(cbore_depth)
        self.csink_dia = float(csink_dia)
        self.csink_angle = float(csink_angle)
        self.parameters = {
            "pos_x": actual_x,
            "pos_y": actual_y,
            "diameter": float(diameter),
            "depth": float(depth),
            "segments": float(segments),
            "cbore_dia": float(cbore_dia),
            "cbore_depth": float(cbore_depth),
            "csink_dia": float(csink_dia),
            "csink_angle": float(csink_angle),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Perce la pièce cible à la coordonnée demandée avec lamage ou fraisage optionnel."""
        updated = dict(existing_bodies)
        target_key = self.target_body_id
        if target_key not in updated and f"body_{target_key}" in updated:
            target_key = f"body_{target_key}"
        elif target_key not in updated and updated:
            target_key = list(updated.keys())[0]

        if target_key not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[target_key]
        rad = max(0.01, self.parameters["diameter"] / 2.0)
        dep = max(0.01, self.parameters["depth"])
        segs = max(16, int(self.parameters["segments"]))
        px = self.parameters["pos_x"]
        py = self.parameters["pos_y"]

        b_min, b_max = target.bounding_box()
        top_z = b_max.z

        # 1. Cylindre principal débouchant depuis la face supérieure vers le bas
        cutter = make_cylinder(rad, dep + 0.1, segments=segs, center=False).translate(Vector3D(0.0, 0.0, top_z - dep))

        # 2. Lamage (Counterbore) ou Fraisage conique (Countersink)
        if self.hole_type == "counterbore":
            cb_rad = max(rad, self.parameters.get("cbore_dia", rad * 2.0) / 2.0)
            cb_dep = max(0.01, self.parameters.get("cbore_depth", 6.0))
            cbore_cyl = make_cylinder(cb_rad, cb_dep + 0.2, segments=segs, center=False).translate(Vector3D(0.0, 0.0, top_z - cb_dep))
            cutter = cutter.union(cbore_cyl)
        elif self.hole_type == "countersink":
            cs_rad = max(rad, self.parameters.get("csink_dia", rad * 2.0) / 2.0)
            cs_angle = max(30.0, min(150.0, self.parameters.get("csink_angle", 90.0)))
            half_angle_rad = np.radians(cs_angle / 2.0)
            cs_h = max(0.01, (cs_rad - rad) / float(np.tan(half_angle_rad)))
            csink_cone = make_cone(rad, cs_rad, cs_h + 0.2, segments=segs).translate(Vector3D(0.0, 0.0, top_z - cs_h))
            cutter = cutter.union(csink_cone)

        cutter_placed = cutter.translate(Vector3D(px, py, 0.0))
        updated[target_key] = target.difference(cutter_placed)
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


def _resample_profile(profile: Sequence[Point2D], target_count: int) -> np.ndarray:
    """Rééchantillonne uniformément un polygone 2D fermé en un nombre fixé de points."""
    if not profile or len(profile) < 3:
        theta = np.linspace(0, 2 * np.pi, target_count, endpoint=False)
        return np.column_stack([10.0 * np.cos(theta), 10.0 * np.sin(theta)])
    pts = np.array([[pt.u, pt.v] for pt in profile], dtype=np.float64)
    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[0:1]])
    deltas = np.diff(pts, axis=0)
    seg_lens = np.linalg.norm(deltas, axis=1)
    cum_lens = np.insert(np.cumsum(seg_lens), 0, 0.0)
    total_len = cum_lens[-1]
    if total_len < 1e-6:
        theta = np.linspace(0, 2 * np.pi, target_count, endpoint=False)
        return np.column_stack([10.0 * np.cos(theta), 10.0 * np.sin(theta)])
    target_dists = np.linspace(0.0, total_len, target_count, endpoint=False)
    fx = interp1d(cum_lens, pts[:, 0], kind="linear", assume_sorted=True)
    fy = interp1d(cum_lens, pts[:, 1], kind="linear", assume_sorted=True)
    return np.column_stack([fx(target_dists), fy(target_dists)])


class LoftFeature(Feature):
    """
    Lissage volumique paramétrique (Loft) reliant deux profils d'esquisse.
    Permet de créer des corps aérodynamiques, des carénages et des conduits de transition.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Loft",
        start_sketch_id: str = "",
        end_sketch_id: str = "",
        height_offset: float = 30.0,
        scale_top: float = 1.0,
        num_segments: int = 36,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.start_sketch_id = start_sketch_id
        self.end_sketch_id = end_sketch_id
        self.parameters = {
            "height_offset": float(height_offset),
            "scale_top": float(scale_top),
            "num_segments": float(num_segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le solide lissé étanche entre les deux sections."""
        if self.start_sketch_id not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        start_sketch = sketches[self.start_sketch_id]
        prof1 = start_sketch.get_primary_profile()
        if not prof1 or len(prof1) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        target_count = max(8, min(120, int(self.parameters.get("num_segments", 36))))
        pts1 = _resample_profile(prof1, target_count)

        if self.end_sketch_id in sketches and self.end_sketch_id != self.start_sketch_id:
            end_sketch = sketches[self.end_sketch_id]
            prof2 = end_sketch.get_primary_profile()
            pts2 = _resample_profile(prof2, target_count) if prof2 and len(prof2) >= 3 else None
        else:
            pts2 = None

        h_off = max(0.1, float(self.parameters.get("height_offset", 30.0)))
        if pts2 is None:
            scale = max(0.01, float(self.parameters.get("scale_top", 1.0)))
            c1x = float(np.mean(pts1[:, 0]))
            c1y = float(np.mean(pts1[:, 1]))
            pts2 = np.column_stack([c1x + (pts1[:, 0] - c1x) * scale, c1y + (pts1[:, 1] - c1y) * scale])

        p1_3d = np.column_stack([pts1, np.zeros(target_count)])
        p2_3d = np.column_stack([pts2, np.full(target_count, h_off)])
        all_pts = np.vstack([p1_3d, p2_3d])

        tris: List[List[int]] = []
        for i in range(target_count):
            next_i = (i + 1) % target_count
            tris.append([i, next_i, target_count + next_i])
            tris.append([i, target_count + next_i, target_count + i])

        c1 = np.array([float(np.mean(pts1[:, 0])), float(np.mean(pts1[:, 1])), 0.0])
        c2 = np.array([float(np.mean(pts2[:, 0])), float(np.mean(pts2[:, 1])), h_off])
        c1_idx = len(all_pts)
        c2_idx = c1_idx + 1
        all_pts = np.vstack([all_pts, c1[None, :], c2[None, :]])

        for i in range(target_count):
            next_i = (i + 1) % target_count
            tris.append([c1_idx, next_i, i])
            tris.append([c2_idx, target_count + i, target_count + next_i])

        mesh = m.Mesh(vert_properties=all_pts.astype(np.float32), tri_verts=np.array(tris, dtype=np.uint32))
        loft_manifold = m.Manifold(mesh)
        solid = Solid(loft_manifold, self.name)
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)


class SweepFeature(Feature):
    """
    Balayage volumique paramétrique (Sweep / Pipe) d'un profil 2D le long d'une trajectoire 3D.
    Idéal pour conduites, câbles, tuyauteries et rails.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Sweep",
        profile_sketch_id: str = "",
        trajectory_type: str = "arc",
        radius: float = 30.0,
        height: float = 40.0,
        turns: float = 1.0,
        num_steps: int = 24,
        segments: int = 24,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.profile_sketch_id = profile_sketch_id
        self.trajectory_type = trajectory_type
        self.parameters = {
            "radius": float(radius),
            "height": float(height),
            "turns": float(turns),
            "num_steps": float(num_steps),
            "segments": float(segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le solide balayé le long du chemin."""
        prof: Optional[Sequence[Point2D]] = None
        if self.profile_sketch_id in sketches:
            sk = sketches[self.profile_sketch_id]
            prof = sk.get_primary_profile()

        k_steps = max(4, min(100, int(self.parameters.get("num_steps", 24))))
        n_segs = max(6, min(60, int(self.parameters.get("segments", 24))))
        prof_2d = _resample_profile(prof if prof else [], n_segs)
        prof_2d -= np.mean(prof_2d, axis=0)

        rad = max(1.0, float(self.parameters.get("radius", 30.0)))
        h = max(1.0, float(self.parameters.get("height", 40.0)))
        turns = max(0.1, float(self.parameters.get("turns", 1.0)))

        # Construction de la trajectoire
        if self.trajectory_type == "helix":
            t = np.linspace(0.0, 1.0, k_steps)
            ang = 2.0 * np.pi * turns * t
            path_pts = np.column_stack([rad * np.cos(ang), rad * np.sin(ang), h * t])
        elif self.trajectory_type == "s_curve":
            t = np.linspace(0.0, 1.0, k_steps)
            path_pts = np.column_stack([t * h, rad * np.sin(2.0 * np.pi * t), np.zeros(k_steps)])
        elif self.trajectory_type == "linear":
            t = np.linspace(0.0, 1.0, k_steps)
            path_pts = np.column_stack([np.zeros(k_steps), np.zeros(k_steps), h * t])
        else:  # arc par défaut
            ang = np.linspace(0.0, np.pi * 0.5, k_steps)
            path_pts = np.column_stack([rad * np.cos(ang), rad * np.sin(ang), (h / max(1.0, k_steps)) * np.arange(k_steps)])

        tangents = np.gradient(path_pts, axis=0)
        norm_t = np.linalg.norm(tangents, axis=1, keepdims=True)
        norm_t[norm_t < 1e-9] = 1.0
        tangents /= norm_t

        all_slices: List[np.ndarray] = []
        for k in range(k_steps):
            pos = path_pts[k]
            t_vec = tangents[k]
            ref = np.array([0.0, 0.0, 1.0]) if abs(t_vec[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
            n_vec = np.cross(t_vec, ref)
            n_len = np.linalg.norm(n_vec)
            if n_len < 1e-9:
                n_vec = np.array([0.0, 1.0, 0.0])
            else:
                n_vec /= n_len
            b_vec = np.cross(t_vec, n_vec)

            slice_v = pos + np.outer(prof_2d[:, 0], n_vec) + np.outer(prof_2d[:, 1], b_vec)
            all_slices.append(slice_v)

        flat_pts = np.vstack(all_slices)
        tris: List[List[int]] = []
        for k in range(k_steps - 1):
            for i in range(n_segs):
                next_i = (i + 1) % n_segs
                v0 = k * n_segs + i
                v1 = k * n_segs + next_i
                v2 = (k + 1) * n_segs + next_i
                v3 = (k + 1) * n_segs + i
                tris.append([v0, v1, v2])
                tris.append([v0, v2, v3])

        start_c_idx = len(flat_pts)
        end_c_idx = start_c_idx + 1
        flat_pts = np.vstack([flat_pts, path_pts[0:1], path_pts[-1:]])

        for i in range(n_segs):
            next_i = (i + 1) % n_segs
            tris.append([start_c_idx, next_i, i])
            tris.append([end_c_idx, (k_steps - 1) * n_segs + i, (k_steps - 1) * n_segs + next_i])

        mesh = m.Mesh(vert_properties=flat_pts.astype(np.float32), tri_verts=np.array(tris, dtype=np.uint32))
        sweep_manifold = m.Manifold(mesh)
        solid = Solid(sweep_manifold, self.name)
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)


class FilletFeature(Feature):
    """
    Congé de raccordement paramétrique (Fillet) adoucissant les arêtes vives.
    Réduit les concentrations de contraintes mécaniques selon les standards industriels.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Fillet",
        target_body_id: str = "",
        radius: float = 2.0,
        segments: int = 16
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.parameters = {
            "radius": float(radius),
            "segments": float(segments),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Arrondit les arêtes du corps solide cible."""
        updated = dict(existing_bodies)
        if self.target_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[self.target_body_id]
        r = max(0.05, float(self.parameters.get("radius", 2.0)))
        segs = max(8, min(32, int(self.parameters.get("segments", 16))))
        b_min, b_max = target.bounding_box()
        dx = b_max.x - b_min.x
        dy = b_max.y - b_min.y
        dz = b_max.z - b_min.z

        if dx > 2.2 * r and dy > 2.2 * r and dz > 2.2 * r:
            sx = (dx - 2.0 * r) / dx
            sy = (dy - 2.0 * r) / dy
            sz = (dz - 2.0 * r) / dz
            center = Vector3D((b_min.x + b_max.x) * 0.5, (b_min.y + b_max.y) * 0.5, (b_min.z + b_max.z) * 0.5)
            shrunk = target.translate(center.scale(-1.0)).scale(sx, sy, sz).translate(center)
            sphere_kernel = m.Manifold.sphere(r, segs)
            rounded_m = shrunk.manifold.minkowski_sum(sphere_kernel)
            if not rounded_m.is_empty():
                updated[self.target_body_id] = Solid(rounded_m, f"{target.name}_Fillet")
                self.status = FeatureStatus.OK
                return updated

        # Fallback de lissage si trop étroit pour Minkowski
        updated[self.target_body_id] = target.simplify(r * 0.1)
        self.status = FeatureStatus.OK
        return updated


class ChamferFeature(Feature):
    """
    Chanfrein paramétrique (Chamfer) biseautant les arêtes nettes à 45°.
    Essentiel pour l'ébavurage, l'assemblage et la conformité d'usinage.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Chamfer",
        target_body_id: str = "",
        distance: float = 2.0,
        edges_mode: str = "all"
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.edges_mode = edges_mode
        self.parameters = {
            "distance": float(distance),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Applique les biseaux de découpe par plans inclinés sur les arêtes cibles."""
        updated = dict(existing_bodies)
        if self.target_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[self.target_body_id]
        d = max(0.01, float(self.parameters.get("distance", 2.0)))
        b_min, b_max = target.bounding_box()
        x0, x1 = b_min.x, b_max.x
        y0, y1 = b_min.y, b_max.y
        z0, z1 = b_min.z, b_max.z

        # Normalisation du biseau à 45°
        inv_sqrt2 = 1.0 / np.sqrt(2.0)
        cut_planes: List[Tuple[np.ndarray, float]] = []

        # Arêtes supérieures (Z = z1)
        if self.edges_mode in ("all", "top"):
            cut_planes.append((np.array([inv_sqrt2, 0.0, inv_sqrt2]), (x1 + z1 - d) * inv_sqrt2))
            cut_planes.append((np.array([-inv_sqrt2, 0.0, inv_sqrt2]), (-x0 + z1 - d) * inv_sqrt2))
            cut_planes.append((np.array([0.0, inv_sqrt2, inv_sqrt2]), (y1 + z1 - d) * inv_sqrt2))
            cut_planes.append((np.array([0.0, -inv_sqrt2, inv_sqrt2]), (-y0 + z1 - d) * inv_sqrt2))

        # Arêtes inférieures (Z = z0)
        if self.edges_mode in ("all", "bottom"):
            cut_planes.append((np.array([inv_sqrt2, 0.0, -inv_sqrt2]), (x1 - z0 - d) * inv_sqrt2))
            cut_planes.append((np.array([-inv_sqrt2, 0.0, -inv_sqrt2]), (-x0 - z0 - d) * inv_sqrt2))
            cut_planes.append((np.array([0.0, inv_sqrt2, -inv_sqrt2]), (y1 - z0 - d) * inv_sqrt2))
            cut_planes.append((np.array([0.0, -inv_sqrt2, -inv_sqrt2]), (-y0 - z0 - d) * inv_sqrt2))

        # Arêtes verticales
        if self.edges_mode in ("all", "vertical"):
            cut_planes.append((np.array([inv_sqrt2, inv_sqrt2, 0.0]), (x1 + y1 - d) * inv_sqrt2))
            cut_planes.append((np.array([inv_sqrt2, -inv_sqrt2, 0.0]), (x1 - y0 - d) * inv_sqrt2))
            cut_planes.append((np.array([-inv_sqrt2, inv_sqrt2, 0.0]), (-x0 + y1 - d) * inv_sqrt2))
            cut_planes.append((np.array([-inv_sqrt2, -inv_sqrt2, 0.0]), (-x0 - y0 - d) * inv_sqrt2))

        chamfered = target
        for norm_v, cut_dist in cut_planes:
            norm_3d = Vector3D(float(norm_v[0]), float(norm_v[1]), float(norm_v[2]))
            chamfered = chamfered.trim_by_plane(norm_3d.scale(-1.0), -cut_dist)

        updated[self.target_body_id] = chamfered
        self.status = FeatureStatus.OK
        return updated


class DraftFeature(Feature):
    """
    Dépouille de moulage paramétrique (Draft) inclinant les faces latérales.
    Garantit le démoulage facile des pièces injectées sous pression ou coulées en fonderie.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Draft",
        target_body_id: str = "",
        draft_angle_deg: float = 3.0,
        pull_axis: str = "Z"
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.pull_axis = pull_axis
        self.parameters = {
            "draft_angle": float(draft_angle_deg)
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Applique l'angle de dépouille en déformant les faces selon la direction de tirage."""
        updated = dict(existing_bodies)
        if self.target_body_id not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[self.target_body_id]
        angle_deg = self.parameters.get("draft_angle", 3.0)
        angle_rad = np.radians(angle_deg)
        b_min, b_max = target.bounding_box()
        h_z = max(0.1, b_max.z - b_min.z)
        tan_a = float(np.tan(angle_rad))
        cx = (b_min.x + b_max.x) * 0.5
        cy = (b_min.y + b_max.y) * 0.5

        def _draft_warp(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
            x, y, z = v[0], v[1], v[2]
            delta_z = z - b_min.z
            scale_fac = max(0.05, 1.0 - (delta_z / h_z) * tan_a)
            new_x = cx + (x - cx) * scale_fac
            new_y = cy + (y - cy) * scale_fac
            return (float(new_x), float(new_y), float(z))

        updated[self.target_body_id] = target.warp(_draft_warp)
        self.status = FeatureStatus.OK
        return updated


class PipeFeature(Feature):
    """
    Extrusion tubulaire le long d'une trajectoire 3D multi-axes (FreeCAD PartDesign Pipe).
    Permet de créer des conduites, tubulures, serpentins et guides-fils complexes.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Pipe",
        path_points: Optional[List[Tuple[float, float, float]]] = None,
        outer_radius: float = 6.0,
        inner_radius: float = 0.0,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.path_points: List[Tuple[float, float, float]] = (
            path_points if path_points is not None else [(0.0, 0.0, 0.0), (50.0, 0.0, 0.0), (50.0, 50.0, 0.0)]
        )
        self.operation = operation
        self.target_body_id = target_body_id
        self.outer_radius = float(outer_radius)
        self.inner_radius = float(inner_radius)
        self.parameters = {
            "outer_radius": float(outer_radius),
            "inner_radius": float(inner_radius),
        }
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère le tuyau 3D étanche le long de la trajectoire multi-points."""
        r_out = max(0.1, self.parameters["outer_radius"])
        r_in = max(0.0, min(r_out * 0.95, self.parameters.get("inner_radius", 0.0)))
        pts = [np.array(p, dtype=np.float32) for p in self.path_points]

        if len(pts) < 2:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        solid_pipe = self._build_pipe_solid(pts, r_out, self.name)
        if r_in > 0.05:
            inner_pipe = self._build_pipe_solid(pts, r_in, f"{self.name}_inner")
            solid_pipe = solid_pipe.difference(inner_pipe)

        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid_pipe, self.operation, self.body_id, self.target_body_id)

    @staticmethod
    def _build_pipe_solid(pts: List[np.ndarray], radius: float, name: str) -> Solid:
        """Construit un réseau de cylindres orientés et de rotules sphériques étanches."""
        solid_total: Optional[Solid] = None
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            v = p1 - p0
            length = float(np.linalg.norm(v))
            if length < 1e-4:
                continue

            v_norm = v / length
            z = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            dot = float(np.dot(z, v_norm))
            if abs(dot - 1.0) < 1e-6:
                rot_mat = np.eye(3, dtype=np.float32)
            elif abs(dot + 1.0) < 1e-6:
                rot_mat = np.diag([1.0, -1.0, -1.0]).astype(np.float32)
            else:
                k = np.cross(z, v_norm)
                k_len = float(np.linalg.norm(k))
                k = k / k_len
                c = dot
                s = k_len
                skew_k = np.array([
                    [0.0, -k[2], k[1]],
                    [k[2], 0.0, -k[0]],
                    [-k[1], k[0], 0.0]
                ], dtype=np.float32)
                rot_mat = np.eye(3, dtype=np.float32) + s * skew_k + (1.0 - c) * (skew_k @ skew_k)

            trans_mat = np.zeros((3, 4), dtype=np.float32)
            trans_mat[:3, :3] = rot_mat
            trans_mat[:3, 3] = p0

            cyl_m = m.Manifold.cylinder(length, radius, radius, 32).transform(trans_mat)
            seg_solid = Solid(cyl_m, f"seg_{i}")

            sph_m = m.Manifold.sphere(radius, 32).translate(list(p0))
            sph_solid = Solid(sph_m, f"joint_{i}")

            if solid_total is None:
                solid_total = seg_solid.union(sph_solid)
            else:
                solid_total = solid_total.union(seg_solid).union(sph_solid)

        last_sph = Solid(m.Manifold.sphere(radius, 32).translate(list(pts[-1])), "joint_end")
        if solid_total is None:
            return last_sph
        solid_total = solid_total.union(last_sph)
        solid_total.name = name
        return solid_total
