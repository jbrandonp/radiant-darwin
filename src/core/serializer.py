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
    Feature, BoxFeature, CylinderFeature, SphereFeature, ExtrudeFeature, BooleanFeature
)
from src.core.operations_advanced import (
    RevolveFeature, LinearPatternFeature, CircularPatternFeature,
    MirrorFeature, HoleFeature, ShellFeature
)
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
                "entities": []
            }
            for ent in sk.entities:
                pts = [[pt.u, pt.v] for pt in ent.get_points()]
                cast_entities: List[object] = sk_data["entities"]  # type: ignore[assignment]
                cast_entities.append({
                    "id": ent.entity_id,
                    "type": ent.entity_type.value,
                    "points": pts
                })
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
                    sketch = Sketch2D(str(sk_data["id"]), str(sk_data.get("name", "Esquisse")), plane=plane)

                    entities_data = sk_data.get("entities", [])
                    if isinstance(entities_data, list):
                        for ent_dict in entities_data:
                            if not isinstance(ent_dict, dict):
                                continue
                            raw_pts = ent_dict.get("points", [])
                            if isinstance(raw_pts, list):
                                pts: List[Point2D] = []
                                for coord in raw_pts:
                                    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                                        try:
                                            pts.append(Point2D(float(coord[0]), float(coord[1])))
                                        except (ValueError, TypeError):
                                            pass
                                if len(pts) >= 3:
                                    sketch.add_polygon(pts)

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
                        feat = ExtrudeFeature(f_id, f_name, s_id, dist, op, target_id)

                    elif f_cls == "RevolveFeature":
                        s_id = str(f_data.get("sketch_id", ""))
                        ang = float(params.get("angle", 360.0))
                        feat = RevolveFeature(f_id, f_name, s_id, ang, 48, op, target_id)

                    elif f_cls == "HoleFeature":
                        px = float(params.get("pos_x", 0.0))
                        py = float(params.get("pos_y", 0.0))
                        dia = float(params.get("diameter", 6.0))
                        dep = float(params.get("depth", 30.0))
                        feat = HoleFeature(f_id, f_name, target_id or "", px, py, dia, dep)

                    elif f_cls == "ShellFeature":
                        thick = float(params.get("wall_thickness", 2.0))
                        feat = ShellFeature(f_id, f_name, target_id or "", thick)

                    elif f_cls == "LinearPatternFeature":
                        src = str(f_data.get("source_body_id", ""))
                        nx = int(params.get("count_x", 2))
                        dx = float(params.get("spacing_x", 30.0))
                        feat = LinearPatternFeature(f_id, f_name, src, nx, dx)

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
