"""
Générateur de plans techniques 2D (Engineering Drawing & Drafting ISO) style Autodesk Fusion 360.
Calcule les 4 projections orthogonales normalisées (Face, Dessus, Droite, Isométrique),
génère les cotations dimensionnelles et le cartouche ISO.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional
import numpy as np

from src.core.geometry import Solid
from src.core.types import Vector3D


class ViewType(Enum):
    """Types de vues normalisées sur la planche de dessin technique."""
    FRONT = "Vue de Face"
    TOP = "Vue de Dessus"
    RIGHT = "Vue de Droite"
    ISOMETRIC = "Vue Isométrique 3D"


@dataclass
class DrawingLine2D:
    """Segment de ligne 2D sur la planche de dessin (en mm de feuille)."""
    x1: float
    y1: float
    x2: float
    y2: float
    is_hidden: bool = False     # Ligne cachée en pointillés
    is_dimension: bool = False  # Ligne de cote
    is_hatch: bool = False      # Ligne de hachure de coupe ISO 128
    is_centerline: bool = False # Trait d'axe mixte long-court ISO 128


@dataclass
class DimensionLabel:
    """Cotation technique avec flèches et valeur numérique."""
    x: float
    y: float
    text: str
    is_vertical: bool = False


@dataclass
class TitleBlock:
    """Cartouche de mise en plan normalisé ISO."""
    project_title: str
    author: str = "Brandon"
    material: str = "Acier Carbone C45"
    scale: str = "1:1"
    date: str = "2026-10-13"
    sheet: str = "1 / 1"


@dataclass
class TechnicalSheet:
    """Feuille de dessin technique complète (Format A3 ou A4)."""
    width_mm: float = 420.0   # A3 Paysage standard
    height_mm: float = 297.0
    title_block: TitleBlock = field(default_factory=lambda: TitleBlock("Pièce Usinée"))
    lines: List[DrawingLine2D] = field(default_factory=list)
    dimensions: List[DimensionLabel] = field(default_factory=list)


class TechnicalDrawingGenerator:
    """
    Moteur de génération de plans techniques 2D conformes à la norme ISO 128.
    """

    def __init__(self, sheet_width: float = 420.0, sheet_height: float = 297.0) -> None:
        """Initialise la planche de dessin au format indiqué."""
        self.width = sheet_width
        self.height = sheet_height

    @classmethod
    def generate_views(
        cls,
        solid: Solid,
        title: str = "Composant Mécanique",
        author: str = "Brandon",
        material_name: str = "Aluminium 6061-T6"
    ) -> TechnicalSheet:
        """Génère la planche technique normalisée directement depuis la classe."""
        gen = cls()
        return gen.generate_sheet(solid, title=title, author=author, material_name=material_name)

    def generate_sheet(
        self,
        solid: Solid,
        title: str = "Composant Mécanique",
        author: str = "Brandon",
        material_name: str = "Aluminium 6061-T6"
    ) -> TechnicalSheet:
        """
        Extrait les projections orthogonales d'un solide et dispose les vues et cotations.
        """
        sheet = TechnicalSheet(
            width_mm=self.width,
            height_mm=self.height,
            title_block=TitleBlock(project_title=title, author=author, material=material_name)
        )

        # 1. Dessiner le cadre extérieur (Marge 10 mm)
        sheet.lines.extend([
            DrawingLine2D(10.0, 10.0, self.width - 10.0, 10.0),
            DrawingLine2D(self.width - 10.0, 10.0, self.width - 10.0, self.height - 10.0),
            DrawingLine2D(self.width - 10.0, self.height - 10.0, 10.0, self.height - 10.0),
            DrawingLine2D(10.0, self.height - 10.0, 10.0, 10.0),
        ])

        if solid.is_empty():
            return sheet

        b_min, b_max = solid.bounding_box()
        dx = max(1.0, b_max.x - b_min.x)
        dy = max(1.0, b_max.y - b_min.y)
        dz = max(1.0, b_max.z - b_min.z)

        # Calculer le facteur d'échelle automatique pour rentrer dans la planche
        max_dim = max(dx, dy, dz)
        scale = min(1.5, 90.0 / max_dim)
        sheet.title_block.scale = f"1:{1.0/scale:.1f}" if scale < 1.0 else f"{scale:.1f}:1"

        buf = solid.to_mesh_buffer()
        if buf.is_empty():
            return sheet

        # 2. Disposition des centres de vues (Méthode européenne du 1er dièdre)
        cx_front, cy_front = 110.0, 110.0
        cx_top, cy_top = 110.0, 215.0
        cx_right, cy_right = 230.0, 110.0
        cx_iso, cy_iso = 310.0, 220.0

        # Projection Face (Vue selon Y : coord X et Z)
        self._project_view(buf.vertices, buf.edges, cx_front, cy_front, scale, axis_h=0, axis_v=2, sheet=sheet)
        # Projection Dessus (Vue selon Z : coord X et Y)
        self._project_view(buf.vertices, buf.edges, cx_top, cy_top, scale, axis_h=0, axis_v=1, sheet=sheet)
        # Projection Droite (Vue selon X : coord Y et Z)
        self._project_view(buf.vertices, buf.edges, cx_right, cy_right, scale, axis_h=1, axis_v=2, sheet=sheet)
        # Projection Isométrique (Projection axonométrique 30 deg)
        self._project_isometric_view(buf.vertices, buf.edges, cx_iso, cy_iso, scale * 0.85, sheet=sheet)

        # 3. Ajout des cotations principales de référence
        # Cotation Largeur (X) sous la vue de face
        w_scaled = dx * scale
        sheet.lines.append(DrawingLine2D(cx_front - w_scaled / 2, cy_front - 15.0, cx_front + w_scaled / 2, cy_front - 15.0, is_dimension=True))
        sheet.dimensions.append(DimensionLabel(cx_front, cy_front - 18.0, f"{dx:.1f} mm"))

        # Cotation Hauteur (Z) à gauche de la vue de face
        h_scaled = dz * scale
        sheet.lines.append(DrawingLine2D(cx_front - w_scaled / 2 - 15.0, cy_front - h_scaled / 2, cx_front - w_scaled / 2 - 15.0, cy_front + h_scaled / 2, is_dimension=True))
        sheet.dimensions.append(DimensionLabel(cx_front - w_scaled / 2 - 25.0, cy_front, f"{dz:.1f} mm", is_vertical=True))

        # Cotation Profondeur (Y) au-dessus de la vue de dessus
        d_scaled = dy * scale
        sheet.dimensions.append(DimensionLabel(cx_top, cy_top + d_scaled / 2 + 10.0, f"Prof. {dy:.1f} mm"))

        return sheet

    def _project_view(
        self,
        vertices: np.ndarray,
        edges: np.ndarray,
        center_x: float,
        center_y: float,
        scale: float,
        axis_h: int,
        axis_v: int,
        sheet: TechnicalSheet
    ) -> None:
        """Projette les arêtes 3D sur un plan 2D selon deux axes cartésiens."""
        if len(edges) == 0:
            return

        h_coords = vertices[:, axis_h]
        v_coords = vertices[:, axis_v]
        mean_h = np.mean(h_coords)
        mean_v = np.mean(v_coords)

        for edge in edges:
            i0, i1 = int(edge[0]), int(edge[1])
            x1 = center_x + (h_coords[i0] - mean_h) * scale
            y1 = center_y + (v_coords[i0] - mean_v) * scale
            x2 = center_x + (h_coords[i1] - mean_h) * scale
            y2 = center_y + (v_coords[i1] - mean_v) * scale
            sheet.lines.append(DrawingLine2D(x1, y1, x2, y2))

    def _project_isometric_view(
        self,
        vertices: np.ndarray,
        edges: np.ndarray,
        center_x: float,
        center_y: float,
        scale: float,
        sheet: TechnicalSheet
    ) -> None:
        """Projette en vue isométrique avec angles de 30 degrés."""
        if len(edges) == 0:
            return

        # Matrice isométrique standard
        cos30 = np.cos(np.radians(30))
        sin30 = np.sin(np.radians(30))

        # x_iso = (x - y) * cos(30)
        # y_iso = (x + y) * sin(30) + z
        iso_x = (vertices[:, 0] - vertices[:, 1]) * cos30
        iso_y = (vertices[:, 0] + vertices[:, 1]) * sin30 + vertices[:, 2]

        mean_x = np.mean(iso_x)
        mean_y = np.mean(iso_y)

        for edge in edges:
            i0, i1 = int(edge[0]), int(edge[1])
            x1 = center_x + (iso_x[i0] - mean_x) * scale
            y1 = center_y + (iso_y[i0] - mean_y) * scale
            x2 = center_x + (iso_x[i1] - mean_x) * scale
            y2 = center_y + (iso_y[i1] - mean_y) * scale
            sheet.lines.append(DrawingLine2D(x1, y1, x2, y2))

    def generate_section_view(
        self,
        solid: Solid,
        cut_height: float = 0.0,
        center_x: float = 210.0,
        center_y: float = 150.0,
        scale: float = 1.0,
        hatch_spacing: float = 4.0,
        title: str = "Coupe A-A (Section View ISO)"
    ) -> TechnicalSheet:
        """
        Génère une vue en coupe technique normalisée (FreeCAD TechDraw Section View).
        Découpe le solide à la hauteur cut_height, projette le contour et applique
        des hachures diagonales à 45° selon la norme ISO 128.
        """
        sheet = TechnicalSheet(
            width_mm=self.width,
            height_mm=self.height,
            title_block=TitleBlock(project_title=title)
        )
        # Cadre extérieur (Marge 10 mm)
        sheet.lines.extend([
            DrawingLine2D(10.0, 10.0, self.width - 10.0, 10.0),
            DrawingLine2D(self.width - 10.0, 10.0, self.width - 10.0, self.height - 10.0),
            DrawingLine2D(self.width - 10.0, self.height - 10.0, 10.0, self.height - 10.0),
            DrawingLine2D(10.0, self.height - 10.0, 10.0, 10.0),
        ])

        if solid.is_empty():
            return sheet

        contours = solid.slice(cut_height)
        if not contours:
            return sheet

        # Calcul du centre moyen pour centrer la coupe à (center_x, center_y)
        all_u: List[float] = [pt.u for poly in contours for pt in poly]
        all_v: List[float] = [pt.v for poly in contours for pt in poly]
        mean_u = float(np.mean(all_u)) if all_u else 0.0
        mean_v = float(np.mean(all_v)) if all_v else 0.0

        for poly in contours:
            n = len(poly)
            if n < 3:
                continue

            # 1. Dessiner les arêtes du contour extérieur de coupe
            for i in range(n):
                p_curr = poly[i]
                p_next = poly[(i + 1) % n]
                x1 = center_x + (p_curr.u - mean_u) * scale
                y1 = center_y + (p_curr.v - mean_v) * scale
                x2 = center_x + (p_next.u - mean_u) * scale
                y2 = center_y + (p_next.v - mean_v) * scale
                sheet.lines.append(DrawingLine2D(x1, y1, x2, y2))

            # 2. Hachures ISO à 45 degrés dans le polygone
            poly_u = [pt.u for pt in poly]
            poly_v = [pt.v for pt in poly]
            min_u, max_u = min(poly_u), max(poly_u)
            min_v, max_v = min(poly_v), max(poly_v)

            # Ligne à 45 deg : v = u + c  =>  c = v - u
            c_min = min_v - max_u
            c_max = max_v - min_u
            step = hatch_spacing / scale if scale > 1e-4 else hatch_spacing

            c_val = c_min
            while c_val <= c_max:
                intersections: List[float] = []
                for i in range(n):
                    pa = poly[i]
                    pb = poly[(i + 1) % n]
                    du = pb.u - pa.u
                    dv = pb.v - pa.v
                    denom = dv - du
                    if abs(denom) > 1e-7:
                        t = (c_val - (pa.v - pa.u)) / denom
                        if 0.0 <= t <= 1.0:
                            intersections.append(pa.u + t * du)

                intersections.sort()
                for k in range(0, len(intersections) - 1, 2):
                    u_start = intersections[k]
                    u_end = intersections[k + 1]
                    v_start = u_start + c_val
                    v_end = u_end + c_val

                    hx1 = center_x + (u_start - mean_u) * scale
                    hy1 = center_y + (v_start - mean_v) * scale
                    hx2 = center_x + (u_end - mean_u) * scale
                    hy2 = center_y + (v_end - mean_v) * scale
                    sheet.lines.append(DrawingLine2D(hx1, hy1, hx2, hy2, is_hatch=True))

                c_val += step

        sheet.dimensions.append(DimensionLabel(center_x, center_y - 80.0, f"Coupe A-A (Z = {cut_height:.1f} mm)"))
        return sheet

    def add_centerline_cross(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        extension: float = 4.0,
        sheet: Optional[TechnicalSheet] = None
    ) -> List[DrawingLine2D]:
        """
        Ajoute une croix de traits d'axe normalisée ISO 128 (Centerline Cross)
        au centre d'un alésage, cylindre ou cercle de perçage.
        """
        span = radius + extension
        l_horiz = DrawingLine2D(center_x - span, center_y, center_x + span, center_y, is_centerline=True)
        l_vert = DrawingLine2D(center_x, center_y - span, center_x, center_y + span, is_centerline=True)
        lines = [l_horiz, l_vert]
        if sheet is not None:
            sheet.lines.extend(lines)
        return lines

    def add_bolt_circle_centerline(
        self,
        center_x: float,
        center_y: float,
        pitch_circle_radius: float,
        num_holes: int = 4,
        hole_radius: float = 3.0,
        sheet: Optional[TechnicalSheet] = None
    ) -> List[DrawingLine2D]:
        """
        Génère le cercle primitif d'axe (Pitch Circle Diameter PCD) et les croix
        d'axes sur chaque perçage selon les règles du dessin technique ISO (FreeCAD TechDraw CenterLine).
        """
        lines: List[DrawingLine2D] = []
        # Croix centrale
        lines.extend(self.add_centerline_cross(center_x, center_y, pitch_circle_radius, extension=6.0))

        # Discrétisation du cercle primitif en traits d'axe
        angles = np.linspace(0.0, 2.0 * np.pi, max(16, num_holes * 8), endpoint=True)
        for i in range(len(angles) - 1):
            a1 = angles[i]
            a2 = angles[i + 1]
            x1 = center_x + pitch_circle_radius * float(np.cos(a1))
            y1 = center_y + pitch_circle_radius * float(np.sin(a1))
            x2 = center_x + pitch_circle_radius * float(np.cos(a2))
            y2 = center_y + pitch_circle_radius * float(np.sin(a2))
            lines.append(DrawingLine2D(x1, y1, x2, y2, is_centerline=True))

        # Croix individuelles sur chaque trou
        hole_angles = np.linspace(0.0, 2.0 * np.pi, num_holes, endpoint=False)
        for ha in hole_angles:
            hx = center_x + pitch_circle_radius * float(np.cos(ha))
            hy = center_y + pitch_circle_radius * float(np.sin(ha))
            lines.extend(self.add_centerline_cross(hx, hy, hole_radius, extension=2.0))

        if sheet is not None:
            sheet.lines.extend(lines)
        return lines


