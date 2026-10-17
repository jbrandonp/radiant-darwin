"""
Opérations d'usinage et de forme volumique : révolution, perçage, poche, rainure, nervure, découpe et tuyau.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np
import manifold3d as m

from src.core.types import BooleanOperation, FeatureStatus, Vector3D, Point2D, PlaneType
from src.core.geometry import Solid, make_cylinder, make_sphere, make_box, make_cone, extrude_polygon
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
                if k_len < 1e-7:
                    rot_mat = np.eye(3, dtype=np.float32)
                else:
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


class SplitFeature(Feature):
    """
    Fonctionnalité de découpe / partitionnement 3D par un plan (FreeCAD Part::Slice / Split).
    Découpe un corps solide selon un plan de référence (XY, XZ, YZ ou vecteur normal personnalisé).
    Permet de conserver la moitié positive, la moitié négative, ou les deux moitiés sous forme de corps distincts.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Split",
        target_body_id: str = "",
        plane: PlaneType = PlaneType.XY,
        plane_offset: float = 0.0,
        keep_side: str = "positive",
        normal_custom: Optional[Tuple[float, float, float]] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.target_body_id = target_body_id
        self.plane = plane
        self.plane_offset = float(plane_offset)
        self.keep_side = str(keep_side).lower()
        self.normal_custom = normal_custom
        self.parameters = {
            "plane_offset": self.plane_offset,
        }
        self.body_id = f"body_{feature_id}"

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Découpe le corps cible selon le plan de référence de façon instantanée et étanche."""
        updated = dict(existing_bodies)
        target_key = resolve_target_body_id(self.target_body_id, updated)
        if not target_key or target_key not in updated:
            self.status = FeatureStatus.ERROR
            return updated

        target_solid = updated[target_key]
        if target_solid.is_empty():
            self.status = FeatureStatus.OK
            return updated

        if self.normal_custom is not None:
            nx, ny, nz = self.normal_custom
            length = float(np.sqrt(nx * nx + ny * ny + nz * nz))
            normal = (nx / length, ny / length, nz / length) if length > 1e-6 else (0.0, 0.0, 1.0)
        elif self.plane == PlaneType.XZ:
            normal = (0.0, 1.0, 0.0)
        elif self.plane == PlaneType.YZ:
            normal = (1.0, 0.0, 0.0)
        else:
            normal = (0.0, 0.0, 1.0)

        offset = float(self.parameters.get("plane_offset", self.plane_offset))

        if self.keep_side == "negative":
            inv_normal = (-normal[0], -normal[1], -normal[2])
            res = target_solid.trim_by_plane(inv_normal, -offset)
            res.name = self.name
            updated[target_key] = res
        elif self.keep_side == "both":
            s_pos, s_neg = target_solid.split_by_plane(normal, offset)
            s_pos.name = f"{self.name}_1"
            s_neg.name = f"{self.name}_2"
            updated[target_key] = s_pos
            updated[f"{target_key}_split_2"] = s_neg
        else:  # "positive"
            res = target_solid.trim_by_plane(normal, offset)
            res.name = self.name
            updated[target_key] = res

        self.status = FeatureStatus.OK
        return updated


