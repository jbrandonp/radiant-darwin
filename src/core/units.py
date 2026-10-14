"""
Moteur de Gestion des Unités Physiques et Grandeurs Dimensionnelles (Pillar 8).
Permet la conversion automatique et le typage strict des unités en ingénierie :
longueur (mm, cm, m, in, ft), angle (deg, rad), masse (kg, g, lb), force (N, kN, lbf),
pression et contrainte (Pa, MPa, bar, psi).
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
from typing import Dict, List, Tuple, Optional


class UnitCategory(Enum):
    """Catégories physiques de grandeurs mesurables."""
    LENGTH = "length"
    ANGLE = "angle"
    MASS = "mass"
    FORCE = "force"
    PRESSURE = "pressure"
    TIME = "time"


@dataclass(frozen=True)
class UnitDefinition:
    """Définition d'une unité de mesure avec son facteur d'échelle vers l'unité SI de base."""
    symbol: str
    category: UnitCategory
    scale_to_base: float  # Facteur multiplicateur vers l'unité de référence (m, rad, kg, N, Pa, s)


# Table des unités de référence d'ingénierie
UNIT_REGISTRY: Dict[str, UnitDefinition] = {
    # Longueur (Base : mètre 'm')
    "m": UnitDefinition("m", UnitCategory.LENGTH, 1.0),
    "mm": UnitDefinition("mm", UnitCategory.LENGTH, 1e-3),
    "cm": UnitDefinition("cm", UnitCategory.LENGTH, 1e-2),
    "dm": UnitDefinition("dm", UnitCategory.LENGTH, 1e-1),
    "km": UnitDefinition("km", UnitCategory.LENGTH, 1e3),
    "in": UnitDefinition("in", UnitCategory.LENGTH, 0.0254),
    "inch": UnitDefinition("inch", UnitCategory.LENGTH, 0.0254),
    "ft": UnitDefinition("ft", UnitCategory.LENGTH, 0.3048),
    "mil": UnitDefinition("mil", UnitCategory.LENGTH, 2.54e-5),
    "thou": UnitDefinition("thou", UnitCategory.LENGTH, 2.54e-5),

    # Angle (Base : radian 'rad')
    "rad": UnitDefinition("rad", UnitCategory.ANGLE, 1.0),
    "deg": UnitDefinition("deg", UnitCategory.ANGLE, 0.017453292519943295),  # pi / 180
    "grad": UnitDefinition("grad", UnitCategory.ANGLE, 0.015707963267948967), # pi / 200

    # Masse (Base : kilogramme 'kg')
    "kg": UnitDefinition("kg", UnitCategory.MASS, 1.0),
    "g": UnitDefinition("g", UnitCategory.MASS, 1e-3),
    "mg": UnitDefinition("mg", UnitCategory.MASS, 1e-6),
    "ton": UnitDefinition("ton", UnitCategory.MASS, 1e3),
    "lb": UnitDefinition("lb", UnitCategory.MASS, 0.45359237),
    "oz": UnitDefinition("oz", UnitCategory.MASS, 0.028349523125),

    # Force (Base : Newton 'N')
    "n": UnitDefinition("n", UnitCategory.FORCE, 1.0),
    "kn": UnitDefinition("kn", UnitCategory.FORCE, 1e3),
    "lbf": UnitDefinition("lbf", UnitCategory.FORCE, 4.4482216152605),

    # Pression / Contrainte (Base : Pascal 'Pa')
    "pa": UnitDefinition("pa", UnitCategory.PRESSURE, 1.0),
    "kpa": UnitDefinition("kpa", UnitCategory.PRESSURE, 1e3),
    "mpa": UnitDefinition("mpa", UnitCategory.PRESSURE, 1e6),
    "bar": UnitDefinition("bar", UnitCategory.PRESSURE, 1e5),
    "psi": UnitDefinition("psi", UnitCategory.PRESSURE, 6894.757293168),

    # Temps (Base : seconde 's')
    "s": UnitDefinition("s", UnitCategory.TIME, 1.0),
    "min": UnitDefinition("min", UnitCategory.TIME, 60.0),
    "h": UnitDefinition("h", UnitCategory.TIME, 3600.0)
}


@dataclass(frozen=True)
class PhysicalQuantity:
    """Grandeur physique scalaire associée à son unité de mesure."""
    value: float
    unit: str

    def __post_init__(self) -> None:
        u_key = self.unit.lower()
        if u_key not in UNIT_REGISTRY:
            raise ValueError(f"Unité physique inconnue : {self.unit}")

    @property
    def definition(self) -> UnitDefinition:
        """Retourne la définition de l'unité active."""
        return UNIT_REGISTRY[self.unit.lower()]

    @property
    def category(self) -> UnitCategory:
        """Retourne la catégorie physique (longueur, angle, masse, etc.)."""
        return self.definition.category

    @property
    def value_si(self) -> float:
        """Valeur convertie dans l'unité de base internationale (SI)."""
        return self.value * self.definition.scale_to_base

    def to(self, target_unit: str) -> PhysicalQuantity:
        """Convertit la grandeur vers une unité compatible de même catégorie."""
        t_key = target_unit.lower()
        if t_key not in UNIT_REGISTRY:
            raise ValueError(f"Unité cible inconnue : {target_unit}")
        t_def = UNIT_REGISTRY[t_key]
        if t_def.category != self.category:
            raise TypeError(f"Incompatibilité physique : impossible de convertir {self.category.value} en {t_def.category.value}")

        converted_val = self.value_si / t_def.scale_to_base
        return PhysicalQuantity(converted_val, target_unit)

    def to_mm(self) -> float:
        """Raccourci de conversion rapide vers les millimètres (CAO standard)."""
        return self.to("mm").value

    def to_deg(self) -> float:
        """Raccourci de conversion rapide vers les degrés."""
        return self.to("deg").value

    def __add__(self, other: PhysicalQuantity) -> PhysicalQuantity:
        if self.category != other.category:
            raise TypeError("Addition impossible entre grandeurs de catégories physiques différentes.")
        other_converted = other.to(self.unit)
        return PhysicalQuantity(self.value + other_converted.value, self.unit)

    def __sub__(self, other: PhysicalQuantity) -> PhysicalQuantity:
        if self.category != other.category:
            raise TypeError("Soustraction impossible entre grandeurs de catégories physiques différentes.")
        other_converted = other.to(self.unit)
        return PhysicalQuantity(self.value - other_converted.value, self.unit)

    def __mul__(self, factor: float) -> PhysicalQuantity:
        return PhysicalQuantity(self.value * float(factor), self.unit)

    def __truediv__(self, divisor: float) -> PhysicalQuantity:
        if abs(divisor) < 1e-12:
            raise ZeroDivisionError("Division par zéro d'une grandeur physique.")
        return PhysicalQuantity(self.value / float(divisor), self.unit)

    def __str__(self) -> str:
        return f"{self.value:.4g} {self.unit}"


class UnitsParser:
    """
    Parseur d'expressions dimensionnelles composites pour les champs de saisie CAO.
    Exemples : "25.4 mm", "2.5 in + 10 mm", "45 deg", "150 MPa".
    """

    @classmethod
    def parse_single_quantity(cls, text: str) -> PhysicalQuantity:
        """Parse une valeur simple avec son suffixe d'unité (ex: '50.8 mm' ou '2 in')."""
        clean = text.strip()
        # Chercher le motif : nombre optionnellement flottant ou négatif suivi de lettres
        match = re.match(r"^([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)\s*([a-zA-Z]+)?$", clean)
        if not match:
            raise ValueError(f"Format de grandeur dimensionnelle invalide : '{text}'")

        val_str, unit_str = match.groups()
        val = float(val_str)
        unit = unit_str if unit_str else "mm"  # Millimètre par défaut en CAO mécanique
        return PhysicalQuantity(val, unit)

    @classmethod
    def parse_expression(cls, expression: str, target_unit: str = "mm") -> float:
        """
        Évalue une expression de sommes et soustractions dimensionnelles.
        Exemple : '1 in + 25.4 mm - 0.5 in' -> évalue en mm.
        """
        expr = expression.strip()
        if not expr:
            return 0.0

        # Remplacer les '+' et '-' par des délimiteurs sécurisés
        tokens = re.split(r"(\+|\-)", expr)
        current_op = "+"
        total_quantity: Optional[PhysicalQuantity] = None

        for token in tokens:
            t = token.strip()
            if not t:
                continue
            if t in ("+", "-"):
                current_op = t
                continue

            qty = cls.parse_single_quantity(t)
            if total_quantity is None:
                total_quantity = qty
            else:
                if current_op == "+":
                    total_quantity = total_quantity + qty
                else:
                    total_quantity = total_quantity - qty

        if total_quantity is None:
            return 0.0

        return total_quantity.to(target_unit).value
