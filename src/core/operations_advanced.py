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
from src.core.geometry import Solid, make_cylinder, make_sphere, make_box, make_cone, extrude_polygon, _extract_sharp_edges
from src.core.feature import Feature, _apply_boolean_operation, resolve_target_body_id
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
        tgt_key = resolve_target_body_id(self.target_body_id, updated)
        if not tgt_key:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[tgt_key]
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
        updated[tgt_key] = target.difference(inner)
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
        tgt_key = resolve_target_body_id(self.target_body_id, updated)
        if not tgt_key:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[tgt_key]
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
                updated[tgt_key] = Solid(rounded_m, f"{target.name}_Fillet")
                self.status = FeatureStatus.OK
                return updated

        # Fallback de lissage si trop étroit pour Minkowski
        updated[tgt_key] = target.simplify(r * 0.1)
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
        tgt_key = resolve_target_body_id(self.target_body_id, updated)
        if not tgt_key:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[tgt_key]
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

        updated[tgt_key] = chamfered
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
        pull_axis: str = "Z",
        draft_angle: Optional[float] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.pull_axis = str(pull_axis).upper() if pull_axis else "Z"
        actual_angle = float(draft_angle if draft_angle is not None else draft_angle_deg)
        self.parameters = {
            "draft_angle": actual_angle
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Applique l'angle de dépouille en déformant les faces selon la direction de tirage."""
        updated = dict(existing_bodies)
        tgt_key = resolve_target_body_id(self.target_body_id, updated)
        if not tgt_key:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[tgt_key]
        angle_deg = max(-60.0, min(60.0, float(self.parameters.get("draft_angle", 3.0))))
        angle_rad = np.radians(angle_deg)
        b_min, b_max = target.bounding_box()
        tan_a = float(np.tan(angle_rad))

        axis_up = self.pull_axis.upper() if self.pull_axis else "Z"
        if axis_up == "X":
            h_dim = max(0.1, b_max.x - b_min.x)
            cy = (b_min.y + b_max.y) * 0.5
            cz = (b_min.z + b_max.z) * 0.5
            def _draft_warp(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
                x, y, z = v[0], v[1], v[2]
                delta = x - b_min.x
                scale_fac = max(0.05, 1.0 - (delta / h_dim) * tan_a)
                return (float(x), float(cy + (y - cy) * scale_fac), float(cz + (z - cz) * scale_fac))
        elif axis_up == "Y":
            h_dim = max(0.1, b_max.y - b_min.y)
            cx = (b_min.x + b_max.x) * 0.5
            cz = (b_min.z + b_max.z) * 0.5
            def _draft_warp(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
                x, y, z = v[0], v[1], v[2]
                delta = y - b_min.y
                scale_fac = max(0.05, 1.0 - (delta / h_dim) * tan_a)
                return (float(cx + (x - cx) * scale_fac), float(y), float(cz + (z - cz) * scale_fac))
        else:
            h_dim = max(0.1, b_max.z - b_min.z)
            cx = (b_min.x + b_max.x) * 0.5
            cy = (b_min.y + b_max.y) * 0.5
            def _draft_warp(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
                x, y, z = v[0], v[1], v[2]
                delta = z - b_min.z
                scale_fac = max(0.05, 1.0 - (delta / h_dim) * tan_a)
                return (float(cx + (x - cx) * scale_fac), float(cy + (y - cy) * scale_fac), float(z))

        updated[tgt_key] = target.warp(_draft_warp)
        self.status = FeatureStatus.OK
        return updated
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
            v_start = (pts[0] - pts[1])
            len_start = float(np.linalg.norm(v_start))
            p_start_ext = pts[0] + (v_start / len_start) * (r_out * 1.5) if len_start > 1e-4 else pts[0]

            v_end = (pts[-1] - pts[-2])
            len_end = float(np.linalg.norm(v_end))
            p_end_ext = pts[-1] + (v_end / len_end) * (r_out * 1.5) if len_end > 1e-4 else pts[-1]

            inner_pts = [p_start_ext] + pts[1:-1] + [p_end_ext]
            inner_pipe = self._build_pipe_solid(inner_pts, r_in, f"{self.name}_inner")
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


class PocketFeature(Feature):
    """
    Fonctionnalité de cavité / poche soustractive (FreeCAD PartDesign Pocket).
    Permet de creuser une forme 2D dans un corps avec profondeur finie ou traversante (through_all).
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Pocket",
        sketch_id: str = "",
        depth: float = 10.0,
        through_all: bool = False,
        reversed_dir: bool = False,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.sketch_id = sketch_id
        self.through_all = through_all
        self.reversed_dir = reversed_dir
        self.target_body_id = target_body_id
        self.parameters = {
            "depth": float(depth),
            "through_all": 1.0 if through_all else 0.0,
            "reversed": 1.0 if reversed_dir else 0.0,
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Creuse la cavité dans le corps cible par soustraction booléenne."""
        if self.sketch_id not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        sketch = sketches[self.sketch_id]
        profile = sketch.get_primary_profile()
        if not profile or len(profile) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        updated = dict(existing_bodies)
        target_key = resolve_target_body_id(self.target_body_id, updated)
        if not target_key or target_key not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target_body = updated[target_key]
        min_b, max_b = target_body.bounding_box()
        diag_span = float(np.linalg.norm(np.array([max_b.x - min_b.x, max_b.y - min_b.y, max_b.z - min_b.z])))

        is_through = bool(self.through_all or self.parameters.get("through_all", 0.0) > 0.5)
        is_rev = bool(self.reversed_dir or self.parameters.get("reversed", 0.0) > 0.5)

        if is_through:
            cut_depth = max(100.0, diag_span * 2.0)
            # Traverse complètement le solide des deux côtés du plan
            tool_solid = extrude_polygon(
                profile,
                2.0 * cut_depth,
                plane=sketch.plane,
                plane_offset=sketch.offset_distance - cut_depth,
                name=f"{self.name}_cutter"
            )
        else:
            cut_depth = max(0.001, self.parameters.get("depth", 10.0))
            h = -cut_depth if is_rev else cut_depth
            tool_solid = extrude_polygon(
                profile,
                h,
                plane=sketch.plane,
                plane_offset=sketch.offset_distance,
                name=f"{self.name}_cutter"
            )

        try:
            result_body = target_body.difference(tool_solid)
            if not is_through and abs(result_body.volume() - target_body.volume()) < 1e-4:
                # Si l'extrusion dans le sens h n'a touché aucune matière, on teste dans le sens opposé
                alt_tool = extrude_polygon(
                    profile,
                    -h,
                    plane=sketch.plane,
                    plane_offset=sketch.offset_distance,
                    name=f"{self.name}_cutter"
                )
                alt_result = target_body.difference(alt_tool)
                if abs(alt_result.volume() - target_body.volume()) > 1e-4:
                    result_body = alt_result

            updated[target_key] = result_body
            self.status = FeatureStatus.OK
        except Exception:
            self.status = FeatureStatus.ERROR

        return updated


class DatumPlaneFeature(Feature):
    """
    Plan de référence paramétrique auxiliaire (FreeCAD PartDesign Datum Plane).
    Définit un plan de construction décalé ou orienté pour y attacher des esquisses.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Datum Plane",
        base_plane: PlaneType = PlaneType.XY,
        offset_distance: float = 0.0
    ) -> None:
        super().__init__(feature_id, name)
        self.base_plane = base_plane
        self.parameters = {
            "offset_distance": float(offset_distance),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Un plan de référence est un élément de construction non volumique."""
        self.status = FeatureStatus.OK
        return dict(existing_bodies)

    def attach_to_sketch(self, sketch: Sketch2D) -> None:
        """Associe ce plan de référence à une esquisse pour définir son plan et son décalage."""
        sketch.plane = self.base_plane
        sketch.offset_distance = self.parameters.get("offset_distance", 0.0)


class GrooveFeature(Feature):
    """
    Fonctionnalité de gorge / rainure de révolution soustractive (FreeCAD PartDesign Groove).
    Effectue une révolution du profil d'esquisse et la soustrait du corps cible
    pour créer des gorges de joints toriques, poulies, cannelures et alésages tournés.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Groove",
        sketch_id: str = "",
        angle_deg: float = 360.0,
        segments: int = 48,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.sketch_id = sketch_id
        self.target_body_id = target_body_id
        self.parameters = {
            "angle": float(angle_deg),
            "segments": float(segments),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Exécute la révolution soustractive du profil d'esquisse."""
        if self.sketch_id not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        sketch = sketches[self.sketch_id]
        profile = sketch.get_primary_profile()
        if not profile or len(profile) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        updated = dict(existing_bodies)
        target_key = resolve_target_body_id(self.target_body_id, updated)
        if not target_key or target_key not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target_body = updated[target_key]
        poly_coords: List[List[float]] = [[pt.u, pt.v] for pt in profile]
        cs = m.CrossSection([poly_coords])
        angle = max(1.0, min(360.0, self.parameters.get("angle", 360.0)))
        segs = max(12, int(self.parameters.get("segments", 48)))

        cutter_manifold = m.Manifold.revolve(cs, segs, angle)
        if sketch.plane == PlaneType.XZ:
            cutter_manifold = cutter_manifold.rotate([90.0, 0.0, 0.0])
        elif sketch.plane == PlaneType.YZ:
            cutter_manifold = cutter_manifold.rotate([0.0, -90.0, 0.0])

        cutter_solid = Solid(cutter_manifold, f"{self.name}_cutter")
        try:
            result_body = target_body.difference(cutter_solid)
            updated[target_key] = result_body
            self.status = FeatureStatus.OK
        except Exception:
            self.status = FeatureStatus.ERROR

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
            new_set: List[Solid] = []
            if step.transform_type == "linear":
                for s in current_solids:
                    for i in range(step.count):
                        disp = float(i) * step.spacing
                        if step.axis == "Y":
                            t = [0.0, disp, 0.0]
                        elif step.axis == "Z":
                            t = [0.0, 0.0, disp]
                        else:
                            t = [disp, 0.0, 0.0]
                        new_set.append(s.translate(t))

            elif step.transform_type == "circular":
                for s in current_solids:
                    num = step.count
                    step_ang = step.total_angle / float(num) if num > 1 else 0.0
                    for i in range(num):
                        ang = float(i) * step_ang
                        if step.axis == "X":
                            rot = [ang, 0.0, 0.0]
                        elif step.axis == "Y":
                            rot = [0.0, ang, 0.0]
                        else:
                            rot = [0.0, 0.0, ang]
                        new_set.append(s.rotate(rot[0], rot[1], rot[2]))

            elif step.transform_type == "mirror":
                for s in current_solids:
                    new_set.append(s)
                    if step.mirror_plane == PlaneType.XY:
                        m_solid = s.scale(1.0, 1.0, -1.0)
                    elif step.mirror_plane == PlaneType.XZ:
                        m_solid = s.scale(1.0, -1.0, 1.0)
                    else:
                        m_solid = s.scale(-1.0, 1.0, 1.0)
                    new_set.append(m_solid)

            if new_set:
                current_solids = new_set

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


class HelixFeature(Feature):
    """
    Fonctionnalité paramétrique d'hélice 3D (ressorts, filets de vis, vis d'Archimède, goujures).
    Équivalent direct de FreeCAD PartDesign::AdditiveHelix et PartDesign::SubtractiveHelix.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Helix",
        pitch: float = 10.0,
        height: float = 40.0,
        turns: Optional[float] = None,
        radius: float = 15.0,
        wire_radius: float = 2.0,
        cone_angle: float = 0.0,
        is_left_handed: bool = False,
        axis: str = "Z",
        is_subtractive: bool = False,
        operation: Optional[BooleanOperation] = None,
        target_body_id: Optional[str] = None,
        segments_per_turn: int = 24
    ) -> None:
        super().__init__(feature_id, name)
        safe_pitch = max(0.1, abs(pitch))
        if turns is not None:
            safe_turns = max(0.1, abs(turns))
            safe_height = safe_turns * safe_pitch
        else:
            safe_height = max(0.1, abs(height))
            safe_turns = safe_height / safe_pitch

        self.pitch = safe_pitch
        self.height = safe_height
        self.turns = safe_turns
        self.radius = max(0.1, abs(radius))
        self.wire_radius = max(0.05, abs(wire_radius))
        self.cone_angle = float(cone_angle)
        self.is_left_handed = bool(is_left_handed)
        self.axis = str(axis).upper()
        self.is_subtractive = bool(is_subtractive)
        self.segments_per_turn = max(12, int(segments_per_turn))
        self.target_body_id = target_body_id

        if operation is not None:
            self.operation = operation
        else:
            self.operation = BooleanOperation.CUT if self.is_subtractive else BooleanOperation.NEW_BODY

        self.parameters = {
            "pitch": self.pitch,
            "height": self.height,
            "turns": self.turns,
            "radius": self.radius,
            "wire_radius": self.wire_radius,
            "cone_angle": self.cone_angle,
            "is_left_handed": 1.0 if self.is_left_handed else 0.0,
            "is_subtractive": 1.0 if self.is_subtractive else 0.0,
        }
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère l'hélice volumique 3D étanche et l'intègre au modèle (ajout ou soustraction)."""
        p = max(0.1, self.parameters.get("pitch", self.pitch))
        h = max(0.1, self.parameters.get("height", self.height))
        r = max(0.1, self.parameters.get("radius", self.radius))
        wr = max(0.05, self.parameters.get("wire_radius", self.wire_radius))
        c_ang = float(self.parameters.get("cone_angle", self.cone_angle))
        left_h = bool(self.parameters.get("is_left_handed", 1.0 if self.is_left_handed else 0.0) > 0.5)

        turns = h / p
        total_pts = max(16, int(turns * self.segments_per_turn))
        t_vals = np.linspace(0.0, 1.0, total_pts, endpoint=True)

        hand_sign = -1.0 if left_h else 1.0
        thetas = 2.0 * np.pi * turns * t_vals * hand_sign
        zs = t_vals * h

        if abs(c_ang) > 1e-4:
            tan_cone = float(np.tan(np.radians(c_ang)))
            rs = np.maximum(0.1, r + zs * tan_cone)
        else:
            rs = np.full_like(zs, r)

        xs = rs * np.cos(thetas)
        ys = rs * np.sin(thetas)
        pts: List[np.ndarray] = [np.array([x, y, z], dtype=np.float32) for x, y, z in zip(xs, ys, zs)]

        cyls: List[m.Manifold] = []
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            v = p1 - p0
            seg_len = float(np.linalg.norm(v))
            if seg_len < 1e-4:
                continue

            v_norm = v / seg_len
            z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            dot = float(np.dot(z_axis, v_norm))
            if abs(dot - 1.0) < 1e-6:
                rot_mat = np.eye(3, dtype=np.float32)
            elif abs(dot + 1.0) < 1e-6:
                rot_mat = np.diag([1.0, -1.0, -1.0]).astype(np.float32)
            else:
                k = np.cross(z_axis, v_norm)
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

            cyl_m = m.Manifold.cylinder(seg_len, wr, wr, 16).transform(trans_mat)
            sph_m = m.Manifold.sphere(wr, 16).translate(list(p0))
            cyls.append(cyl_m)
            cyls.append(sph_m)

        cyls.append(m.Manifold.sphere(wr, 16).translate(list(pts[-1])))
        if not cyls:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        helix_manifold = m.Manifold.batch_boolean(cyls, m.OpType.Add)

        # Orientation de l'axe de l'hélice
        if self.axis == "X":
            helix_manifold = helix_manifold.rotate([0.0, 90.0, 0.0])
        elif self.axis == "Y":
            helix_manifold = helix_manifold.rotate([-90.0, 0.0, 0.0])

        solid = Solid(helix_manifold, self.name)
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)


class RibFeature(Feature):
    """
    Fonctionnalité de nervure / renfort de structure (FreeCAD PartDesign::Rib).
    Extrude un profil d'esquisse (triangle de gousset, nervure de raidissement)
    de manière symétrique par rapport au plan d'esquisse et le fusionne avec le corps cible.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Rib",
        sketch_id: str = "",
        thickness: float = 4.0,
        symmetric: bool = True,
        draft_angle: float = 0.0,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.sketch_id = sketch_id
        self.thickness = max(0.1, abs(thickness))
        self.symmetric = symmetric
        self.draft_angle = float(draft_angle)
        self.operation = BooleanOperation.JOIN
        self.target_body_id = target_body_id
        self.parameters = {
            "thickness": self.thickness,
            "symmetric": 1.0 if self.symmetric else 0.0,
            "draft_angle": self.draft_angle,
        }
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la nervure volumique et la fusionne avec le corps cible."""
        if self.sketch_id not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        sketch = sketches[self.sketch_id]
        profile = sketch.get_primary_profile()
        if not profile or len(profile) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        t = max(0.1, self.parameters.get("thickness", self.thickness))
        sym = bool(self.parameters.get("symmetric", 1.0 if self.symmetric else 0.0) > 0.5)
        draft = float(self.parameters.get("draft_angle", self.draft_angle))

        rib_solid = extrude_polygon(
            profile,
            t,
            plane=sketch.plane,
            plane_offset=sketch.offset_distance,
            symmetric=sym,
            taper_angle=draft,
            name=self.name
        )
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, rib_solid, self.operation, self.body_id, self.target_body_id)


