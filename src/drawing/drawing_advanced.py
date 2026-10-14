"""
Mise en Plan Vectorielle Avancée : Coupes Brisées & Tolérancement Géométrique GD&T (Pillar 5).
Équivalent professionnel du module TechDraw de FreeCAD 1.0 et normes ISO 1101 / ASME Y14.5.
Fournit :
1. Les coupes locales partielles / écorchés (Broken-Out Section Views) avec hachures normalisées.
2. Les cadres de tolérancement géométrique (Feature Control Frames) avec symboles normalisés
   (planéité, perpendicularité, localisation, battement) et références d'éléments de référence (Datums A, B, C).
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional
import math

from src.core.types import Vector3D, Point2D


class GeometricCharacteristic(str, Enum):
    """Symboles normalisés de tolérancement géométrique ISO 1101 / ASME Y14.5."""
    STRAIGHTNESS = "straightness"         # Rectitude (—)
    FLATNESS = "flatness"                 # Planéité (⏥)
    CIRCULARITY = "circularity"           # Circularité (○)
    CYLINDRICITY = "cylindricity"         # Cylindricité (⌭)
    PROFILE_LINE = "profile_line"         # Profil d'une ligne (⌒)
    PROFILE_SURFACE = "profile_surface"   # Profil d'une surface (⌓)
    PERPENDICULARITY = "perpendicularity" # Perpendicularité (⟂)
    PARALLELISM = "parallelism"           # Parallélisme (∥)
    ANGULARITY = "angularity"             # Inclinaison (∠)
    POSITION = "position"                 # Localisation (⌖)
    CONCENTRICITY = "concentricity"       # Concentricité (◎)
    COAXIALITY = "coaxiality"             # Coaxialité
    SYMMETRY = "symmetry"                 # Symétrie (⌯)
    CIRCULAR_RUNOUT = "circular_runout"   # Battement simple (↗)
    TOTAL_RUNOUT = "total_runout"         # Battement total (⌰)


class MaterialCondition(str, Enum):
    """Modificateurs d'état de matière."""
    NONE = ""
    MAXIMUM_MATERIAL = "M"   # MMC: Ⓜ (Maximum Material Condition)
    LEAST_MATERIAL = "L"     # LMC: Ⓛ (Least Material Condition)
    REGARDLESS = "S"         # RFS: Ⓢ (Regardless of Feature Size)


@dataclass
class DatumReference:
    """Référence d'élément de référence (Datum) avec son modificateur éventuel."""
    datum_letter: str
    material_condition: MaterialCondition = MaterialCondition.NONE

    def format_text(self) -> str:
        """Formate le texte de la case de référence."""
        if self.material_condition != MaterialCondition.NONE:
            return f"{self.datum_letter} {self.material_condition.value}"
        return self.datum_letter


@dataclass
class FeatureControlFrame:
    """
    Cadre de tolérancement géométrique normalisé ISO 1101 / ASME Y14.5.
    Exemple: [ ⌖ | Ø 0.05 Ⓜ | A | B Ⓜ | C ]
    """
    characteristic: GeometricCharacteristic
    tolerance_value: float
    is_diameter_zone: bool = False
    material_condition: MaterialCondition = MaterialCondition.NONE
    primary_datum: Optional[DatumReference] = None
    secondary_datum: Optional[DatumReference] = None
    tertiary_datum: Optional[DatumReference] = None

    def get_symbol_unicode(self) -> str:
        """Retourne le glyphe ou symbole conventionnel ISO."""
        symbols = {
            GeometricCharacteristic.STRAIGHTNESS: "—",
            GeometricCharacteristic.FLATNESS: "⏥",
            GeometricCharacteristic.CIRCULARITY: "○",
            GeometricCharacteristic.CYLINDRICITY: "⌭",
            GeometricCharacteristic.PROFILE_LINE: "⌒",
            GeometricCharacteristic.PROFILE_SURFACE: "⌓",
            GeometricCharacteristic.PERPENDICULARITY: "⟂",
            GeometricCharacteristic.PARALLELISM: "∥",
            GeometricCharacteristic.ANGULARITY: "∠",
            GeometricCharacteristic.POSITION: "⌖",
            GeometricCharacteristic.CONCENTRICITY: "◎",
            GeometricCharacteristic.COAXIALITY: "◎",
            GeometricCharacteristic.SYMMETRY: "⌯",
            GeometricCharacteristic.CIRCULAR_RUNOUT: "↗",
            GeometricCharacteristic.TOTAL_RUNOUT: "⌰",
        }
        return symbols.get(self.characteristic, "?")

    def render_svg(self, x: float, y: float, cell_height: float = 24.0) -> str:
        """
        Génère les éléments SVG vectoriels pour dessiner le cadre rectangulaire compartimenté.
        """
        sym = self.get_symbol_unicode()
        dia_prefix = "Ø " if self.is_diameter_zone else ""
        mat_suffix = f" {self.material_condition.value}" if self.material_condition != MaterialCondition.NONE else ""
        tol_text = f"{dia_prefix}{self.tolerance_value:.3f}{mat_suffix}"

        cells: List[Tuple[str, float]] = [
            (sym, 32.0),
            (tol_text, 70.0)
        ]

        if self.primary_datum:
            cells.append((self.primary_datum.format_text(), 36.0))
        if self.secondary_datum:
            cells.append((self.secondary_datum.format_text(), 36.0))
        if self.tertiary_datum:
            cells.append((self.tertiary_datum.format_text(), 36.0))

        svg_parts: List[str] = []
        current_x = x

        for text, width in cells:
            svg_parts.append(
                f'<rect x="{current_x}" y="{y}" width="{width}" height="{cell_height}" '
                f'fill="#ffffff" stroke="#111827" stroke-width="1.5"/>'
            )
            mid_x = current_x + width / 2.0
            mid_y = y + cell_height * 0.7
            svg_parts.append(
                f'<text x="{mid_x}" y="{mid_y}" font-family="Arial, sans-serif" font-size="13" '
                f'font-weight="bold" text-anchor="middle" fill="#111827">{text}</text>'
            )
            current_x += width

        return "\n".join(svg_parts)


@dataclass
class BrokenOutSectionView:
    """
    Coupe locale partielle (écorché / Broken-Out Section).
    Définit un contour fermé 2D (spline ou polygone) sur une vue existante
    et une profondeur de pénétration 3D pour révéler l'intérieur de la pièce.
    """
    view_id: str
    boundary_polygon: List[Point2D]
    cutting_depth_mm: float
    hatch_angle_deg: float = 45.0
    hatch_spacing_mm: float = 2.5

    def is_point_inside_cutout(self, pt: Point2D) -> bool:
        """Algorithme Ray-Casting standard pour tester si un point 2D est dans le contour."""
        inside = False
        n = len(self.boundary_polygon)
        if n < 3:
            return False

        j = n - 1
        for i in range(n):
            pi = self.boundary_polygon[i]
            pj = self.boundary_polygon[j]
            if ((pi.y > pt.y) != (pj.y > pt.y)) and (
                pt.x < (pj.x - pi.x) * (pt.y - pi.y) / (pj.y - pi.y + 1e-12) + pi.x
            ):
                inside = not inside
            j = i

        return inside

    def generate_hatch_lines(
        self,
        bounding_box: Tuple[float, float, float, float]
    ) -> List[Tuple[Point2D, Point2D]]:
        """
        Génère les lignes de hachures à 45° restreintes à l'intérieur du contour de coupe.
        bounding_box = (min_x, min_y, max_x, max_y)
        """
        min_x, min_y, max_x, max_y = bounding_box
        hatch_lines: List[Tuple[Point2D, Point2D]] = []

        angle_rad = math.radians(self.hatch_angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        width = max_x - min_x
        height = max_y - min_y
        diagonal = math.sqrt(width * width + height * height)
        num_lines = int(diagonal / self.hatch_spacing_mm) + 2

        start_offset = -diagonal * 0.5

        for k in range(num_lines):
            d = start_offset + float(k) * self.hatch_spacing_mm
            # Ligne infinie paramétrique projetée
            # x * cos(a) + y * sin(a) = d
            p1 = Point2D(min_x, (d - min_x * cos_a) / (sin_a + 1e-9))
            p2 = Point2D(max_x, (d - max_x * cos_a) / (sin_a + 1e-9))

            # Échantillonnage pour segmenter à l'intérieur du polygone
            steps = 40
            current_segment_start: Optional[Point2D] = None

            for s in range(steps + 1):
                t = float(s) / float(steps)
                sx = p1.x + t * (p2.x - p1.x)
                sy = p1.y + t * (p2.y - p1.y)
                sample_pt = Point2D(sx, sy)

                inside = self.is_point_inside_cutout(sample_pt)
                if inside:
                    if current_segment_start is None:
                        current_segment_start = sample_pt
                else:
                    if current_segment_start is not None:
                        hatch_lines.append((current_segment_start, sample_pt))
                        current_segment_start = None

            if current_segment_start is not None:
                hatch_lines.append((current_segment_start, p2))

        return hatch_lines
