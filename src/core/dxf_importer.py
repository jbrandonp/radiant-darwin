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

from src.core.types import Point2D, PlaneType
from src.core.sketch import Sketch2D


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
        cls._parse_entities(groups, sketch)
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
    def _parse_entities(cls, groups: List[DXFGroup], sketch: Sketch2D) -> None:
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
                cls._dispatch_entity(ent_type, entity_groups, sketch)
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
        sketch: Sketch2D
    ) -> None:
        """Achemine l'entité vers le parseur géométrique spécialisé."""
        if ent_type == "LINE":
            cls._parse_line(entity_groups, sketch)
        elif ent_type == "CIRCLE":
            cls._parse_circle(entity_groups, sketch)
        elif ent_type == "ARC":
            cls._parse_arc(entity_groups, sketch)
        elif ent_type == "LWPOLYLINE":
            cls._parse_lwpolyline(entity_groups, sketch)

    @classmethod
    def _parse_line(cls, groups: List[DXFGroup], sketch: Sketch2D) -> None:
        """Extrait un segment LINE défini par (10, 20) et (11, 21)."""
        x0: float = 0.0
        y0: float = 0.0
        x1: float = 0.0
        y1: float = 0.0
        for g in groups:
            if g.code == 10:
                x0 = float(g.value)
            elif g.code == 20:
                y0 = float(g.value)
            elif g.code == 11:
                x1 = float(g.value)
            elif g.code == 21:
                y1 = float(g.value)
        sketch.add_line(Point2D(x0, y0), Point2D(x1, y1))

    @classmethod
    def _parse_circle(cls, groups: List[DXFGroup], sketch: Sketch2D) -> None:
        """Extrait un cercle CIRCLE défini par le centre (10, 20) et le rayon 40."""
        cx: float = 0.0
        cy: float = 0.0
        radius: float = 0.0
        for g in groups:
            if g.code == 10:
                cx = float(g.value)
            elif g.code == 20:
                cy = float(g.value)
            elif g.code == 40:
                radius = float(g.value)
        if radius > 0.0:
            sketch.add_circle(Point2D(cx, cy), radius=radius)

    @classmethod
    def _parse_arc(cls, groups: List[DXFGroup], sketch: Sketch2D) -> None:
        """Extrait un arc ARC défini par centre (10, 20), rayon 40, et angles (50, 51) en degrés."""
        cx: float = 0.0
        cy: float = 0.0
        radius: float = 0.0
        start_deg: float = 0.0
        end_deg: float = 0.0
        for g in groups:
            if g.code == 10:
                cx = float(g.value)
            elif g.code == 20:
                cy = float(g.value)
            elif g.code == 40:
                radius = float(g.value)
            elif g.code == 50:
                start_deg = float(g.value)
            elif g.code == 51:
                end_deg = float(g.value)

        if radius > 0.0:
            start_rad = math.radians(start_deg)
            end_rad = math.radians(end_deg)
            sketch.add_arc(Point2D(cx, cy), radius=radius, start_angle_rad=start_rad, end_angle_rad=end_rad)

    @classmethod
    def _parse_lwpolyline(cls, groups: List[DXFGroup], sketch: Sketch2D) -> None:
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
                curr_x = float(g.value)
            elif g.code == 20:
                curr_y = float(g.value)
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

