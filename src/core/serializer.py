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
        """Désérialise un projet .cadproj et reconstruit l'arbre paramétrique."""
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        doc = CADDocument(name=data.get("name", "Projet Chargé"))

        # 1. Reconstruire les esquisses
        for sk_data in data.get("sketches", []):
            plane_val = sk_data.get("plane", "XY")
            plane = PlaneType(plane_val) if plane_val in PlaneType._value2member_map_ else PlaneType.XY
            sketch = Sketch2D(sk_data["id"], sk_data.get("name", "Esquisse"), plane=plane)

            for ent_dict in sk_data.get("entities", []):
                pts = [Point2D(coord[0], coord[1]) for coord in ent_dict.get("points", [])]
                if len(pts) >= 3:
                    sketch.add_polygon(pts)

            doc.sketches[sketch.sketch_id] = sketch

        # 2. Reconstruire les features
        for f_data in data.get("features", []):
            f_cls = f_data.get("class")
            f_id = f_data.get("id", "")
            f_name = f_data.get("name", "Feature")
            params = f_data.get("parameters", {})
            op_str = f_data.get("operation", "new_body")
            op = BooleanOperation(op_str) if op_str in BooleanOperation._value2member_map_ else BooleanOperation.NEW_BODY
            target_id = f_data.get("target_body_id")

            feat: Optional[Feature] = None

            if f_cls == "BoxFeature":
                w = params.get("width", 20.0)
                h = params.get("height", 20.0)
                d = params.get("depth", 20.0)
                center = bool(params.get("center", 0.0) > 0.5)
                feat = BoxFeature(f_id, f_name, w, h, d, center, op, target_id)

            elif f_cls == "CylinderFeature":
                rad = params.get("radius", 10.0)
                h = params.get("height", 30.0)
                feat = CylinderFeature(f_id, f_name, rad, h, 36, op, target_id)

            elif f_cls == "SphereFeature":
                rad = params.get("radius", 15.0)
                feat = SphereFeature(f_id, f_name, rad, 36, op, target_id)

            elif f_cls == "ExtrudeFeature":
                s_id = f_data.get("sketch_id", "")
                dist = params.get("distance", 25.0)
                feat = ExtrudeFeature(f_id, f_name, s_id, dist, op, target_id)

            elif f_cls == "RevolveFeature":
                s_id = f_data.get("sketch_id", "")
                ang = params.get("angle", 360.0)
                feat = RevolveFeature(f_id, f_name, s_id, ang, 48, op, target_id)

            elif f_cls == "HoleFeature":
                px = params.get("pos_x", 0.0)
                py = params.get("pos_y", 0.0)
                dia = params.get("diameter", 6.0)
                dep = params.get("depth", 30.0)
                feat = HoleFeature(f_id, f_name, target_id or "", px, py, dia, dep)

            elif f_cls == "ShellFeature":
                thick = params.get("wall_thickness", 2.0)
                feat = ShellFeature(f_id, f_name, target_id or "", thick)

            elif f_cls == "LinearPatternFeature":
                src = f_data.get("source_body_id", "")
                nx = int(params.get("count_x", 2))
                dx = params.get("spacing_x", 30.0)
                feat = LinearPatternFeature(f_id, f_name, src, nx, dx)

            elif f_cls == "BooleanFeature":
                tool_id = f_data.get("tool_body_id", "")
                feat = BooleanFeature(f_id, f_name, target_id or "", tool_id, op)

            elif f_cls == "SheetMetalFeature":
                bw = params.get("base_width", 60.0)
                bl = params.get("base_length", 80.0)
                th = params.get("thickness", 2.0)
                br = params.get("bend_radius", 2.0)
                fl = params.get("flange_length", 25.0)
                kf = params.get("k_factor", 0.44)
                feat = SheetMetalFeature(f_id, f_name, bw, bl, th, br, fl, kf, target_id)

            if feat:
                feat.is_suppressed = f_data.get("is_suppressed", False)
                doc.features.append(feat)

        # 3. Recalculer le modèle complet
        doc.rollback_index = data.get("rollback_index", len(doc.features) - 1)
        doc.rebuild()
        return doc
