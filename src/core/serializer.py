"""
Moteur de sérialisation et persistance de projets CAO (.cadproj / JSON).
Permet de sauvegarder l'arbre complet d'historique paramétrique et les esquisses sur disque
et de recharger le projet avec recalcul automatique de la géométrie 3D.
Architecture modulaire et découplée pour garantir une maintenabilité maximale.
"""

from __future__ import annotations
import json
import os
import zipfile
from typing import Dict, List, Optional, Tuple, Union

# Modèle de typage strict pour données JSON arborescentes
JSONPrimitive = Union[str, int, float, bool, None]
JSONValue = Union[
    JSONPrimitive,
    List[JSONPrimitive],
    Dict[str, JSONPrimitive],
    List[Dict[str, Union[JSONPrimitive, List[float], List[List[float]]]]],
    Dict[str, Union[JSONPrimitive, List[float], Dict[str, JSONPrimitive]]],
    List[Dict[str, Union[str, float, List[Dict[str, Union[str, bool, int, float, List[List[float]]]]]]]]
]

from src.core.document import CADDocument
from src.core.types import PlaneType, BooleanOperation, Point2D
from src.core.sketch import Sketch2D
from src.core.feature import (
    Feature, BoxFeature, CylinderFeature, SphereFeature, ExtrudeFeature, BooleanFeature,
    ConeFeature, TorusFeature, WedgeFeature
)
from src.core.operations_advanced import (
    RevolveFeature, LinearPatternFeature, CircularPatternFeature,
    MirrorFeature, HoleFeature, ShellFeature, PipeFeature,
    LoftFeature, SweepFeature, FilletFeature, ChamferFeature, DraftFeature,
    PocketFeature, DatumPlaneFeature, GrooveFeature, MultiTransformFeature, MultiTransformStep,
    HelixFeature, RibFeature, SplitFeature, SubtractiveLoftFeature, SubtractiveSweepFeature,
    DynamicDatumPlaneFeature, DatumAttachmentMode, VariableRadiusFilletFeature, MultiRailLoftFeature
)
from src.core.fasteners import FastenerFeature
from src.sheetmetal.sheet_metal import SheetMetalFeature


class SketchSerializer:
    """Gestionnaire spécialisé dans la sérialisation et reconstruction des esquisses 2D."""

    @staticmethod
    def serialize(sketch: Sketch2D) -> Dict[str, JSONValue]:
        """Convertit une esquisse 2D en dictionnaire structuré."""
        name_val = sketch.name.value if hasattr(sketch.name, "value") else str(sketch.name)
        sk_data: Dict[str, JSONValue] = {
            "id": sketch.sketch_id,
            "name": name_val,
            "plane": sketch.plane.value,
            "offset_distance": sketch.offset_distance,
            "entities": []
        }
        for ent in sketch.entities:
            pts = [[pt.u, pt.v] for pt in ent.get_points()]
            cast_entities: List[Dict[str, Union[str, bool, int, float, List[List[float]]]]] = sk_data["entities"]  # type: ignore[assignment]
            ent_dict: Dict[str, Union[str, bool, int, float, List[List[float]]]] = {
                "id": ent.entity_id,
                "type": ent.entity_type.value,
                "points": pts,
                "is_construction": ent.is_construction
            }
            if hasattr(ent, "degree"):
                ent_dict["degree"] = getattr(ent, "degree")
            if hasattr(ent, "closed"):
                ent_dict["closed"] = getattr(ent, "closed")
            cast_entities.append(ent_dict)
        return sk_data

    @staticmethod
    def deserialize(sk_data: Dict[str, JSONValue]) -> Optional[Sketch2D]:
        """Reconstruit une esquisse 2D depuis un dictionnaire de données."""
        if not isinstance(sk_data, dict) or "id" not in sk_data:
            return None

        plane_val = str(sk_data.get("plane", "XY"))
        plane = PlaneType(plane_val) if plane_val in PlaneType._value2member_map_ else PlaneType.XY
        offset_d = float(sk_data.get("offset_distance", 0.0))
        sketch = Sketch2D(str(sk_data["id"]), str(sk_data.get("name", "Esquisse")), plane=plane, offset_distance=offset_d)

        entities_data = sk_data.get("entities", [])
        if isinstance(entities_data, list):
            for ent_dict in entities_data:
                if not isinstance(ent_dict, dict):
                    continue
                SketchSerializer._add_entity_to_sketch(sketch, ent_dict)

        return sketch

    @staticmethod
    def _add_entity_to_sketch(sketch: Sketch2D, ent_dict: Dict[str, Union[str, bool, int, float, List[List[float]]]]) -> None:
        """Parse et insère une entité géométrique dans l'esquisse."""
        raw_pts = ent_dict.get("points", [])
        is_const = bool(ent_dict.get("is_construction", False))
        if not isinstance(raw_pts, list):
            return

        pts: List[Point2D] = []
        for coord in raw_pts:
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                try:
                    pts.append(Point2D(float(coord[0]), float(coord[1])))
                except (ValueError, TypeError):
                    pass

        e_type = str(ent_dict.get("type", "polygon"))
        if e_type == "bspline":
            deg = int(ent_dict.get("degree", 3))
            cls_spl = bool(ent_dict.get("closed", False))
            sketch.add_bspline(pts, degree=deg, closed=cls_spl, is_construction=is_const)
        elif e_type == "bezier":
            cls_bez = bool(ent_dict.get("closed", False))
            sketch.add_bezier(pts, closed=cls_bez, is_construction=is_const)
        elif len(pts) >= 3:
            sketch.add_polygon(pts, is_construction=is_const)
        elif len(pts) == 2:
            sketch.add_line(pts[0], pts[1], is_construction=is_const)


class FeatureDeserializerRegistry:
    """
    Registre modulaire de désérialisation des fonctionnalités 3D.
    Divise la logique en constructeurs spécialisés par famille pour éliminer la complexité cognitive.
    """

    @classmethod
    def deserialize(cls, f_data: Dict[str, JSONValue]) -> Optional[Feature]:
        """Désérialise une fonctionnalité en déléguant au constructeur adapté."""
        if not isinstance(f_data, dict):
            return None

        f_cls = str(f_data.get("class", ""))
        f_id = str(f_data.get("id", ""))
        f_name = str(f_data.get("name", "Feature"))
        raw_params = f_data.get("parameters", {})
        params = raw_params if isinstance(raw_params, dict) else {}
        op_str = str(f_data.get("operation", "new_body"))
        op = BooleanOperation(op_str) if op_str in BooleanOperation._value2member_map_ else BooleanOperation.NEW_BODY
        target_id: Optional[str] = str(f_data["target_body_id"]) if f_data.get("target_body_id") is not None else None

        # 1. Primitives volumiques de base
        feat = cls._build_primitives(f_cls, f_id, f_name, params, op, target_id)
        if feat:
            return feat

        # 2. Opérations 2.5D basées sur esquisse
        feat = cls._build_sketch_features(f_cls, f_id, f_name, params, op, target_id, f_data)
        if feat:
            return feat

        # 3. Répétitions et transformations
        feat = cls._build_patterns_and_transforms(f_cls, f_id, f_name, params, op, target_id, f_data)
        if feat:
            return feat

        # 4. Opérations d'habillage (Dress-up)
        feat = cls._build_dressup_features(f_cls, f_id, f_name, params, op, target_id, f_data)
        if feat:
            return feat

        # 5. Formes complexes et lissages (Loft, Sweep, Tuyaux)
        feat = cls._build_complex_shapes(f_cls, f_id, f_name, params, op, target_id, f_data)
        if feat:
            return feat

        # 6. Plans de référence et fonctionnalités industrielles
        return cls._build_datum_and_specialized(f_cls, f_id, f_name, params, op, target_id, f_data)

    @staticmethod
    def _build_primitives(
        f_cls: str, f_id: str, f_name: str, params: Dict[str, JSONPrimitive],
        op: BooleanOperation, target_id: Optional[str]
    ) -> Optional[Feature]:
        """Reconstruit les primitives 3D analytiques."""
        if f_cls == "BoxFeature":
            w = float(params.get("width", 20.0))
            h = float(params.get("height", 20.0))
            d = float(params.get("depth", 20.0))
            center = bool(float(params.get("center", 0.0)) > 0.5)
            return BoxFeature(f_id, f_name, w, h, d, center, op, target_id)

        if f_cls == "CylinderFeature":
            rad = float(params.get("radius", 10.0))
            h = float(params.get("height", 30.0))
            return CylinderFeature(f_id, f_name, rad, h, 36, op, target_id)

        if f_cls == "SphereFeature":
            rad = float(params.get("radius", 15.0))
            return SphereFeature(f_id, f_name, rad, 36, op, target_id)

        if f_cls == "ConeFeature":
            r_bot = float(params.get("radius_bottom", 15.0))
            r_top = float(params.get("radius_top", 0.0))
            h = float(params.get("height", 30.0))
            return ConeFeature(f_id, f_name, r_bot, r_top, h, 36, op, target_id)

        if f_cls == "TorusFeature":
            r_maj = float(params.get("major_radius", 25.0))
            r_min = float(params.get("minor_radius", 6.0))
            return TorusFeature(f_id, f_name, r_maj, r_min, 36, op, target_id)

        if f_cls == "WedgeFeature":
            dx = float(params.get("dx", 30.0))
            dy = float(params.get("dy", 20.0))
            dz = float(params.get("dz", 15.0))
            dx_top = float(params.get("dx_top", 0.0))
            dy_top = float(params.get("dy_top", 0.0))
            return WedgeFeature(f_id, f_name, dx, dy, dz, dx_top, dy_top, op, target_id)

        return None

    @staticmethod
    def _build_sketch_features(
        f_cls: str, f_id: str, f_name: str, params: Dict[str, JSONPrimitive],
        op: BooleanOperation, target_id: Optional[str], f_data: Dict[str, JSONValue]
    ) -> Optional[Feature]:
        """Reconstruit les opérations basées sur une esquisse."""
        if f_cls == "ExtrudeFeature":
            s_id = str(f_data.get("sketch_id", ""))
            dist = float(params.get("distance", 25.0))
            sym = bool(params.get("symmetric", 0.0) > 0.5 or f_data.get("symmetric", False))
            taper = float(params.get("taper_angle", f_data.get("taper_angle", 0.0)))
            twist = float(params.get("twist_degrees", f_data.get("twist_degrees", 0.0)))
            return ExtrudeFeature(
                f_id, f_name, s_id, dist,
                symmetric=sym, taper_angle=taper, twist_degrees=twist,
                operation=op, target_body_id=target_id
            )

        if f_cls == "PocketFeature":
            s_id = str(f_data.get("sketch_id", ""))
            dep = float(params.get("depth", 10.0))
            thru = bool(f_data.get("through_all", False) or params.get("through_all", 0.0) > 0.5)
            rev = bool(f_data.get("reversed_dir", False) or params.get("reversed", 0.0) > 0.5)
            return PocketFeature(f_id, f_name, s_id, dep, thru, rev, target_id)

        if f_cls == "RevolveFeature":
            s_id = str(f_data.get("sketch_id", ""))
            ang = float(params.get("angle", 360.0))
            return RevolveFeature(f_id, f_name, s_id, ang, 48, op, target_id)

        if f_cls == "GrooveFeature":
            s_id = str(f_data.get("sketch_id", ""))
            ang = float(params.get("angle", 360.0))
            segs = int(params.get("segments", 48))
            return GrooveFeature(f_id, f_name, s_id, ang, segs, target_id)

        if f_cls == "RibFeature":
            s_id = str(f_data.get("sketch_id", ""))
            thick = float(params.get("thickness", 4.0))
            sym = bool(params.get("symmetric", 1.0) > 0.5 or f_data.get("symmetric", True))
            draft = float(params.get("draft_angle", 0.0))
            return RibFeature(f_id, f_name, sketch_id=s_id, thickness=thick, symmetric=sym, draft_angle=draft, target_body_id=target_id)

        return None

    @staticmethod
    def _build_patterns_and_transforms(
        f_cls: str, f_id: str, f_name: str, params: Dict[str, JSONPrimitive],
        op: BooleanOperation, target_id: Optional[str], f_data: Dict[str, JSONValue]
    ) -> Optional[Feature]:
        """Reconstruit les répétitions, miroirs et transformations combinées."""
        if f_cls == "LinearPatternFeature":
            src = str(f_data.get("source_body_id", ""))
            nx = int(params.get("count_x", 2))
            dx = float(params.get("spacing_x", 30.0))
            return LinearPatternFeature(f_id, f_name, src, nx, dx)

        if f_cls == "CircularPatternFeature":
            src = str(f_data.get("source_body_id", ""))
            count = int(params.get("count", 6))
            total_ang = float(params.get("total_angle", 360.0))
            join_b = bool(f_data.get("join_bodies", True))
            return CircularPatternFeature(f_id, f_name, src, count, total_ang, join_b)

        if f_cls == "MirrorFeature":
            src = str(f_data.get("source_body_id", ""))
            mp_str = str(f_data.get("mirror_plane", "YZ"))
            mp = PlaneType(mp_str) if mp_str in PlaneType._value2member_map_ else PlaneType.YZ
            join_s = bool(f_data.get("join_with_source", True))
            return MirrorFeature(f_id, f_name, src, mp, join_s)

        if f_cls == "MultiTransformFeature":
            src = str(f_data.get("source_body_id", ""))
            join_b = bool(f_data.get("join_bodies", True))
            raw_steps = f_data.get("steps", [])
            steps_objs: List[MultiTransformStep] = []
            if isinstance(raw_steps, list):
                for st_data in raw_steps:
                    if isinstance(st_data, dict):
                        t_type = str(st_data.get("type", "linear"))
                        cnt = int(st_data.get("count", 2))
                        spc = float(st_data.get("spacing", 20.0))
                        ax = str(st_data.get("axis", "X"))
                        tot_ang = float(st_data.get("total_angle", 360.0))
                        mp_str = str(st_data.get("mirror_plane", "YZ"))
                        mp = PlaneType(mp_str) if mp_str in PlaneType._value2member_map_ else PlaneType.YZ
                        s_fact = float(st_data.get("scale_factor", 1.0))
                        steps_objs.append(MultiTransformStep(t_type, cnt, spc, ax, tot_ang, mp, s_fact))
            return MultiTransformFeature(f_id, f_name, src, steps_objs, join_b)

        return None

    @staticmethod
    def _build_dressup_features(
        f_cls: str, f_id: str, f_name: str, params: Dict[str, JSONPrimitive],
        op: BooleanOperation, target_id: Optional[str], f_data: Dict[str, JSONValue]
    ) -> Optional[Feature]:
        """Reconstruit les opérations d'habillage géométrique."""
        if f_cls == "FilletFeature":
            rad = float(params.get("radius", 2.0))
            segs = int(params.get("segments", 16))
            return FilletFeature(f_id, f_name, target_id or "", rad, segs)

        if f_cls == "VariableRadiusFilletFeature":
            r_start = float(params.get("start_radius", 2.0))
            r_end = float(params.get("end_radius", 8.0))
            r_mid = float(params.get("mid_radius", (r_start + r_end) * 0.5))
            edge_dir = str(f_data.get("edge_direction", "z"))
            n_steps = int(params.get("steps", 16))
            return VariableRadiusFilletFeature(
                f_id, f_name, target_body_id=target_id or "",
                start_radius=r_start, end_radius=r_end, mid_radius=r_mid,
                edge_direction=edge_dir, steps=n_steps
            )

        if f_cls == "ChamferFeature":
            dist = float(params.get("distance", 2.0))
            mode = str(f_data.get("edges_mode", "all"))
            return ChamferFeature(f_id, f_name, target_id or "", dist, mode)

        if f_cls == "DraftFeature":
            angle = float(params.get("draft_angle", 3.0))
            axis = str(f_data.get("pull_axis", "Z"))
            return DraftFeature(f_id, f_name, target_id or "", angle, axis)

        if f_cls == "ShellFeature":
            thick = float(params.get("wall_thickness", 2.0))
            return ShellFeature(f_id, f_name, target_id or "", thick)

        if f_cls == "HoleFeature":
            px = float(params.get("pos_x", 0.0))
            py = float(params.get("pos_y", 0.0))
            dia = float(params.get("diameter", 6.0))
            dep = float(params.get("depth", 30.0))
            htype = str(f_data.get("hole_type", "simple"))
            cbdia = float(params.get("cbore_dia", 10.0))
            cbdep = float(params.get("cbore_depth", 6.0))
            csdia = float(params.get("csink_dia", 12.0))
            csang = float(params.get("csink_angle", 90.0))
            return HoleFeature(f_id, f_name, target_id or "", px, py, dia, dep, 36, htype, cbdia, cbdep, csdia, csang)

        return None

    @staticmethod
    def _build_complex_shapes(
        f_cls: str, f_id: str, f_name: str, params: Dict[str, JSONPrimitive],
        op: BooleanOperation, target_id: Optional[str], f_data: Dict[str, JSONValue]
    ) -> Optional[Feature]:
        """Reconstruit les formes complexes (Loft, Sweep, Pipe, Helix)."""
        if f_cls == "LoftFeature":
            s_start = str(f_data.get("start_sketch_id", ""))
            s_end = str(f_data.get("end_sketch_id", ""))
            h_off = float(params.get("height_offset", 30.0))
            s_top = float(params.get("scale_top", 1.0))
            segs = int(params.get("num_segments", 36))
            return LoftFeature(f_id, f_name, s_start, s_end, h_off, s_top, segs, op, target_id)

        if f_cls == "SubtractiveLoftFeature":
            s_start = str(f_data.get("start_sketch_id", ""))
            s_end = str(f_data.get("end_sketch_id", ""))
            h_off = float(params.get("height_offset", 30.0))
            s_top = float(params.get("scale_top", 1.0))
            segs = int(params.get("num_segments", 36))
            return SubtractiveLoftFeature(f_id, f_name, s_start, s_end, h_off, s_top, segs, target_id)

        if f_cls == "MultiRailLoftFeature":
            sk_ids = [str(x) for x in f_data.get("profile_sketch_ids", []) if isinstance(x, str)]
            raw_rails = f_data.get("guide_rail_curves", [])
            rails_list: List[List[Tuple[float, float, float]]] = []
            if isinstance(raw_rails, list):
                for r in raw_rails:
                    if isinstance(r, list):
                        rail_pts: List[Tuple[float, float, float]] = []
                        for pt in r:
                            if isinstance(pt, list) and len(pt) == 3:
                                rail_pts.append((float(pt[0]), float(pt[1]), float(pt[2])))
                        rails_list.append(rail_pts)
            n_sec = int(params.get("num_sections", 16))
            n_seg = int(params.get("num_segments", 36))
            return MultiRailLoftFeature(
                f_id, f_name, profile_sketch_ids=sk_ids,
                guide_rail_curves=rails_list, num_intermediate_sections=n_sec,
                num_segments=n_seg, operation=op, target_body_id=target_id
            )

        if f_cls == "SweepFeature":
            prof_id = str(f_data.get("profile_sketch_id", ""))
            traj_type = str(f_data.get("trajectory_type", "arc"))
            rad = float(params.get("radius", 30.0))
            h = float(params.get("height", 40.0))
            turns = float(params.get("turns", 1.0))
            k_steps = int(params.get("num_steps", 24))
            n_segs = int(params.get("segments", 24))
            return SweepFeature(f_id, f_name, prof_id, traj_type, rad, h, turns, k_steps, n_segs, op, target_id)

        if f_cls == "SubtractiveSweepFeature":
            prof_id = str(f_data.get("profile_sketch_id", ""))
            traj_type = str(f_data.get("trajectory_type", "arc"))
            rad = float(params.get("radius", 30.0))
            h = float(params.get("height", 40.0))
            turns = float(params.get("turns", 1.0))
            k_steps = int(params.get("num_steps", 24))
            n_segs = int(params.get("segments", 24))
            return SubtractiveSweepFeature(f_id, f_name, prof_id, traj_type, rad, h, turns, k_steps, n_segs, target_id)

        if f_cls == "HelixFeature":
            pitch = float(params.get("pitch", 10.0))
            h = float(params.get("height", 40.0))
            turns = float(params.get("turns", 4.0))
            rad = float(params.get("radius", 15.0))
            w_rad = float(params.get("wire_radius", 2.0))
            c_ang = float(params.get("cone_angle", 0.0))
            is_left = bool(params.get("is_left_handed", 0.0) > 0.5 or f_data.get("is_left_handed", False))
            axis = str(f_data.get("axis", "Z"))
            is_sub = bool(params.get("is_subtractive", 0.0) > 0.5 or f_data.get("is_subtractive", False))
            return HelixFeature(
                f_id, f_name, pitch=pitch, height=h, turns=turns, radius=rad,
                wire_radius=w_rad, cone_angle=c_ang, is_left_handed=is_left,
                axis=axis, is_subtractive=is_sub, operation=op, target_body_id=target_id
            )

        if f_cls == "PipeFeature":
            raw_pts = f_data.get("path_points")
            pts_list: List[Tuple[float, float, float]] = []
            if isinstance(raw_pts, list):
                for p in raw_pts:
                    if isinstance(p, (list, tuple)) and len(p) >= 3:
                        pts_list.append((float(p[0]), float(p[1]), float(p[2])))
            if not pts_list:
                pts_list = [(0.0, 0.0, 0.0), (50.0, 0.0, 0.0), (50.0, 50.0, 0.0)]
            r_out = float(params.get("outer_radius", 6.0))
            r_in = float(params.get("inner_radius", 0.0))
            return PipeFeature(f_id, f_name, pts_list, r_out, r_in, op, target_id)

        return None

    @staticmethod
    def _build_datum_and_specialized(
        f_cls: str, f_id: str, f_name: str, params: Dict[str, JSONPrimitive],
        op: BooleanOperation, target_id: Optional[str], f_data: Dict[str, JSONValue]
    ) -> Optional[Feature]:
        """Reconstruit les plans de référence, la tôlerie et la visserie."""
        if f_cls == "DatumPlaneFeature":
            bp_str = str(f_data.get("base_plane", "XY"))
            bp = PlaneType(bp_str) if bp_str in PlaneType._value2member_map_ else PlaneType.XY
            off = float(params.get("offset_distance", 0.0))
            return DatumPlaneFeature(f_id, f_name, bp, off)

        if f_cls == "DynamicDatumPlaneFeature":
            mode_str = str(f_data.get("mode", "OFFSET"))
            mode = DatumAttachmentMode(mode_str) if mode_str in DatumAttachmentMode._value2member_map_ else DatumAttachmentMode.OFFSET
            bp_str = str(f_data.get("base_plane", "XY"))
            bp = PlaneType(bp_str) if bp_str in PlaneType._value2member_map_ else PlaneType.XY
            off = float(params.get("offset_distance", 0.0))

            raw_p1 = f_data.get("point1", [0.0, 0.0, 0.0])
            p1 = (float(raw_p1[0]), float(raw_p1[1]), float(raw_p1[2])) if isinstance(raw_p1, list) and len(raw_p1) == 3 else (0.0, 0.0, 0.0)
            raw_p2 = f_data.get("point2")
            p2 = (float(raw_p2[0]), float(raw_p2[1]), float(raw_p2[2])) if isinstance(raw_p2, list) and len(raw_p2) == 3 else None
            raw_p3 = f_data.get("point3")
            p3 = (float(raw_p3[0]), float(raw_p3[1]), float(raw_p3[2])) if isinstance(raw_p3, list) and len(raw_p3) == 3 else None
            raw_tn = f_data.get("tangent_or_normal")
            tn = (float(raw_tn[0]), float(raw_tn[1]), float(raw_tn[2])) if isinstance(raw_tn, list) and len(raw_tn) == 3 else None

            return DynamicDatumPlaneFeature(
                f_id, f_name, mode=mode, base_plane=bp, offset_distance=off,
                point1=p1, point2=p2, point3=p3, tangent_or_normal=tn
            )

        if f_cls == "SplitFeature":
            pl_str = str(f_data.get("plane", "XY"))
            pl = PlaneType(pl_str) if pl_str in PlaneType._value2member_map_ else PlaneType.XY
            off = float(params.get("plane_offset", 0.0))
            side = str(f_data.get("keep_side", "positive"))
            return SplitFeature(f_id, f_name, target_body_id=target_id or "", plane=pl, plane_offset=off, keep_side=side)

        if f_cls == "BooleanFeature":
            tool_id = str(f_data.get("tool_body_id", ""))
            return BooleanFeature(f_id, f_name, target_id or "", tool_id, op)

        if f_cls == "SheetMetalFeature":
            bw = float(params.get("base_width", 60.0))
            bl = float(params.get("base_length", 80.0))
            th = float(params.get("thickness", 2.0))
            br = float(params.get("bend_radius", 2.0))
            fl = float(params.get("flange_length", 25.0))
            kf = float(params.get("k_factor", 0.44))
            return SheetMetalFeature(f_id, f_name, bw, bl, th, br, fl, kf, target_id)

        if f_cls == "FastenerFeature":
            ftype = str(f_data.get("fastener_type", "hex_bolt"))
            size = str(f_data.get("standard_size", "M6"))
            length = float(params.get("length", 30.0))
            return FastenerFeature(f_id, f_name, ftype, size, length, op, target_id)

        return None


class ProjectSerializer:
    """Gestionnaire de haut niveau pour la sauvegarde et le chargement de projet paramétrique."""

    @staticmethod
    def save_project(document: CADDocument, filepath: str) -> bool:
        """Sérialise le document complet sous forme de fichier JSON .cadproj ou .cadz compressé."""
        data: Dict[str, JSONValue] = {
            "format_version": "1.0",
            "name": document.name,
            "rollback_index": document.rollback_index,
            "sketches": [],
            "features": []
        }

        # 1. Sérialiser les esquisses via SketchSerializer
        cast_sketches: List[Dict[str, JSONValue]] = data["sketches"]  # type: ignore[assignment]
        for sk in document.sketches.values():
            cast_sketches.append(SketchSerializer.serialize(sk))

        # 2. Sérialiser les fonctionnalités paramétriques
        cast_features: List[Dict[str, JSONValue]] = data["features"]  # type: ignore[assignment]
        for feat in document.features:
            f_dict = ProjectSerializer._serialize_feature(feat)
            cast_features.append(f_dict)

        # 3. Écriture sur disque (support du format compressé .cadz)
        return ProjectSerializer._write_to_disk(data, filepath)

    @staticmethod
    def _serialize_feature(feat: Feature) -> Dict[str, JSONValue]:
        """Convertit une fonctionnalité paramétrique en dictionnaire JSON."""
        f_type = feat.__class__.__name__
        f_dict: Dict[str, JSONValue] = {
            "class": f_type,
            "id": feat.feature_id,
            "name": feat.name,
            "parameters": feat.parameters,
            "is_suppressed": feat.is_suppressed,
        }

        if hasattr(feat, "operation") and isinstance(feat.operation, BooleanOperation):
            f_dict["operation"] = feat.operation.value
        if hasattr(feat, "target_body_id"):
            f_dict["target_body_id"] = getattr(feat, "target_body_id")
        if hasattr(feat, "sketch_id"):
            f_dict["sketch_id"] = getattr(feat, "sketch_id")
        if hasattr(feat, "source_body_id"):
            f_dict["source_body_id"] = getattr(feat, "source_body_id")
        if hasattr(feat, "tool_body_id"):
            f_dict["tool_body_id"] = getattr(feat, "tool_body_id")
        if hasattr(feat, "mirror_plane"):
            f_dict["mirror_plane"] = getattr(feat, "mirror_plane").value
        if hasattr(feat, "hole_type"):
            f_dict["hole_type"] = getattr(feat, "hole_type")
        if hasattr(feat, "fastener_type"):
            f_dict["fastener_type"] = getattr(feat, "fastener_type")
        if hasattr(feat, "standard_size"):
            f_dict["standard_size"] = getattr(feat, "standard_size")
        if hasattr(feat, "path_points"):
            f_dict["path_points"] = getattr(feat, "path_points")
        if hasattr(feat, "start_sketch_id"):
            f_dict["start_sketch_id"] = getattr(feat, "start_sketch_id")
        if hasattr(feat, "end_sketch_id"):
            f_dict["end_sketch_id"] = getattr(feat, "end_sketch_id")
        if hasattr(feat, "profile_sketch_id"):
            f_dict["profile_sketch_id"] = getattr(feat, "profile_sketch_id")
        if hasattr(feat, "trajectory_type"):
            f_dict["trajectory_type"] = getattr(feat, "trajectory_type")
        if hasattr(feat, "edges_mode"):
            f_dict["edges_mode"] = getattr(feat, "edges_mode")
        if hasattr(feat, "pull_axis"):
            f_dict["pull_axis"] = getattr(feat, "pull_axis")
        if hasattr(feat, "base_plane"):
            f_dict["base_plane"] = getattr(feat, "base_plane").value
        if hasattr(feat, "keep_side"):
            f_dict["keep_side"] = getattr(feat, "keep_side")
        if hasattr(feat, "plane") and isinstance(getattr(feat, "plane"), PlaneType):
            f_dict["plane"] = getattr(feat, "plane").value
        if hasattr(feat, "steps") and isinstance(getattr(feat, "steps"), list):
            f_dict["steps"] = [st.to_dict() for st in getattr(feat, "steps") if hasattr(st, "to_dict")]
        if hasattr(feat, "join_bodies"):
            f_dict["join_bodies"] = getattr(feat, "join_bodies")
        if hasattr(feat, "join_with_source"):
            f_dict["join_with_source"] = getattr(feat, "join_with_source")
        if hasattr(feat, "symmetric"):
            f_dict["symmetric"] = getattr(feat, "symmetric")
        if hasattr(feat, "taper_angle"):
            f_dict["taper_angle"] = getattr(feat, "taper_angle")
        if hasattr(feat, "twist_degrees"):
            f_dict["twist_degrees"] = getattr(feat, "twist_degrees")
        if hasattr(feat, "is_left_handed"):
            f_dict["is_left_handed"] = getattr(feat, "is_left_handed")
        if hasattr(feat, "axis"):
            f_dict["axis"] = getattr(feat, "axis")
        if hasattr(feat, "is_subtractive"):
            f_dict["is_subtractive"] = getattr(feat, "is_subtractive")
        if hasattr(feat, "mode"):
            f_dict["mode"] = getattr(feat, "mode").value if hasattr(getattr(feat, "mode"), "value") else str(getattr(feat, "mode"))
        if hasattr(feat, "point1"):
            f_dict["point1"] = list(getattr(feat, "point1")) if getattr(feat, "point1") else None
        if hasattr(feat, "point2"):
            f_dict["point2"] = list(getattr(feat, "point2")) if getattr(feat, "point2") else None
        if hasattr(feat, "point3"):
            f_dict["point3"] = list(getattr(feat, "point3")) if getattr(feat, "point3") else None
        if hasattr(feat, "tangent_or_normal"):
            f_dict["tangent_or_normal"] = list(getattr(feat, "tangent_or_normal")) if getattr(feat, "tangent_or_normal") else None
        if hasattr(feat, "edge_direction"):
            f_dict["edge_direction"] = getattr(feat, "edge_direction")
        if hasattr(feat, "profile_sketch_ids"):
            f_dict["profile_sketch_ids"] = getattr(feat, "profile_sketch_ids")
        if hasattr(feat, "guide_rail_curves"):
            f_dict["guide_rail_curves"] = getattr(feat, "guide_rail_curves")

        return f_dict

    @staticmethod
    def _write_to_disk(data: Dict[str, JSONValue], filepath: str) -> bool:
        """Écrit les données JSON brutes ou zippées."""
        if filepath.lower().endswith(".cadz"):
            with zipfile.ZipFile(filepath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json.dumps(data, indent=2, ensure_ascii=False))
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    @classmethod
    def load_project(cls, filepath: str) -> Optional[CADDocument]:
        """
        Désérialise un projet .cadproj ou .cadz compressé et reconstruit l'arbre paramétrique.
        Architecture propre de moins de 30 lignes avec complexité cognitive minimale.
        """
        if not os.path.exists(filepath):
            return None

        data = cls._read_project_data(filepath)
        if not isinstance(data, dict):
            return None

        try:
            doc = CADDocument(name=str(data.get("name", "Projet Chargé")))

            # 1. Reconstruire toutes les esquisses
            for sk_data in data.get("sketches", []):
                if isinstance(sk_data, dict):
                    sketch = SketchSerializer.deserialize(sk_data)
                    if sketch:
                        doc.sketches[sketch.sketch_id] = sketch

            # 2. Reconstruire toutes les fonctionnalités paramétriques
            for f_data in data.get("features", []):
                if isinstance(f_data, dict):
                    feat = FeatureDeserializerRegistry.deserialize(f_data)
                    if feat:
                        feat.is_suppressed = bool(f_data.get("is_suppressed", False))
                        doc.features.append(feat)

            # 3. Positionner le curseur de rollback et reconstruire la géométrie
            raw_rollback = data.get("rollback_index")
            doc.rollback_index = raw_rollback if isinstance(raw_rollback, int) else len(doc.features) - 1
            doc.rebuild()
            return doc

        except Exception:
            return None

    @staticmethod
    def _read_project_data(filepath: str) -> Optional[Dict[str, JSONValue]]:
        """Lit et décompresse les données JSON du fichier projet."""
        try:
            if filepath.lower().endswith(".cadz") or zipfile.is_zipfile(filepath):
                with zipfile.ZipFile(filepath, "r") as zf:
                    return json.loads(zf.read("project.json").decode("utf-8"))
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
