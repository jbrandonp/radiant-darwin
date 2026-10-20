"""
Importateur 2D DXF Pure-Python (AutoCAD R12 / 2000+).
Parse les entités géométriques 2D (LINE, ARC, CIRCLE, LWPOLYLINE avec bulge)
et les injecte directement dans une esquisse paramétrique Sketch2D.
Conforme aux standards de typage strict et SonarQube (complexité cognitive <= 25).
"""

from __future__ import annotations
import math
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, TextIO
import numpy as np

from src.core.types import Point2D, PlaneType
from src.core.sketch import Sketch2D


_DXF_UNIT_SCALES: Dict[int, float] = {
    0: 1.0,         # Non spécifié (défaut mm)
    1: 25.4,        # Pouces (Inches)
    2: 304.8,       # Pieds (Feet)
    3: 1609344.0,   # Miles
    4: 1.0,         # Millimètres
    5: 10.0,        # Centimètres
    6: 1000.0,      # Mètres
    7: 1000000.0,   # Kilomètres
    8: 0.0000254,   # Micro-pouces
    9: 0.0254,      # Mils
    10: 914.4,      # Yards
    14: 100.0,      # Décimètres
}


@dataclass
class DXFGroup:
    """Paire code de groupe / valeur lue dans le flux DXF."""
    code: int
    value: str


@dataclass
class DXFPolylineVertex:
    """Sommet d'une polyligne légère (LWPOLYLINE) avec facteur de cambrure (bulge)."""
    point: Point2D
    bulge: float = 0.0


class DXFImporter:
    """Moteur de lecture et conversion de fichiers CAO 2D au standard DXF."""

    @classmethod
    def parse_dxf_text(
        cls,
        dxf_text: str,
        sketch_name: str = "Imported_DXF",
        plane: PlaneType = PlaneType.XY
    ) -> Sketch2D:
        """Parse directement une chaîne de texte au format DXF en esquisse Sketch2D."""
        lines = [line.strip() for line in dxf_text.splitlines() if line.strip()]
        groups = cls._tokenize_dxf(lines)
        sketch = Sketch2D(sketch_id=f"sketch_{sketch_name.lower()}", name=sketch_name, plane=plane)
        unit_scale = cls._parse_header_units(groups)
        blocks = cls._parse_blocks(groups)
        cls._parse_entities(groups, sketch, unit_scale, blocks)
        return sketch

    @classmethod
    def import_dxf_to_sketch(
        cls,
        filepath: str,
        sketch_name: str = "Imported_DXF",
        plane: PlaneType = PlaneType.XY
    ) -> Sketch2D:
        """Lit un fichier .dxf et génère une esquisse Sketch2D correspondante."""
        if not filepath.lower().endswith(".dxf"):
            raise ValueError(f"Extension de fichier non supportée pour l'import DXF : {filepath}")
        safe_path = os.path.abspath(filepath)
        dir_name = os.path.dirname(safe_path)
        if dir_name and os.path.commonpath([dir_name, safe_path]) != dir_name:
            raise ValueError("Path traversal détecté")
        with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(10_000_000)
        return cls.parse_dxf_text(content, sketch_name=sketch_name, plane=plane)

    @classmethod
    def _tokenize_dxf(cls, lines: List[str]) -> List[DXFGroup]:
        """Convertit les lignes alternées (code, valeur) en liste de groupes DXF."""
        groups: List[DXFGroup] = []
        n = len(lines)
        i = 0
        while i < n - 1:
            try:
                code = int(lines[i])
                val = lines[i + 1]
                groups.append(DXFGroup(code=code, value=val))
                i += 2
            except ValueError:
                i += 1
        return groups

    @classmethod
    def _parse_header_units(cls, groups: List[DXFGroup]) -> float:
        """Détecte l'unité globale ($INSUNITS) dans le HEADER et retourne le facteur d'échelle vers mm."""
        in_header = False
        n = len(groups)
        for i in range(n):
            g = groups[i]
            if g.code == 0:
                if g.value == "ENDSEC" and in_header:
                    break
                in_header = (i + 1 < n and groups[i + 1].code == 2 and groups[i + 1].value == "HEADER")
            elif in_header and g.code == 9 and g.value == "$INSUNITS" and i + 1 < n:
                scale = cls._extract_insunits_val(groups[i + 1])
                if scale is not None:
                    return scale
        return 1.0

    @staticmethod
    def _extract_insunits_val(group: DXFGroup) -> Optional[float]:
        """Extrait la valeur entière de code d'unité INSUNITS."""
        if group.code != 70:
            return None
        try:
            return _DXF_UNIT_SCALES.get(int(group.value), 1.0)
        except ValueError:
            return None

    @classmethod
    def _parse_blocks(cls, groups: List[DXFGroup]) -> Dict[str, List[Tuple[str, List[DXFGroup]]]]:
        """Extrait les définitions de blocs (BLOCKS) et leurs géométries associées."""
        blocks: Dict[str, List[Tuple[str, List[DXFGroup]]]] = {}
        in_blocks = False
        n = len(groups)
        i = 0
        while i < n:
            g = groups[i]
            if g.code == 0 and g.value == "SECTION":
                if i + 1 < n and groups[i + 1].code == 2 and groups[i + 1].value == "BLOCKS":
                    in_blocks = True
                    i += 2
                    continue
            elif g.code == 0 and g.value == "ENDSEC":
                if in_blocks:
                    break
            if in_blocks and g.code == 0 and g.value == "BLOCK":
                i = cls._extract_single_block(groups, i + 1, blocks)
            else:
                i += 1
        return blocks

    @classmethod
    def _extract_single_block(
        cls,
        groups: List[DXFGroup],
        start_idx: int,
        blocks: Dict[str, List[Tuple[str, List[DXFGroup]]]]
    ) -> int:
        """Parse une définition de bloc individuelle jusqu'à ENDBLK."""
        block_name = ""
        entities: List[Tuple[str, List[DXFGroup]]] = []
        i = start_idx
        n = len(groups)
        while i < n:
            g = groups[i]
            if g.code == 0 and g.value == "ENDBLK":
                if block_name:
                    blocks[block_name] = entities
                return i + 1
            if not block_name and g.code == 2:
                block_name = g.value
                i += 1
                continue
            if g.code == 0:
                ent_type = g.value.upper()
                next_idx = cls._find_next_entity_idx(groups, i + 1)
                entities.append((ent_type, groups[i + 1 : next_idx]))
                i = next_idx
            else:
                i += 1
        return i

    @classmethod
    def _parse_entities(
        cls,
        groups: List[DXFGroup],
        sketch: Sketch2D,
        scale: float,
        blocks: Dict[str, List[Tuple[str, List[DXFGroup]]]]
    ) -> None:
        """Parcourt la section ENTITIES et extrait les primitives géométriques."""
        in_entities = False
        i = 0
        total = len(groups)

        while i < total:
            g = groups[i]
            if g.code == 0 and g.value == "SECTION":
                if i + 1 < total and groups[i + 1].code == 2 and groups[i + 1].value == "ENTITIES":
                    in_entities = True
                    i += 2
                    continue
            elif g.code == 0 and g.value == "ENDSEC":
                if in_entities:
                    break

            if in_entities and g.code == 0:
                ent_type = g.value.upper()
                next_ent_idx = cls._find_next_entity_idx(groups, i + 1)
                entity_groups = groups[i + 1 : next_ent_idx]
                cls._dispatch_entity(ent_type, entity_groups, sketch, scale, blocks)
                i = next_ent_idx
            else:
                i += 1

    @classmethod
    def _find_next_entity_idx(cls, groups: List[DXFGroup], start_idx: int) -> int:
        """Recherche l'indice du prochain enregistrement entité (code 0)."""
        idx = start_idx
        while idx < len(groups):
            if groups[idx].code == 0:
                return idx
            idx += 1
        return idx

    @classmethod
    def _dispatch_entity(
        cls,
        ent_type: str,
        entity_groups: List[DXFGroup],
        sketch: Sketch2D,
        scale: float,
        blocks: Dict[str, List[Tuple[str, List[DXFGroup]]]]
    ) -> None:
        """Achemine l'entité vers le parseur géométrique spécialisé."""
        if ent_type == "LINE":
            cls._parse_line(entity_groups, sketch, scale)
        elif ent_type == "CIRCLE":
            cls._parse_circle(entity_groups, sketch, scale)
        elif ent_type == "ARC":
            cls._parse_arc(entity_groups, sketch, scale)
        elif ent_type == "LWPOLYLINE":
            cls._parse_lwpolyline(entity_groups, sketch, scale)
        elif ent_type == "SPLINE":
            cls._parse_spline(entity_groups, sketch, scale)
        elif ent_type == "ELLIPSE":
            cls._parse_ellipse(entity_groups, sketch, scale)
        elif ent_type == "INSERT":
            cls._parse_insert(entity_groups, sketch, scale, blocks)

    @classmethod
    def _parse_line(cls, groups: List[DXFGroup], sketch: Sketch2D, scale: float) -> None:
        """Extrait un segment LINE défini par (10, 20) et (11, 21)."""
        x0: float = 0.0
        y0: float = 0.0
        x1: float = 0.0
        y1: float = 0.0
        for g in groups:
            if g.code == 10:
                x0 = float(g.value) * scale
            elif g.code == 20:
                y0 = float(g.value) * scale
            elif g.code == 11:
                x1 = float(g.value) * scale
            elif g.code == 21:
                y1 = float(g.value) * scale
        sketch.add_line(Point2D(x0, y0), Point2D(x1, y1))

    @classmethod
    def _parse_circle(cls, groups: List[DXFGroup], sketch: Sketch2D, scale: float) -> None:
        """Extrait un cercle CIRCLE défini par le centre (10, 20) et le rayon 40."""
        cx: float = 0.0
        cy: float = 0.0
        radius: float = 0.0
        for g in groups:
            if g.code == 10:
                cx = float(g.value) * scale
            elif g.code == 20:
                cy = float(g.value) * scale
            elif g.code == 40:
                radius = float(g.value) * scale
        if radius > 0.0:
            sketch.add_circle(Point2D(cx, cy), radius=radius)

    @classmethod
    def _parse_arc(cls, groups: List[DXFGroup], sketch: Sketch2D, scale: float) -> None:
        """Extrait un arc ARC défini par centre (10, 20), rayon 40, et angles (50, 51) en degrés."""
        cx: float = 0.0
        cy: float = 0.0
        radius: float = 0.0
        start_deg: float = 0.0
        end_deg: float = 0.0
        for g in groups:
            if g.code == 10:
                cx = float(g.value) * scale
            elif g.code == 20:
                cy = float(g.value) * scale
            elif g.code == 40:
                radius = float(g.value) * scale
            elif g.code == 50:
                start_deg = float(g.value)
            elif g.code == 51:
                end_deg = float(g.value)

        if radius > 0.0:
            start_rad = math.radians(start_deg)
            end_rad = math.radians(end_deg)
            sketch.add_arc(Point2D(cx, cy), radius=radius, start_angle_rad=start_rad, end_angle_rad=end_rad)

    @classmethod
    def _parse_lwpolyline(cls, groups: List[DXFGroup], sketch: Sketch2D, scale: float) -> None:
        """Extrait une polyligne 2D avec gestion analytique du facteur de courbure (bulge)."""
        vertices: List[DXFPolylineVertex] = []
        is_closed: bool = False
        curr_x: Optional[float] = None
        curr_y: Optional[float] = None
        curr_bulge: float = 0.0

        for g in groups:
            if g.code == 70:
                is_closed = bool(int(g.value) & 1)
            elif g.code == 10:
                if curr_x is not None and curr_y is not None:
                    vertices.append(DXFPolylineVertex(Point2D(curr_x, curr_y), curr_bulge))
                    curr_bulge = 0.0
                curr_x = float(g.value) * scale
            elif g.code == 20:
                curr_y = float(g.value) * scale
            elif g.code == 42:
                curr_bulge = float(g.value)

        if curr_x is not None and curr_y is not None:
            vertices.append(DXFPolylineVertex(Point2D(curr_x, curr_y), curr_bulge))

        num_v = len(vertices)
        if num_v < 2:
            return

        limit = num_v if is_closed else num_v - 1
        for j in range(limit):
            v0 = vertices[j]
            v1 = vertices[(j + 1) % num_v]
            if abs(v0.bulge) < 1e-6:
                sketch.add_line(v0.point, v1.point)
            else:
                cls._add_bulge_arc(sketch, v0.point, v1.point, v0.bulge)

    @classmethod
    def _parse_spline(cls, groups: List[DXFGroup], sketch: Sketch2D, scale: float) -> None:
        """Extrait une spline SPLINE et l'ajoute comme B-Spline analytique dans l'esquisse."""
        degree: int = 3
        is_closed: bool = False
        ctrl_pts: List[Point2D] = []
        curr_x: Optional[float] = None
        for g in groups:
            if g.code == 71:
                try:
                    degree = int(g.value)
                except ValueError:
                    pass
            elif g.code == 70:
                try:
                    is_closed = bool(int(g.value) & 1)
                except ValueError:
                    pass
            elif g.code == 10:
                curr_x = float(g.value) * scale
            elif g.code == 20:
                if curr_x is not None:
                    ctrl_pts.append(Point2D(curr_x, float(g.value) * scale))
                    curr_x = None
        if len(ctrl_pts) >= 2:
            sketch.add_bspline(ctrl_pts, degree=min(degree, max(1, len(ctrl_pts) - 1)), closed=is_closed)

    @classmethod
    def _parse_ellipse(cls, groups: List[DXFGroup], sketch: Sketch2D, scale: float) -> None:
        """Extrait une ellipse ou arc elliptique ELLIPSE et l'injecte dans l'esquisse."""
        cx: float = 0.0
        cy: float = 0.0
        mx: float = 0.0
        my: float = 0.0
        ratio: float = 1.0
        start_param: float = 0.0
        end_param: float = 2.0 * math.pi

        for g in groups:
            if g.code == 10:
                cx = float(g.value) * scale
            elif g.code == 20:
                cy = float(g.value) * scale
            elif g.code == 11:
                mx = float(g.value) * scale
            elif g.code == 21:
                my = float(g.value) * scale
            elif g.code == 40:
                ratio = max(1e-4, min(1.0, float(g.value)))
            elif g.code == 41:
                start_param = float(g.value)
            elif g.code == 42:
                end_param = float(g.value)

        major_len = math.hypot(mx, my)
        if major_len < 1e-6:
            return

        minor_len = major_len * ratio
        rot = math.atan2(my, mx)
        cos_rot = math.cos(rot)
        sin_rot = math.sin(rot)

        if end_param < start_param:
            end_param += 2.0 * math.pi
        span = end_param - start_param
        num_segs = max(16, int(span / (math.pi / 18.0)))
        t_vals = np.linspace(start_param, end_param, num_segs, endpoint=True)

        pts: List[Point2D] = []
        for t in t_vals:
            px_loc = major_len * math.cos(float(t))
            py_loc = minor_len * math.sin(float(t))
            gx = cx + px_loc * cos_rot - py_loc * sin_rot
            gy = cy + px_loc * sin_rot + py_loc * cos_rot
            pts.append(Point2D(gx, gy))

        if abs(span - 2.0 * math.pi) < 1e-3 and len(pts) >= 3:
            sketch.add_polygon(pts)
        else:
            for k in range(len(pts) - 1):
                sketch.add_line(pts[k], pts[k + 1])

    @classmethod
    def _parse_insert(
        cls,
        groups: List[DXFGroup],
        sketch: Sketch2D,
        scale: float,
        blocks: Dict[str, List[Tuple[str, List[DXFGroup]]]]
    ) -> None:
        """Déploie une référence de bloc INSERT avec translation, rotation et facteur d'échelle."""
        block_name: str = ""
        ins_x: float = 0.0
        ins_y: float = 0.0
        sx: float = 1.0
        sy: float = 1.0
        rot_deg: float = 0.0

        for g in groups:
            if g.code == 2:
                block_name = g.value
            elif g.code == 10:
                ins_x = float(g.value)
            elif g.code == 20:
                ins_y = float(g.value)
            elif g.code == 41:
                sx = float(g.value)
            elif g.code == 42:
                sy = float(g.value)
            elif g.code == 50:
                rot_deg = float(g.value)

        block_entities = blocks.get(block_name)
        if not block_entities:
            return

        rot_rad = math.radians(rot_deg)
        cos_t = math.cos(rot_rad)
        sin_t = math.sin(rot_rad)

        for b_type, b_groups in block_entities:
            trans_groups = cls._transform_entity_groups(b_groups, ins_x, ins_y, sx, sy, cos_t, sin_t)
            cls._dispatch_entity(b_type, trans_groups, sketch, scale, blocks)

    @classmethod
    def _transform_entity_groups(
        cls,
        groups: List[DXFGroup],
        ins_x: float,
        ins_y: float,
        sx: float,
        sy: float,
        cos_t: float,
        sin_t: float
    ) -> List[DXFGroup]:
        """Applique la transformation affine 2D aux codes de coordonnées DXF d'une entité de bloc."""
        res: List[DXFGroup] = []
        i = 0
        n = len(groups)
        while i < n:
            g = groups[i]
            if g.code == 10 and i + 1 < n and groups[i + 1].code == 20:
                x = float(g.value)
                y = float(groups[i + 1].value)
                tx, ty = cls._affine_point(x, y, ins_x, ins_y, sx, sy, cos_t, sin_t)
                res.extend([DXFGroup(10, str(tx)), DXFGroup(20, str(ty))])
                i += 2
                continue
            if g.code == 11 and i + 1 < n and groups[i + 1].code == 21:
                x = float(g.value)
                y = float(groups[i + 1].value)
                tx, ty = cls._affine_point(x, y, ins_x, ins_y, sx, sy, cos_t, sin_t)
                res.extend([DXFGroup(11, str(tx)), DXFGroup(21, str(ty))])
                i += 2
                continue
            if g.code == 40:
                res.append(DXFGroup(40, str(float(g.value) * abs(sx))))
                i += 1
                continue
            res.append(g)
            i += 1
        return res

    @staticmethod
    def _affine_point(
        x: float, y: float, ins_x: float, ins_y: float, sx: float, sy: float, cos_t: float, sin_t: float
    ) -> Tuple[float, float]:
        """Effectue l'échelle, rotation et translation d'un point 2D."""
        xs = x * sx
        ys = y * sy
        rx = xs * cos_t - ys * sin_t
        ry = xs * sin_t + ys * cos_t
        return (ins_x + rx, ins_y + ry)

    @classmethod
    def _add_bulge_arc(
        cls,
        sketch: Sketch2D,
        p1: Point2D,
        p2: Point2D,
        bulge: float
    ) -> None:
        """Convertit un segment à cambrure (bulge) en arc circulaire exact."""
        dx = p2.u - p1.u
        dy = p2.v - p1.v
        chord = math.hypot(dx, dy)
        if chord < 1e-9:
            return

        theta = 4.0 * math.atan(bulge)
        sin_half = math.sin(theta * 0.5)
        if abs(sin_half) < 1e-9:
            sketch.add_line(p1, p2)
            return

        radius = abs(chord / (2.0 * sin_half))
        sagitta = (chord * 0.5) * bulge
        h = (chord * 0.5) / math.tan(theta * 0.5)

        mx = (p1.u + p2.u) * 0.5
        my = (p1.v + p2.v) * 0.5
        nx = -dy / chord
        ny = dx / chord

        cx = mx + nx * h
        cy = my + ny * h

        start_angle = math.atan2(p1.v - cy, p1.u - cx)
        end_angle = math.atan2(p2.v - cy, p2.u - cx)

        if bulge > 0.0:
            if end_angle < start_angle:
                end_angle += 2.0 * math.pi
        else:
            if end_angle > start_angle:
                end_angle -= 2.0 * math.pi

        sketch.add_arc(Point2D(cx, cy), radius=radius, start_angle_rad=start_angle, end_angle_rad=end_angle)


# Alias d'interopérabilité
DXF2DImporter = DXFImporter

