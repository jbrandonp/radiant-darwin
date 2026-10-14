"""
Moteur de sérialisation et persistance de projets CAO (.cadproj / JSON).
Permet de sauvegarder l'arbre complet d'historique paramétrique et les esquisses sur disque
et de recharger le projet avec recalcul automatique de la géométrie 3D.
"""

from __future__ import annotations
import json
import os
from typing import Dict, List, Optional, Union

# Typage strict pour données JSON sans utilisation d'Any
JSONValue = Union[str, int, float, bool, None, List[object], Dict[str, object]]

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
    HelixFeature, RibFeature, SplitFeature, SubtractiveLoftFeature, SubtractiveSweepFeature
)
from src.core.fasteners import FastenerFeature
from src.sheetmetal.sheet_metal import SheetMetalFeature


class ProjectSerializer:
    """Gestionnaire de sauvegarde et chargement de projet paramétrique."""

    @staticmethod
    def save_project(document: CADDocument, filepath: str) -> bool:
        """Sérialise le document complet sous forme de fichier JSON .cadproj."""
        data: Dict[str, JSONValue] = {
            "format_version": "1.0",
            "name": document.name,
            "rollback_index": document.rollback_index,
            "sketches": [],
            "features": []
        }

        # 1. Sérialiser les esquisses
        for s_id, sk in document.sketches.items():
            sk_data: Dict[str, JSONValue] = {
                "id": sk.sketch_id,
                "name": sk.name,
                "plane": sk.plane.value,
                "offset_distance": sk.offset_distance,
                "entities": []
            }
            for ent in sk.entities:
                pts = [[pt.u, pt.v] for pt in ent.get_points()]
                cast_entities: List[object] = sk_data["entities"]  # type: ignore[assignment]
                ent_dict: Dict[str, object] = {
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
            cast_sketches: List[object] = data["sketches"]  # type: ignore[assignment]
            cast_sketches.append(sk_data)

        # 2. Sérialiser les features paramétriques
        for feat in document.features:
            f_type = feat.__class__.__name__
            f_dict: Dict[str, JSONValue] = {
                "class": f_type,
                "id": feat.feature_id,
                "name": feat.name,
                "parameters": feat.parameters,
                "is_suppressed": feat.is_suppressed,
            }

            # Champs spécifiques selon le type
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
            if hasattr(feat, "mirror_plane") and isinstance(feat.mirror_plane, PlaneType):
                f_dict["mirror_plane"] = feat.mirror_plane.value
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
            if hasattr(feat, "fastener_type"):
                f_dict["fastener_type"] = getattr(feat, "fastener_type")
            if hasattr(feat, "standard_size"):
                f_dict["standard_size"] = getattr(feat, "standard_size")
            if hasattr(feat, "join_bodies"):
                f_dict["join_bodies"] = getattr(feat, "join_bodies")
            if hasattr(feat, "join_with_source"):
                f_dict["join_with_source"] = getattr(feat, "join_with_source")
            if hasattr(feat, "hole_type"):
                f_dict["hole_type"] = getattr(feat, "hole_type")
            if hasattr(feat, "path_points"):
                f_dict["path_points"] = getattr(feat, "path_points")
            if hasattr(feat, "through_all"):
                f_dict["through_all"] = getattr(feat, "through_all")
            if hasattr(feat, "reversed_dir"):
                f_dict["reversed_dir"] = getattr(feat, "reversed_dir")
            if hasattr(feat, "base_plane") and isinstance(feat.base_plane, PlaneType):
                f_dict["base_plane"] = feat.base_plane.value
            if hasattr(feat, "steps") and isinstance(getattr(feat, "steps"), list):
                raw_st: List[object] = getattr(feat, "steps")
                st_list: List[object] = []
                for st in raw_st:
                    st_list.append({
                        "type": getattr(st, "transform_type", "linear"),
                        "count": getattr(st, "count", 2),
                        "spacing": getattr(st, "spacing", 20.0),
                        "axis": getattr(st, "axis", "X"),
                        "total_angle": getattr(st, "total_angle", 360.0),
                        "mirror_plane": getattr(st, "mirror_plane").value if hasattr(st, "mirror_plane") and isinstance(getattr(st, "mirror_plane"), PlaneType) else "YZ",
                        "scale_factor": getattr(st, "scale_factor", 1.0)
                    })
                f_dict["steps"] = st_list
            if hasattr(feat, "symmetric"):
                f_dict["symmetric"] = getattr(feat, "symmetric")
            if hasattr(feat, "taper_angle"):
                f_dict["taper_angle"] = getattr(feat, "taper_angle")
            if hasattr(feat, "twist_degrees"):
                f_dict["twist_degrees"] = getattr(feat, "twist_degrees")
            if hasattr(feat, "pitch"):
                f_dict["pitch"] = getattr(feat, "pitch")
            if hasattr(feat, "turns"):
                f_dict["turns"] = getattr(feat, "turns")
            if hasattr(feat, "wire_radius"):
                f_dict["wire_radius"] = getattr(feat, "wire_radius")
            if hasattr(feat, "cone_angle"):
                f_dict["cone_angle"] = getattr(feat, "cone_angle")
            if hasattr(feat, "is_left_handed"):
                f_dict["is_left_handed"] = getattr(feat, "is_left_handed")
            if hasattr(feat, "axis"):
                f_dict["axis"] = getattr(feat, "axis")
            if hasattr(feat, "is_subtractive"):
                f_dict["is_subtractive"] = getattr(feat, "is_subtractive")
            if hasattr(feat, "thickness"):
                f_dict["thickness"] = getattr(feat, "thickness")
            if hasattr(feat, "draft_angle"):
                f_dict["draft_angle"] = getattr(feat, "draft_angle")
            if hasattr(feat, "keep_side"):
                f_dict["keep_side"] = getattr(feat, "keep_side")
            if hasattr(feat, "plane") and isinstance(getattr(feat, "plane"), PlaneType):
                f_dict["plane"] = getattr(feat, "plane").value

            data["features"].append(f_dict)

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True

    @staticmethod
    def load_project(filepath: str) -> Optional[CADDocument]:
        """Désérialise un projet .cadproj et reconstruit l'arbre paramétrique de façon blindée."""
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        try:
            doc_name = str(data.get("name", "Projet Chargé"))
            doc = CADDocument(name=doc_name)

            # 1. Reconstruire les esquisses
            sketches_data = data.get("sketches", [])
            if isinstance(sketches_data, list):
                for sk_data in sketches_data:
                    if not isinstance(sk_data, dict) or "id" not in sk_data:
                        continue
                    plane_val = str(sk_data.get("plane", "XY"))
                    plane = PlaneType(plane_val) if plane_val in PlaneType._value2member_map_ else PlaneType.XY
                    offset_d = float(sk_data.get("offset_distance", 0.0))
                    sketch = Sketch2D(str(sk_data["id"]), str(sk_data.get("name", "Esquisse")), plane=plane, offset_distance=offset_d)

                    entities_data = sk_data.get("entities", [])
                    if isinstance(entities_data, list):
                        for ent_dict in entities_data:
                            if not isinstance(ent_dict, dict):
                                continue
                            raw_pts = ent_dict.get("points", [])
                            is_const = bool(ent_dict.get("is_construction", False))
                            if isinstance(raw_pts, list):
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

                    doc.sketches[sketch.sketch_id] = sketch

            # 2. Reconstruire les features
            features_data = data.get("features", [])
            if isinstance(features_data, list):
                for f_data in features_data:
                    if not isinstance(f_data, dict):
                        continue
                    f_cls = f_data.get("class")
                    f_id = str(f_data.get("id", ""))
                    f_name = str(f_data.get("name", "Feature"))
                    raw_params = f_data.get("parameters", {})
                    params = raw_params if isinstance(raw_params, dict) else {}
                    op_str = str(f_data.get("operation", "new_body"))
                    op = BooleanOperation(op_str) if op_str in BooleanOperation._value2member_map_ else BooleanOperation.NEW_BODY
                    target_id = f_data.get("target_body_id")
                    if target_id is not None:
                        target_id = str(target_id)

                    feat: Optional[Feature] = None

                    if f_cls == "BoxFeature":
                        w = float(params.get("width", 20.0))
                        h = float(params.get("height", 20.0))
                        d = float(params.get("depth", 20.0))
                        center = bool(float(params.get("center", 0.0)) > 0.5)
                        feat = BoxFeature(f_id, f_name, w, h, d, center, op, target_id)

                    elif f_cls == "CylinderFeature":
                        rad = float(params.get("radius", 10.0))
                        h = float(params.get("height", 30.0))
                        feat = CylinderFeature(f_id, f_name, rad, h, 36, op, target_id)

                    elif f_cls == "SphereFeature":
                        rad = float(params.get("radius", 15.0))
                        feat = SphereFeature(f_id, f_name, rad, 36, op, target_id)

                    elif f_cls == "ExtrudeFeature":
                        s_id = str(f_data.get("sketch_id", ""))
                        dist = float(params.get("distance", 25.0))
                        sym = bool(params.get("symmetric", 0.0) > 0.5 or f_data.get("symmetric", False))
                        taper = float(params.get("taper_angle", f_data.get("taper_angle", 0.0)))
                        twist = float(params.get("twist_degrees", f_data.get("twist_degrees", 0.0)))
                        feat = ExtrudeFeature(
                            f_id, f_name, s_id, dist,
                            symmetric=sym, taper_angle=taper, twist_degrees=twist,
                            operation=op, target_body_id=target_id
                        )

                    elif f_cls == "RevolveFeature":
                        s_id = str(f_data.get("sketch_id", ""))
                        ang = float(params.get("angle", 360.0))
                        feat = RevolveFeature(f_id, f_name, s_id, ang, 48, op, target_id)

                    elif f_cls == "HoleFeature":
                        px = float(params.get("pos_x", 0.0))
                        py = float(params.get("pos_y", 0.0))
                        dia = float(params.get("diameter", 6.0))
                        dep = float(params.get("depth", 30.0))
                        htype = str(f_data.get("hole_type", "simple"))
                        cbdia = float(params.get("cbore_dia", 10.0))
                        cbdep = float(params.get("cbore_depth", 6.0))
                        csdia = float(params.get("csink_dia", 12.0))
                        csang = float(params.get("csink_angle", 90.0))
                        feat = HoleFeature(f_id, f_name, target_id or "", px, py, dia, dep, 36, htype, cbdia, cbdep, csdia, csang)

                    elif f_cls == "ShellFeature":
                        thick = float(params.get("wall_thickness", 2.0))
                        feat = ShellFeature(f_id, f_name, target_id or "", thick)

                    elif f_cls == "LinearPatternFeature":
                        src = str(f_data.get("source_body_id", ""))
                        nx = int(params.get("count_x", 2))
                        dx = float(params.get("spacing_x", 30.0))
                        feat = LinearPatternFeature(f_id, f_name, src, nx, dx)

                    elif f_cls == "CircularPatternFeature":
                        src = str(f_data.get("source_body_id", ""))
                        count = int(params.get("count", 6))
                        total_ang = float(params.get("total_angle", 360.0))
                        join_b = bool(f_data.get("join_bodies", True))
                        feat = CircularPatternFeature(f_id, f_name, src, count, total_ang, join_b)

                    elif f_cls == "MirrorFeature":
                        src = str(f_data.get("source_body_id", ""))
                        mp_str = str(f_data.get("mirror_plane", "YZ"))
                        mp = PlaneType(mp_str) if mp_str in PlaneType._value2member_map_ else PlaneType.YZ
                        join_s = bool(f_data.get("join_with_source", True))
                        feat = MirrorFeature(f_id, f_name, src, mp, join_s)

                    elif f_cls == "BooleanFeature":
                        tool_id = str(f_data.get("tool_body_id", ""))
                        feat = BooleanFeature(f_id, f_name, target_id or "", tool_id, op)

                    elif f_cls == "SheetMetalFeature":
                        bw = float(params.get("base_width", 60.0))
                        bl = float(params.get("base_length", 80.0))
                        th = float(params.get("thickness", 2.0))
                        br = float(params.get("bend_radius", 2.0))
                        fl = float(params.get("flange_length", 25.0))
                        kf = float(params.get("k_factor", 0.44))
                        feat = SheetMetalFeature(f_id, f_name, bw, bl, th, br, fl, kf, target_id)

                    elif f_cls == "LoftFeature":
                        s_start = str(f_data.get("start_sketch_id", ""))
                        s_end = str(f_data.get("end_sketch_id", ""))
                        h_off = float(params.get("height_offset", 30.0))
                        s_top = float(params.get("scale_top", 1.0))
                        segs = int(params.get("num_segments", 36))
                        feat = LoftFeature(f_id, f_name, s_start, s_end, h_off, s_top, segs, op, target_id)

                    elif f_cls == "SweepFeature":
                        prof_id = str(f_data.get("profile_sketch_id", ""))
                        traj_type = str(f_data.get("trajectory_type", "arc"))
                        rad = float(params.get("radius", 30.0))
                        h = float(params.get("height", 40.0))
                        turns = float(params.get("turns", 1.0))
                        k_steps = int(params.get("num_steps", 24))
                        n_segs = int(params.get("segments", 24))
                        feat = SweepFeature(f_id, f_name, prof_id, traj_type, rad, h, turns, k_steps, n_segs, op, target_id)

                    elif f_cls == "FilletFeature":
                        rad = float(params.get("radius", 2.0))
                        segs = int(params.get("segments", 16))
                        feat = FilletFeature(f_id, f_name, target_id or "", rad, segs)

                    elif f_cls == "ChamferFeature":
                        dist = float(params.get("distance", 2.0))
                        mode = str(f_data.get("edges_mode", "all"))
                        feat = ChamferFeature(f_id, f_name, target_id or "", dist, mode)

                    elif f_cls == "DraftFeature":
                        angle = float(params.get("draft_angle", 3.0))
                        axis = str(f_data.get("pull_axis", "Z"))
                        feat = DraftFeature(f_id, f_name, target_id or "", angle, axis)

                    elif f_cls == "ConeFeature":
                        r_bot = float(params.get("radius_bottom", 15.0))
                        r_top = float(params.get("radius_top", 0.0))
                        h = float(params.get("height", 30.0))
                        feat = ConeFeature(f_id, f_name, r_bot, r_top, h, 36, op, target_id)

                    elif f_cls == "TorusFeature":
                        r_maj = float(params.get("major_radius", 25.0))
                        r_min = float(params.get("minor_radius", 6.0))
                        feat = TorusFeature(f_id, f_name, r_maj, r_min, 36, op, target_id)

                    elif f_cls == "FastenerFeature":
                        ftype = str(f_data.get("fastener_type", "hex_bolt"))
                        size = str(f_data.get("standard_size", "M6"))
                        length = float(params.get("length", 30.0))
                        feat = FastenerFeature(f_id, f_name, ftype, size, length, op, target_id)

                    elif f_cls == "WedgeFeature":
                        dx = float(params.get("dx", 30.0))
                        dy = float(params.get("dy", 20.0))
                        dz = float(params.get("dz", 15.0))
                        dx_top = float(params.get("dx_top", 0.0))
                        dy_top = float(params.get("dy_top", 0.0))
                        feat = WedgeFeature(f_id, f_name, dx, dy, dz, dx_top, dy_top, op, target_id)

                    elif f_cls == "PipeFeature":
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
                        feat = PipeFeature(f_id, f_name, pts_list, r_out, r_in, op, target_id)

                    elif f_cls == "PocketFeature":
                        s_id = str(f_data.get("sketch_id", ""))
                        dep = float(params.get("depth", 10.0))
                        thru = bool(f_data.get("through_all", False) or params.get("through_all", 0.0) > 0.5)
                        rev = bool(f_data.get("reversed_dir", False) or params.get("reversed", 0.0) > 0.5)
                        feat = PocketFeature(f_id, f_name, s_id, dep, thru, rev, target_id)

                    elif f_cls == "DatumPlaneFeature":
                        bp_str = str(f_data.get("base_plane", "XY"))
                        bp = PlaneType(bp_str) if bp_str in PlaneType._value2member_map_ else PlaneType.XY
                        off = float(params.get("offset_distance", 0.0))
                        feat = DatumPlaneFeature(f_id, f_name, bp, off)

                    elif f_cls == "GrooveFeature":
                        s_id = str(f_data.get("sketch_id", ""))
                        ang = float(params.get("angle", 360.0))
                        segs = int(params.get("segments", 48))
                        feat = GrooveFeature(f_id, f_name, s_id, ang, segs, target_id)

                    elif f_cls == "MultiTransformFeature":
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
                        feat = MultiTransformFeature(f_id, f_name, src, steps_objs, join_b)

                    elif f_cls == "HelixFeature":
                        pitch = float(params.get("pitch", 10.0))
                        h = float(params.get("height", 40.0))
                        turns = float(params.get("turns", 4.0))
                        rad = float(params.get("radius", 15.0))
                        w_rad = float(params.get("wire_radius", 2.0))
                        c_ang = float(params.get("cone_angle", 0.0))
                        is_left = bool(params.get("is_left_handed", 0.0) > 0.5 or f_data.get("is_left_handed", False))
                        axis = str(f_data.get("axis", "Z"))
                        is_sub = bool(params.get("is_subtractive", 0.0) > 0.5 or f_data.get("is_subtractive", False))
                        feat = HelixFeature(
                            f_id, f_name, pitch=pitch, height=h, turns=turns, radius=rad,
                            wire_radius=w_rad, cone_angle=c_ang, is_left_handed=is_left,
                            axis=axis, is_subtractive=is_sub, operation=op, target_body_id=target_id
                        )

                    elif f_cls == "RibFeature":
                        s_id = str(f_data.get("sketch_id", ""))
                        thick = float(params.get("thickness", 4.0))
                        sym = bool(params.get("symmetric", 1.0) > 0.5 or f_data.get("symmetric", True))
                        draft = float(params.get("draft_angle", 0.0))
                        feat = RibFeature(f_id, f_name, sketch_id=s_id, thickness=thick, symmetric=sym, draft_angle=draft, target_body_id=target_id)

                    elif f_cls == "SplitFeature":
                        pl_str = str(f_data.get("plane", "XY"))
                        pl = PlaneType(pl_str) if pl_str in PlaneType._value2member_map_ else PlaneType.XY
                        off = float(params.get("plane_offset", 0.0))
                        side = str(f_data.get("keep_side", "positive"))
                        feat = SplitFeature(f_id, f_name, target_body_id=target_id or "", plane=pl, plane_offset=off, keep_side=side)

                    elif f_cls == "SubtractiveLoftFeature":
                        s_start = str(f_data.get("start_sketch_id", ""))
                        s_end = str(f_data.get("end_sketch_id", ""))
                        h_off = float(params.get("height_offset", 30.0))
                        s_top = float(params.get("scale_top", 1.0))
                        segs = int(params.get("num_segments", 36))
                        feat = SubtractiveLoftFeature(f_id, f_name, s_start, s_end, h_off, s_top, segs, target_id)

                    elif f_cls == "SubtractiveSweepFeature":
                        prof_id = str(f_data.get("profile_sketch_id", ""))
                        traj_type = str(f_data.get("trajectory_type", "arc"))
                        rad = float(params.get("radius", 30.0))
                        h = float(params.get("height", 40.0))
                        turns = float(params.get("turns", 1.0))
                        k_steps = int(params.get("num_steps", 24))
                        n_segs = int(params.get("segments", 24))
                        feat = SubtractiveSweepFeature(f_id, f_name, prof_id, traj_type, rad, h, turns, k_steps, n_segs, target_id)

                    if feat:
                        feat.is_suppressed = bool(f_data.get("is_suppressed", False))
                        doc.features.append(feat)

            # 3. Recalculer le modèle complet
            raw_rollback = data.get("rollback_index")
            if isinstance(raw_rollback, int):
                doc.rollback_index = raw_rollback
            else:
                doc.rollback_index = len(doc.features) - 1
            doc.rebuild()
            return doc
        except Exception:
            return None
