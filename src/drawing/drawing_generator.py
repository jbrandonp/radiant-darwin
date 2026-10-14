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
    is_hidden: bool = False   # Ligne cachée en pointillés
    is_dimension: bool = False # Ligne de cote


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
