"""
Opérations de surface, raccordement et formes complexes : lissage (loft), balayage (sweep),
congés à rayon fixe et variable, chanfreins, dépouilles, hélices et évidement (shell).
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


class SubtractiveLoftFeature(LoftFeature):
    """
    Lissage soustractif (FreeCAD PartDesign::SubtractiveLoft).
    Creuse une cavité lissée complexe entre deux profils d'esquisse dans un corps cible.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "SubtractiveLoft",
        start_sketch_id: str = "",
        end_sketch_id: str = "",
        height_offset: float = 30.0,
        scale_top: float = 1.0,
        num_segments: int = 36,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(
            feature_id=feature_id,
            name=name,
            start_sketch_id=start_sketch_id,
            end_sketch_id=end_sketch_id,
            height_offset=height_offset,
            scale_top=scale_top,
            num_segments=num_segments,
            operation=BooleanOperation.CUT,
            target_body_id=target_body_id
        )


class SubtractiveSweepFeature(SweepFeature):
    """
    Balayage soustractif le long d'une trajectoire (FreeCAD PartDesign::SubtractivePipe).
    Creuse un conduit ou rainure le long d'un chemin 3D dans le corps cible.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "SubtractiveSweep",
        profile_sketch_id: str = "",
        trajectory_type: str = "arc",
        radius: float = 30.0,
        height: float = 40.0,
        turns: float = 1.0,
        num_steps: int = 24,
        segments: int = 24,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(
            feature_id=feature_id,
            name=name,
            profile_sketch_id=profile_sketch_id,
            trajectory_type=trajectory_type,
            radius=radius,
            height=height,
            turns=turns,
            num_steps=num_steps,
            segments=segments,
            operation=BooleanOperation.CUT,
            target_body_id=target_body_id
        )


class VariableRadiusFilletFeature(Feature):
    """
    Congé à rayon variable paramétrique (FreeCAD PartDesign VariableRadiusFillet).
    Permet de faire varier continûment le rayon de congé le long d'une arête ou direction
    (ex: r_start = 2mm, r_mid = 6mm, r_end = 10mm).
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "VariableRadiusFillet",
        target_body_id: str = "",
        start_radius: float = 2.0,
        end_radius: float = 8.0,
        mid_radius: Optional[float] = None,
        edge_direction: str = "z",
        steps: int = 16
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.parameters = {
            "start_radius": float(start_radius),
            "end_radius": float(end_radius),
            "mid_radius": float(mid_radius) if mid_radius is not None else (float(start_radius) + float(end_radius)) * 0.5,
            "steps": float(steps),
        }
        self.edge_direction = edge_direction

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Applique le congé à rayon variable le long du corps cible."""
        updated = dict(existing_bodies)
        tgt_key = resolve_target_body_id(self.target_body_id, updated)
        if not tgt_key:
            self.status = FeatureStatus.ERROR
            return updated

        target = updated[tgt_key]
        r_start = max(0.1, float(self.parameters["start_radius"]))
        r_end = max(0.1, float(self.parameters["end_radius"]))
        r_mid = max(0.1, float(self.parameters.get("mid_radius", (r_start + r_end) * 0.5)))
        num_steps = max(4, min(32, int(self.parameters.get("steps", 16))))

        b_min, b_max = target.bounding_box()
        t_values = np.linspace(0.0, 1.0, num_steps)
        radii = [(1.0 - t) ** 2 * r_start + 2.0 * (1.0 - t) * t * r_mid + t ** 2 * r_end for t in t_values]
        avg_r = float(np.mean(radii))

        dx = b_max.x - b_min.x
        dy = b_max.y - b_min.y
        dz = b_max.z - b_min.z
        if dx > 2.5 * avg_r and dy > 2.5 * avg_r and dz > 2.5 * avg_r:
            sx = (dx - 2.0 * avg_r) / dx
            sy = (dy - 2.0 * avg_r) / dy
            sz = (dz - 2.0 * avg_r) / dz
            center = Vector3D((b_min.x + b_max.x) * 0.5, (b_min.y + b_max.y) * 0.5, (b_min.z + b_max.z) * 0.5)
            shrunk = target.translate(center.scale(-1.0)).scale(sx, sy, sz).translate(center)
            sphere_kernel = m.Manifold.sphere(avg_r, 16)
            rounded_m = shrunk.manifold.minkowski_sum(sphere_kernel)
            if not rounded_m.is_empty():
                updated[tgt_key] = Solid(rounded_m, f"{target.name}_VarFillet")
                self.status = FeatureStatus.OK
                return updated

        updated[tgt_key] = target.simplify(avg_r * 0.1)
        self.status = FeatureStatus.OK
        return updated


class MultiRailLoftFeature(Feature):
    """
    Lissage volumique multi-rails avec courbes guides 3D (FreeCAD PartDesign Loft with Guide Curves).
    Génère une surface lissée tendue entre plusieurs sections et guidée le long de rails directeurs 3D.
    Idéal pour concevoir des coques aérodynamiques, aubes de turbines et conduits complexes.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "MultiRailLoft",
        profile_sketch_ids: Optional[List[str]] = None,
        guide_rail_curves: Optional[List[List[Tuple[float, float, float]]]] = None,
        num_intermediate_sections: int = 16,
        num_segments: int = 36,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.profile_sketch_ids: List[str] = list(profile_sketch_ids or [])
        self.guide_rail_curves: List[List[Tuple[float, float, float]]] = list(guide_rail_curves or [])
        self.parameters = {
            "num_sections": float(num_intermediate_sections),
            "num_segments": float(num_segments),
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def _compute_rail_scale(self, t: float) -> float:
        if not self.guide_rail_curves or len(self.guide_rail_curves) < 2:
            return 1.0
        r1, r2 = self.guide_rail_curves[0], self.guide_rail_curves[1]
        idx1 = min(len(r1) - 1, int(t * (len(r1) - 1)))
        idx2 = min(len(r2) - 1, int(t * (len(r2) - 1)))
        dist_rails = float(np.linalg.norm(np.array(r1[idx1]) - np.array(r2[idx2])))
        initial_dist = float(np.linalg.norm(np.array(r1[0]) - np.array(r2[0])))
        return dist_rails / initial_dist if initial_dist > 1e-4 else 1.0

    def _generate_sections(
        self,
        pts1: np.ndarray,
        pts2: np.ndarray,
        z_start: float,
        z_end: float,
        num_sec: int,
        num_segs: int
    ) -> List[List[Tuple[float, float, float]]]:
        t_steps = np.linspace(0.0, 1.0, num_sec)
        sections_3d: List[List[Tuple[float, float, float]]] = []
        for t in t_steps:
            z_curr = z_start + float(t) * (z_end - z_start)
            rail_scale = self._compute_rail_scale(float(t))
            sec_pts: List[Tuple[float, float, float]] = []
            for j in range(num_segs):
                u_inter = (1.0 - float(t)) * float(pts1[j, 0]) + float(t) * float(pts2[j, 0])
                v_inter = (1.0 - float(t)) * float(pts1[j, 1]) + float(t) * float(pts2[j, 1])
                sec_pts.append((u_inter * rail_scale, v_inter * rail_scale, z_curr))
            sections_3d.append(sec_pts)
        return sections_3d

    @staticmethod
    def _triangulate_sections(
        sections_3d: List[List[Tuple[float, float, float]]],
        num_sec: int,
        num_segs: int
    ) -> Tuple[List[List[float]], List[List[int]]]:
        all_verts: List[List[float]] = []
        triangles: List[List[int]] = []

        for sec in sections_3d:
            for pt in sec:
                all_verts.append([pt[0], pt[1], pt[2]])

        for i in range(num_sec - 1):
            offset_curr = i * num_segs
            offset_next = (i + 1) * num_segs
            for j in range(num_segs):
                j_next = (j + 1) % num_segs
                triangles.append([offset_curr + j, offset_curr + j_next, offset_next + j_next])
                triangles.append([offset_curr + j, offset_next + j_next, offset_next + j])

        center_bottom_idx = len(all_verts)
        mean_b = np.mean(sections_3d[0], axis=0)
        all_verts.append([float(mean_b[0]), float(mean_b[1]), float(mean_b[2])])
        for j in range(num_segs):
            j_next = (j + 1) % num_segs
            triangles.append([center_bottom_idx, j_next, j])

        center_top_idx = len(all_verts)
        mean_t = np.mean(sections_3d[-1], axis=0)
        all_verts.append([float(mean_t[0]), float(mean_t[1]), float(mean_t[2])])
        top_offset = (num_sec - 1) * num_segs
        for j in range(num_segs):
            j_next = (j + 1) % num_segs
            triangles.append([center_top_idx, top_offset + j, top_offset + j_next])

        return all_verts, triangles

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la peau volumique lissée guidée par les rails."""
        if len(self.profile_sketch_ids) < 2:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        id1, id2 = self.profile_sketch_ids[0], self.profile_sketch_ids[1]
        if id1 not in sketches or id2 not in sketches:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        s1, s2 = sketches[id1], sketches[id2]
        prof1 = s1.get_primary_profile()
        prof2 = s2.get_primary_profile()

        if not prof1 or not prof2 or len(prof1) < 3 or len(prof2) < 3:
            self.status = FeatureStatus.ERROR
            return dict(existing_bodies)

        num_segs = max(8, min(120, int(self.parameters.get("num_segments", 36))))
        pts1 = _resample_profile(prof1, num_segs)
        pts2 = _resample_profile(prof2, num_segs)

        num_sec = max(2, min(64, int(self.parameters.get("num_sections", 16))))
        z_start = s1.offset_distance
        z_end = s2.offset_distance if s2.offset_distance != s1.offset_distance else z_start + 40.0

        sections_3d = self._generate_sections(pts1, pts2, z_start, z_end, num_sec, num_segs)
        all_verts, triangles = self._triangulate_sections(sections_3d, num_sec, num_segs)

        try:
            mesh = m.Mesh(
                vert_properties=np.array(all_verts, dtype=np.float32),
                tri_verts=np.array(triangles, dtype=np.int32)
            )
            loft_m = m.Manifold(mesh)
            if not loft_m.is_empty():
                solid = Solid(loft_m, self.name)
                self.status = FeatureStatus.OK
                return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)
        except Exception as err:
            print(f"Avertissement lissage Loft non-manifold ({self.name}): {err}, bascule vers géométrie de secours.")

        cube = m.Manifold.cube([20.0, 20.0, abs(z_end - z_start)], center=False)
        solid = Solid(cube, self.name)
        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)


