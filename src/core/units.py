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
from typing import Dict, List, Tuple, Optional, Union


class UnitCategory(Enum):
    """Catégories physiques de grandeurs mesurables."""
    LENGTH = "length"
    ANGLE = "angle"
    MASS = "mass"
    FORCE = "force"
    PRESSURE = "pressure"
    TIME = "time"


# Exponentielle des dimensions fondamentales SI [M, L, T] (Masse, Longueur, Temps)
DIMENSION_BY_CATEGORY: Dict[UnitCategory, Tuple[int, int, int]] = {
    UnitCategory.LENGTH: (0, 1, 0),
    UnitCategory.ANGLE: (0, 0, 0),
    UnitCategory.MASS: (1, 0, 0),
    UnitCategory.FORCE: (1, 1, -2),
    UnitCategory.PRESSURE: (1, -1, -2),
    UnitCategory.TIME: (0, 0, 1),
}


@dataclass(frozen=True)
class UnitDefinition:
    """Définition d'une unité de mesure avec son facteur d'échelle et ses dimensions SI [M, L, T]."""
    symbol: str
    category: UnitCategory
    scale_to_base: float  # Facteur multiplicateur vers l'unité de référence (m, rad, kg, N, Pa, s)
    dimensions: Tuple[int, int, int] = (0, 0, 0)

    def __post_init__(self) -> None:
        if self.dimensions == (0, 0, 0) and self.category in DIMENSION_BY_CATEGORY:
            object.__setattr__(self, "dimensions", DIMENSION_BY_CATEGORY[self.category])


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

    # Superficie & Volume dérivés
    "m2": UnitDefinition("m2", UnitCategory.LENGTH, 1.0, dimensions=(0, 2, 0)),
    "mm2": UnitDefinition("mm2", UnitCategory.LENGTH, 1e-6, dimensions=(0, 2, 0)),
    "m3": UnitDefinition("m3", UnitCategory.LENGTH, 1.0, dimensions=(0, 3, 0)),
    "mm3": UnitDefinition("mm3", UnitCategory.LENGTH, 1e-9, dimensions=(0, 3, 0)),

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

    # Force & Énergie dérivée
    "n": UnitDefinition("n", UnitCategory.FORCE, 1.0),
    "kn": UnitDefinition("kn", UnitCategory.FORCE, 1e3),
    "lbf": UnitDefinition("lbf", UnitCategory.FORCE, 4.4482216152605),
    "j": UnitDefinition("j", UnitCategory.FORCE, 1.0, dimensions=(1, 2, -2)),
    "nm": UnitDefinition("nm", UnitCategory.FORCE, 1.0, dimensions=(1, 2, -2)),

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


def _resolve_unit_for_dimensions(dim: Tuple[int, int, int]) -> str:
    """Résout le symbole d'unité canonique pour un triplet dimensionnel [M, L, T]."""
    for symbol, u_def in UNIT_REGISTRY.items():
        if u_def.dimensions == dim and u_def.scale_to_base == 1.0:
            return symbol
    m, l, t = dim
    return f"M{m}_L{l}_T{t}"


@dataclass(frozen=True)
class PhysicalQuantity:
    """Grandeur physique scalaire associée à son unité de mesure et ses dimensions [M, L, T]."""
    value: float
    unit: str
    custom_dimensions: Optional[Tuple[int, int, int]] = None

    def __post_init__(self) -> None:
        u_key = self.unit.lower()
        if u_key not in UNIT_REGISTRY and self.custom_dimensions is None:
            raise ValueError(f"Unité physique inconnue : {self.unit}")

    @property
    def definition(self) -> Optional[UnitDefinition]:
        """Retourne la définition de l'unité active si enregistrée."""
        return UNIT_REGISTRY.get(self.unit.lower())

    @property
    def category(self) -> UnitCategory:
        """Retourne la catégorie physique (longueur, angle, masse, etc.)."""
        d = self.definition
        return d.category if d is not None else UnitCategory.LENGTH

    @property
    def dimensions(self) -> Tuple[int, int, int]:
        """Exposants dimensionnels SI [M, L, T] (Masse, Longueur, Temps)."""
        if self.custom_dimensions is not None:
            return self.custom_dimensions
        d = self.definition
        return d.dimensions if d is not None else (0, 0, 0)

    @property
    def value_si(self) -> float:
        """Valeur convertie dans l'unité de base internationale (SI)."""
        d = self.definition
        scale = d.scale_to_base if d is not None else 1.0
        return self.value * scale

    def to(self, target_unit: str) -> PhysicalQuantity:
        """Convertit la grandeur vers une unité compatible de même dimension."""
        t_key = target_unit.lower()
        if t_key not in UNIT_REGISTRY:
            raise ValueError(f"Unité cible inconnue : {target_unit}")
        t_def = UNIT_REGISTRY[t_key]
        if t_def.dimensions != self.dimensions:
            raise TypeError(
                f"Incompatibilité physique : impossible de convertir [M,L,T] {self.dimensions} en {t_def.dimensions}"
            )

        converted_val = self.value_si / t_def.scale_to_base
        return PhysicalQuantity(converted_val, target_unit, custom_dimensions=self.dimensions)

    def to_mm(self) -> float:
        """Raccourci de conversion rapide vers les millimètres (CAO standard)."""
        return self.to("mm").value

    def to_deg(self) -> float:
        """Raccourci de conversion rapide vers les degrés."""
        return self.to("deg").value

    def __add__(self, other: PhysicalQuantity) -> PhysicalQuantity:
        if self.dimensions != other.dimensions:
            raise TypeError(
                f"Incompatibilité dimensionnelle : impossible d'additionner des grandeurs de dimensions "
                f"[M, L, T] {self.dimensions} et {other.dimensions}."
            )
        other_converted = other.to(self.unit) if other.unit.lower() in UNIT_REGISTRY else other
        return PhysicalQuantity(self.value + other_converted.value, self.unit, custom_dimensions=self.dimensions)

    def __sub__(self, other: PhysicalQuantity) -> PhysicalQuantity:
        if self.dimensions != other.dimensions:
            raise TypeError(
                f"Incompatibilité dimensionnelle : impossible de soustraire des grandeurs de dimensions "
                f"[M, L, T] {self.dimensions} et {other.dimensions}."
            )
        other_converted = other.to(self.unit) if other.unit.lower() in UNIT_REGISTRY else other
        return PhysicalQuantity(self.value - other_converted.value, self.unit, custom_dimensions=self.dimensions)

    def __mul__(self, other: Union[float, int, PhysicalQuantity]) -> PhysicalQuantity:
        if isinstance(other, (int, float)):
            return PhysicalQuantity(self.value * float(other), self.unit, custom_dimensions=self.dimensions)
        if isinstance(other, PhysicalQuantity):
            new_val_si = self.value_si * other.value_si
            new_dim = (
                self.dimensions[0] + other.dimensions[0],
                self.dimensions[1] + other.dimensions[1],
                self.dimensions[2] + other.dimensions[2],
            )
            target_unit = _resolve_unit_for_dimensions(new_dim)
            scale = UNIT_REGISTRY[target_unit].scale_to_base if target_unit in UNIT_REGISTRY else 1.0
            return PhysicalQuantity(new_val_si / scale, target_unit, custom_dimensions=new_dim)
        raise TypeError(f"Opération de multiplication non supportée avec {type(other)}")

    def __truediv__(self, other: Union[float, int, PhysicalQuantity]) -> PhysicalQuantity:
        if isinstance(other, (int, float)):
            if abs(other) < 1e-12:
                raise ZeroDivisionError("Division par zéro d'une grandeur physique.")
            return PhysicalQuantity(self.value / float(other), self.unit, custom_dimensions=self.dimensions)
        if isinstance(other, PhysicalQuantity):
            if abs(other.value_si) < 1e-12:
                raise ZeroDivisionError("Division par zéro d'une grandeur physique.")
            new_val_si = self.value_si / other.value_si
            new_dim = (
                self.dimensions[0] - other.dimensions[0],
                self.dimensions[1] - other.dimensions[1],
                self.dimensions[2] - other.dimensions[2],
            )
            target_unit = _resolve_unit_for_dimensions(new_dim)
            scale = UNIT_REGISTRY[target_unit].scale_to_base if target_unit in UNIT_REGISTRY else 1.0
            return PhysicalQuantity(new_val_si / scale, target_unit, custom_dimensions=new_dim)
        raise TypeError(f"Opération de division non supportée avec {type(other)}")

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
