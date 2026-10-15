"""
Importateur 2D SVG Pure-Python (Scalable Vector Graphics).
Parse les balises graphiques (<line>, <circle>, <rect>, <path d="...">)
et les convertit en géométrie paramétrique Sketch2D avec inversion d'axe Y conforme CAO.
Conforme aux standards de typage strict et SonarQube (complexité cognitive <= 25).
"""

from __future__ import annotations
import math
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Optional

from src.core.types import Point2D, PlaneType
from src.core.sketch import Sketch2D


class SVGImporter:
    """Moteur d'importation et de vectorisation SVG pour esquisses CAO 2D."""

    @classmethod
    def parse_svg_text(
        cls,
        svg_text: str,
        sketch_name: str = "Imported_SVG",
        plane: PlaneType = PlaneType.XY,
        invert_y: bool = True
    ) -> Sketch2D:
        """Parse directement un flux XML SVG en mémoire vers une esquisse Sketch2D."""
        root = ET.fromstring(svg_text)
        sketch = Sketch2D(sketch_id=f"sketch_{sketch_name.lower()}", name=sketch_name, plane=plane)
        height = cls._extract_svg_height(root)

        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "line":
                cls._parse_svg_line(elem, sketch, height, invert_y)
            elif tag == "circle":
                cls._parse_svg_circle(elem, sketch, height, invert_y)
            elif tag == "rect":
                cls._parse_svg_rect(elem, sketch, height, invert_y)
            elif tag == "path":
                cls._parse_svg_path(elem, sketch, height, invert_y)

        return sketch

    @classmethod
    def import_svg_to_sketch(
        cls,
        filepath: str,
        sketch_name: str = "Imported_SVG",
        plane: PlaneType = PlaneType.XY,
        invert_y: bool = True
    ) -> Sketch2D:
        """Lit un fichier SVG et crée l'esquisse correspondante."""
        if not filepath.lower().endswith((".svg", ".xml")):
            raise ValueError(f"Extension de fichier non supportée pour l'import SVG : {filepath}")
        safe_path = os.path.abspath(filepath)
        dir_name = os.path.dirname(safe_path)
        if dir_name and os.path.commonpath([dir_name, safe_path]) != dir_name:
            raise ValueError("Path traversal détecté")
        with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(10_000_000)
        return cls.parse_svg_text(content, sketch_name=sketch_name, plane=plane, invert_y=invert_y)

    @classmethod
    def _extract_svg_height(cls, root: ET.Element) -> float:
        """Extrait la hauteur globale du viewBox ou attribut height pour l'inversion Y."""
        vb = root.attrib.get("viewBox")
        if vb:
            parts = [float(p) for p in re.split(r"[\s,]+", vb.strip()) if p]
            if len(parts) >= 4:
                return parts[3]

        h_str = root.attrib.get("height", "100.0")
        try:
            return float(re.sub(r"[^\d.]", "", h_str))
        except ValueError:
            return 100.0

    @classmethod
    def _map_pt(cls, x: float, y: float, height: float, invert_y: bool) -> Point2D:
        """Mappe une coordonnée écran SVG vers le repère orthonormé CAD (Y vers le haut)."""
        actual_y = (height - y) if invert_y else y
        return Point2D(x, actual_y)

    @classmethod
    def _parse_svg_line(
        cls, elem: ET.Element, sketch: Sketch2D, height: float, invert_y: bool
    ) -> None:
        """Parse un élément <line>."""
        try:
            x1 = float(elem.attrib.get("x1", "0"))
            y1 = float(elem.attrib.get("y1", "0"))
            x2 = float(elem.attrib.get("x2", "0"))
            y2 = float(elem.attrib.get("y2", "0"))
            p1 = cls._map_pt(x1, y1, height, invert_y)
            p2 = cls._map_pt(x2, y2, height, invert_y)
            sketch.add_line(p1, p2)
        except (ValueError, KeyError):
            pass

    @classmethod
    def _parse_svg_circle(
        cls, elem: ET.Element, sketch: Sketch2D, height: float, invert_y: bool
    ) -> None:
        """Parse un élément <circle>."""
        try:
            cx = float(elem.attrib.get("cx", "0"))
            cy = float(elem.attrib.get("cy", "0"))
            r = float(elem.attrib.get("r", "0"))
            if r > 0.0:
                center = cls._map_pt(cx, cy, height, invert_y)
                sketch.add_circle(center, radius=r)
        except (ValueError, KeyError):
            pass

    @classmethod
    def _parse_svg_rect(
        cls, elem: ET.Element, sketch: Sketch2D, height: float, invert_y: bool
    ) -> None:
        """Parse un élément <rect>."""
        try:
            x = float(elem.attrib.get("x", "0"))
            y = float(elem.attrib.get("y", "0"))
            w = float(elem.attrib.get("width", "0"))
            h = float(elem.attrib.get("height", "0"))
            if w > 0.0 and h > 0.0:
                p0 = cls._map_pt(x, y, height, invert_y)
                p1 = cls._map_pt(x + w, y, height, invert_y)
                p2 = cls._map_pt(x + w, y + h, height, invert_y)
                p3 = cls._map_pt(x, y + h, height, invert_y)
                sketch.add_line(p0, p1)
                sketch.add_line(p1, p2)
                sketch.add_line(p2, p3)
                sketch.add_line(p3, p0)
        except (ValueError, KeyError):
            pass

    @classmethod
    def _handle_move_to(
        cls, tokens: List[str], idx: int, cmd: str, curr_x: float, curr_y: float
    ) -> Tuple[float, float, float, float, int, str]:
        """Traite une commande MoveTo M ou m."""
        x = float(tokens[idx])
        y = float(tokens[idx + 1])
        new_idx = idx + 2
        new_x = curr_x + x if cmd == "m" else x
        new_y = curr_y + y if cmd == "m" else y
        next_cmd = "L" if cmd == "M" else "l"
        return new_x, new_y, new_x, new_y, new_idx, next_cmd

    @classmethod
    def _handle_line_to(
        cls,
        tokens: List[str],
        idx: int,
        cmd: str,
        curr_x: float,
        curr_y: float,
        height: float,
        invert_y: bool,
        sketch: Sketch2D,
    ) -> Tuple[float, float, int]:
        """Traite une commande LineTo L ou l."""
        x = float(tokens[idx])
        y = float(tokens[idx + 1])
        new_idx = idx + 2
        target_x = curr_x + x if cmd == "l" else x
        target_y = curr_y + y if cmd == "l" else y
        p1 = cls._map_pt(curr_x, curr_y, height, invert_y)
        p2 = cls._map_pt(target_x, target_y, height, invert_y)
        sketch.add_line(p1, p2)
        return target_x, target_y, new_idx

    @classmethod
    def _handle_horizontal_to(
        cls,
        tokens: List[str],
        idx: int,
        cmd: str,
        curr_x: float,
        curr_y: float,
        height: float,
        invert_y: bool,
        sketch: Sketch2D,
    ) -> Tuple[float, int]:
        """Traite une commande horizontale H ou h."""
        x = float(tokens[idx])
        new_idx = idx + 1
        target_x = curr_x + x if cmd == "h" else x
        p1 = cls._map_pt(curr_x, curr_y, height, invert_y)
        p2 = cls._map_pt(target_x, curr_y, height, invert_y)
        sketch.add_line(p1, p2)
        return target_x, new_idx

    @classmethod
    def _handle_vertical_to(
        cls,
        tokens: List[str],
        idx: int,
        cmd: str,
        curr_x: float,
        curr_y: float,
        height: float,
        invert_y: bool,
        sketch: Sketch2D,
    ) -> Tuple[float, int]:
        """Traite une commande verticale V ou v."""
        y = float(tokens[idx])
        new_idx = idx + 1
        target_y = curr_y + y if cmd == "v" else y
        p1 = cls._map_pt(curr_x, curr_y, height, invert_y)
        p2 = cls._map_pt(curr_x, target_y, height, invert_y)
        sketch.add_line(p1, p2)
        return target_y, new_idx

    @classmethod
    def _handle_cubic_to(
        cls,
        tokens: List[str],
        idx: int,
        cmd: str,
        curr_x: float,
        curr_y: float,
        height: float,
        invert_y: bool,
        sketch: Sketch2D,
    ) -> Tuple[float, float, int]:
        """Traite une courbe de Bézier cubique C ou c."""
        x1 = float(tokens[idx])
        y1 = float(tokens[idx + 1])
        x2 = float(tokens[idx + 2])
        y2 = float(tokens[idx + 3])
        x = float(tokens[idx + 4])
        y = float(tokens[idx + 5])
        new_idx = idx + 6

        if cmd == "c":
            x1 += curr_x
            y1 += curr_y
            x2 += curr_x
            y2 += curr_y
            x += curr_x
            y += curr_y

        p0 = cls._map_pt(curr_x, curr_y, height, invert_y)
        p_c1 = cls._map_pt(x1, y1, height, invert_y)
        p_c2 = cls._map_pt(x2, y2, height, invert_y)
        p_end = cls._map_pt(x, y, height, invert_y)
        sketch.add_bezier([p0, p_c1, p_c2, p_end])
        return x, y, new_idx

    @classmethod
    def _handle_close_path(
        cls,
        curr_x: float,
        curr_y: float,
        start_x: float,
        start_y: float,
        height: float,
        invert_y: bool,
        sketch: Sketch2D,
    ) -> Tuple[float, float]:
        """Traite la fermeture de contour Z ou z."""
        p1 = cls._map_pt(curr_x, curr_y, height, invert_y)
        p2 = cls._map_pt(start_x, start_y, height, invert_y)
        if abs(p1.u - p2.u) > 1e-6 or abs(p1.v - p2.v) > 1e-6:
            sketch.add_line(p1, p2)
        return start_x, start_y

    @classmethod
    def _parse_svg_path(
        cls, elem: ET.Element, sketch: Sketch2D, height: float, invert_y: bool
    ) -> None:
        """Parse un élément <path d="..."> avec commandes standard M, L, H, V, C, Z."""
        d = elem.attrib.get("d", "").strip()
        if not d:
            return

        tokens = re.findall(r"([A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)", d)
        if not tokens:
            return

        curr_x, curr_y = 0.0, 0.0
        start_x, start_y = 0.0, 0.0
        cmd = ""
        idx, total = 0, len(tokens)

        while idx < total:
            tok = tokens[idx]
            if tok.isalpha():
                cmd = tok
                idx += 1
                if cmd in ("Z", "z"):
                    curr_x, curr_y = cls._handle_close_path(
                        curr_x, curr_y, start_x, start_y, height, invert_y, sketch
                    )
                continue

            if cmd in ("M", "m"):
                curr_x, curr_y, start_x, start_y, idx, cmd = cls._handle_move_to(
                    tokens, idx, cmd, curr_x, curr_y
                )
            elif cmd in ("L", "l"):
                curr_x, curr_y, idx = cls._handle_line_to(
                    tokens, idx, cmd, curr_x, curr_y, height, invert_y, sketch
                )
            elif cmd in ("H", "h"):
                curr_x, idx = cls._handle_horizontal_to(
                    tokens, idx, cmd, curr_x, curr_y, height, invert_y, sketch
                )
            elif cmd in ("V", "v"):
                curr_y, idx = cls._handle_vertical_to(
                    tokens, idx, cmd, curr_x, curr_y, height, invert_y, sketch
                )
            elif cmd in ("C", "c"):
                curr_x, curr_y, idx = cls._handle_cubic_to(
                    tokens, idx, cmd, curr_x, curr_y, height, invert_y, sketch
                )
            else:
                idx += 1
