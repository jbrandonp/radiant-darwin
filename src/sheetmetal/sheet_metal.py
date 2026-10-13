"""
Moteur de tôlerie industrielle (Sheet Metal Design) style Autodesk Fusion 360.
Calcule les pliages de tôle, la position de la fibre neutre via le Facteur K (K-factor),
la déduction au pli (Bend Deduction) et génère le déplié à plat (Flat Pattern).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import numpy as np

from src.core.types import Vector3D, Point2D, FeatureStatus
from src.core.geometry import Solid, make_box
from src.core.feature import Feature
from src.core.sketch import Sketch2D


@dataclass
class SheetMetalRule:
    """Règle de tôlerie définissant le comportement physique du métal au pliage."""
    name: str = "Acier 2mm Standard"
    thickness_mm: float = 2.0       # Épaisseur nominale de la tôle (t)
    bend_radius_mm: float = 2.0     # Rayon intérieur de pliage (R)
    k_factor: float = 0.44          # Facteur K standard pour l'acier (position fibre neutre)


@dataclass
class BendInfo:
    """Information géométrique sur un pli de tôlerie."""
    angle_deg: float
    flange_length_mm: float
    bend_allowance_mm: float
    bend_deduction_mm: float


@dataclass
class FlatPattern:
    """Modèle 2D du flan de tôle déplié à plat pour découpeuse laser ou poinçonneuse."""
    total_length_mm: float
    total_width_mm: float
    thickness_mm: float
    outline_points: List[Point2D] = field(default_factory=list)
    bend_centerlines: List[Tuple[Point2D, Point2D]] = field(default_factory=list)


class SheetMetalPart:
    """
    Composant de tôlerie paramétrique.
    Gère la tôle de base, l'ajout de rebords pliés (Flanges) et le dépliage à plat.
    """

    def __init__(
        self,
        base_width: float,
        base_length: float,
        rule: Optional[SheetMetalRule] = None
    ) -> None:
        """Initialise la tôle de base avec ses dimensions et la règle de pliage."""
        self.base_width = max(1.0, float(base_width))
        self.base_length = max(1.0, float(base_length))
        self.rule = rule or SheetMetalRule()
        self.bends: List[BendInfo] = []

    def calculate_bend_allowance(self, angle_deg: float) -> float:
        """
        Calcule le développement de l'arc de pliage (Bend Allowance BA).
        Formule normalisée : BA = (pi / 180) * angle * (R + K * t)
        """
        t = max(0.01, self.rule.thickness_mm)
        r = max(0.0, self.rule.bend_radius_mm)
        k = max(0.0, min(1.0, self.rule.k_factor))
        safe_angle = min(179.0, max(0.01, abs(angle_deg)))
        angle_rad = np.radians(safe_angle)
        return float(angle_rad * (r + k * t))

    def calculate_bend_deduction(self, angle_deg: float) -> float:
        """
        Calcule la perte au pli (Bend Deduction BD).
        Formule : BD = 2 * (R + t) * tan(angle / 2) - BA
        """
        t = max(0.01, self.rule.thickness_mm)
        r = max(0.0, self.rule.bend_radius_mm)
        safe_angle = min(179.0, max(0.01, abs(angle_deg)))
        angle_rad = np.radians(safe_angle)
        setback = (r + t) * np.tan(angle_rad / 2.0)
        ba = self.calculate_bend_allowance(safe_angle)
        return float(2.0 * setback - ba)

    def add_flange(self, length_mm: float, angle_deg: float = 90.0) -> BendInfo:
        """
        Ajoute un rebord plié (Flange) à l'extrémité de la tôle.
        """
        ba = self.calculate_bend_allowance(angle_deg)
        bd = self.calculate_bend_deduction(angle_deg)
        bend = BendInfo(
            angle_deg=float(angle_deg),
            flange_length_mm=max(1.0, float(length_mm)),
            bend_allowance_mm=ba,
            bend_deduction_mm=bd
        )
        self.bends.append(bend)
        return bend

    def generate_folded_solid(self) -> Solid:
        """
        Génère le corps 3D plié correspondant à la pièce finie.
        """
        t = self.rule.thickness_mm
        # Corps de base plat
        main_solid = make_box(self.base_width, self.base_length, t, center=False, name="SheetMetal_Base")

        # Ajouter chaque rebord plié
        current_y = self.base_length
        for idx, bend in enumerate(self.bends):
            h = bend.flange_length_mm
            # Rebord plié à 90 degrés selon Z
            flange_solid = make_box(self.base_width, t, h, center=False, name=f"Flange_{idx+1}")
            flange_solid = flange_solid.translate(Vector3D(0.0, current_y - t, t))
            main_solid = main_solid.union(flange_solid)

        return main_solid

    def generate_flat_pattern(self) -> FlatPattern:
        """
        Génère le patron 2D déplié à plat exact (Flat Pattern) pour la fabrication.
        Longueur développée = Longueur de base + somme des rebords - déductions de pliage.
        """
        t = self.rule.thickness_mm
        total_len = self.base_length

        bend_lines: List[Tuple[Point2D, Point2D]] = []
        acc_y = self.base_length

        for bend in self.bends:
            # Ligne de pliage
            bend_lines.append((
                Point2D(0.0, acc_y),
                Point2D(self.base_width, acc_y)
            ))
            # Longueur ajoutée avec correction K-factor
            added_length = bend.flange_length_mm - bend.bend_deduction_mm
            total_len += added_length
            acc_y += added_length

        w = self.base_width
        outline = [
            Point2D(0.0, 0.0),
            Point2D(w, 0.0),
            Point2D(w, total_len),
            Point2D(0.0, total_len)
        ]

        return FlatPattern(
            total_length_mm=total_len,
            total_width_mm=w,
            thickness_mm=t,
            outline_points=outline,
            bend_centerlines=bend_lines
        )


class SheetMetalFeature(Feature):
    """
    Fonctionnalité paramétrique de pièce de tôlerie pliée (Sheet Metal).
    S'intègre dans l'historique temporel et le calcul séquentiel du CADDocument.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Tôlerie Pliée",
        base_width: float = 60.0,
        base_length: float = 80.0,
        thickness: float = 2.0,
        bend_radius: float = 2.0,
        flange_length: float = 25.0,
        k_factor: float = 0.44,
        body_id: Optional[str] = None
    ) -> None:
        """Initialise la feature de tôlerie avec dimensions et règles de pliage."""
        super().__init__(feature_id, name)
        self.parameters = {
            "base_width": float(base_width),
            "base_length": float(base_length),
            "thickness": float(thickness),
            "bend_radius": float(bend_radius),
            "flange_length": float(flange_length),
            "k_factor": float(k_factor)
        }
        self.body_id: str = body_id or f"body_{feature_id}"

    def get_sheet_metal_part(self) -> SheetMetalPart:
        """Instancie le composant de tôlerie à partir des paramètres courants."""
        rule = SheetMetalRule(
            thickness_mm=self.parameters["thickness"],
            bend_radius_mm=self.parameters["bend_radius"],
            k_factor=self.parameters["k_factor"]
        )
        part = SheetMetalPart(
            base_width=self.parameters["base_width"],
            base_length=self.parameters["base_length"],
            rule=rule
        )
        flange_len = self.parameters["flange_length"]
        if flange_len > 0.0:
            part.add_flange(flange_len, 90.0)
        return part

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Évalue et génère le solide 3D plié dans la collection des corps du document."""
        result = dict(existing_bodies)
        part = self.get_sheet_metal_part()
        solid = part.generate_folded_solid()
        solid.name = self.name
        result[self.body_id] = solid
        self.status = FeatureStatus.OK
        return result
