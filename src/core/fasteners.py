"""
Atelier Quincaillerie Mécanique & Visserie Standard (FreeCAD Fasteners Workbench Parity).
Générateur paramétrique de visserie métrique normalisée ISO / DIN :
- Vis à tête hexagonale (ISO 4017 / DIN 933)
- Vis à six pans creux CHC / BTR (ISO 4762 / DIN 912)
- Écrous hexagonaux (ISO 4032 / DIN 934)
- Rondelles plates (ISO 7089 / DIN 125)
Tailles métriques normalisées de M3 à M20. Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Sequence, Union
from dataclasses import dataclass
import numpy as np
import manifold3d as m

from src.core.types import BooleanOperation, FeatureStatus, Vector3D, Point2D
from src.core.geometry import Solid, make_cylinder
from src.core.feature import Feature, _apply_boolean_operation
from src.core.sketch import Sketch2D


@dataclass(frozen=True)
class MetricFastenerSpec:
    """Spécifications dimensionnelles normalisées d'une taille de visserie ISO."""
    nominal_dia: float     # Diamètre nominal d (mm)
    pitch: float           # Pas de vis métrique standard P (mm)
    hex_s: float           # Ouverture de clé / surplats tête et écrou s (mm)
    hex_k: float           # Hauteur de tête vis hexagonale k (mm)
    socket_dk: float       # Diamètre tête vis CHC dk (mm)
    socket_k: float        # Hauteur tête vis CHC k (mm)
    socket_s: float        # Clé Allen / six pans creux s (mm)
    nut_m: float           # Hauteur d'écrou m (mm)
    washer_d1: float       # Diamètre intérieur rondelle d1 (mm)
    washer_d2: float       # Diamètre extérieur rondelle d2 (mm)
    washer_s: float        # Épaisseur rondelle s (mm)


# Table des normes métriques ISO / DIN
ISO_METRIC_TABLE: Dict[str, MetricFastenerSpec] = {
    "M3": MetricFastenerSpec(3.0, 0.5, 5.5, 2.0, 5.5, 3.0, 2.5, 2.4, 3.2, 7.0, 0.5),
    "M4": MetricFastenerSpec(4.0, 0.7, 7.0, 2.8, 7.0, 4.0, 3.0, 3.2, 4.3, 9.0, 0.8),
    "M5": MetricFastenerSpec(5.0, 0.8, 8.0, 3.5, 8.5, 5.0, 4.0, 4.0, 5.3, 10.0, 1.0),
    "M6": MetricFastenerSpec(6.0, 1.0, 10.0, 4.0, 10.0, 6.0, 5.0, 5.0, 6.4, 12.0, 1.6),
    "M8": MetricFastenerSpec(8.0, 1.25, 13.0, 5.3, 13.0, 8.0, 6.0, 6.5, 8.4, 16.0, 1.6),
    "M10": MetricFastenerSpec(10.0, 1.5, 16.0, 6.4, 16.0, 10.0, 8.0, 8.0, 10.5, 20.0, 2.0),
    "M12": MetricFastenerSpec(12.0, 1.75, 18.0, 7.5, 18.0, 12.0, 10.0, 10.0, 13.0, 24.0, 2.5),
    "M16": MetricFastenerSpec(16.0, 2.0, 24.0, 10.0, 24.0, 16.0, 14.0, 13.0, 17.0, 30.0, 3.0),
    "M20": MetricFastenerSpec(20.0, 2.5, 30.0, 12.5, 30.0, 20.0, 17.0, 16.0, 21.0, 37.0, 3.0),
}


def _make_regular_polygon_cross_section(radius: float, num_sides: int = 6) -> m.CrossSection:
    """Génère un contour 2D de polygone régulier centré."""
    angles = np.linspace(0.0, 2.0 * np.pi, num_sides, endpoint=False)
    pts = [[float(radius * np.cos(a)), float(radius * np.sin(a))] for a in angles]
    return m.CrossSection([pts])


def create_hex_bolt(standard_size: str = "M6", length: float = 30.0, name: str = "HexBolt") -> Solid:
    """
    Crée une vis à tête hexagonale conforme ISO 4017 / DIN 933.
    """
    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    safe_len = max(2.0, length)
    shank_rad = spec.nominal_dia * 0.5

    # Corps cylindrique (tige filetée)
    shank_m = m.Manifold.cylinder(safe_len, shank_rad, shank_rad, 36, False)

    # Tête hexagonale (rayon circonscrit R = s / sqrt(3))
    r_circ = (spec.hex_s * 0.5) / float(np.cos(np.pi / 6.0))
    cs_hex = _make_regular_polygon_cross_section(r_circ, 6)
    head_m = m.Manifold.extrude(cs_hex, spec.hex_k).translate([0.0, 0.0, safe_len])

    combined = shank_m + head_m
    return Solid(combined, name)


def create_socket_head_cap_screw(standard_size: str = "M6", length: float = 25.0, name: str = "SocketScrew") -> Solid:
    """
    Crée une vis à six pans creux (CHC / BTR) conforme ISO 4762 / DIN 912.
    """
    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    safe_len = max(2.0, length)
    shank_rad = spec.nominal_dia * 0.5

    # Corps cylindrique
    shank_m = m.Manifold.cylinder(safe_len, shank_rad, shank_rad, 36, False)

    # Tête cylindrique
    head_rad = spec.socket_dk * 0.5
    head_m = m.Manifold.cylinder(spec.socket_k, head_rad, head_rad, 36, False).translate([0.0, 0.0, safe_len])

    # Empreinte six pans creux (clé Allen) soustraite de la tête
    r_hex_socket = (spec.socket_s * 0.5) / float(np.cos(np.pi / 6.0))
    socket_depth = spec.socket_k * 0.75
    cs_socket = _make_regular_polygon_cross_section(r_hex_socket, 6)
    socket_cutter = m.Manifold.extrude(cs_socket, socket_depth).translate([0.0, 0.0, safe_len + spec.socket_k - socket_depth])

    head_with_socket = head_m - socket_cutter
    combined = shank_m + head_with_socket
    return Solid(combined, name)


def create_hex_nut(standard_size: str = "M6", name: str = "HexNut") -> Solid:
    """
    Crée un écrou hexagonal conforme ISO 4032 / DIN 934.
    """
    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    r_circ = (spec.hex_s * 0.5) / float(np.cos(np.pi / 6.0))
    cs_hex = _make_regular_polygon_cross_section(r_circ, 6)
    nut_body = m.Manifold.extrude(cs_hex, spec.nut_m)

    # Alésage taraudé traversant
    hole_rad = spec.nominal_dia * 0.5
    hole_cutter = m.Manifold.cylinder(spec.nut_m * 1.2, hole_rad, hole_rad, 36, True).translate([0.0, 0.0, spec.nut_m * 0.5])

    nut_m_final = nut_body - hole_cutter
    return Solid(nut_m_final, name)


def create_washer(standard_size: str = "M6", name: str = "Washer") -> Solid:
    """
    Crée une rondelle plate conforme ISO 7089 / DIN 125.
    """
    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    r_out = spec.washer_d2 * 0.5
    r_in = spec.washer_d1 * 0.5
    th = spec.washer_s

    outer_cyl = m.Manifold.cylinder(th, r_out, r_out, 36, False)
    inner_cyl = m.Manifold.cylinder(th * 1.2, r_in, r_in, 36, True).translate([0.0, 0.0, th * 0.5])

    washer_m = outer_cyl - inner_cyl
    return Solid(washer_m, name)


class FastenerFeature(Feature):
    """
    Fonctionnalité paramétrique de visserie et boulonnerie normalisée.
    Insère des vis, écrous et rondelles directement dans la Timeline CAO.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Fastener",
        fastener_type: str = "hex_bolt",  # "hex_bolt", "socket_screw", "hex_nut", "washer"
        standard_size: str = "M6",
        length: float = 30.0,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None,
        has_washer: bool = False,
        thread_size: Optional[str] = None
    ) -> None:
        super().__init__(feature_id, name)
        self.fastener_type = "socket_screw" if fastener_type in ("socket_cap", "socket_screw") else fastener_type
        self.standard_size = thread_size if thread_size is not None else standard_size
        self.has_washer = has_washer
        self.parameters = {
            "length": float(length),
            "has_washer": 1.0 if has_washer else 0.0
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def get_parameters(self) -> Dict[str, Union[float, str, bool]]:
        """Retourne les paramètres de la quincaillerie."""
        return {
            "length": self.parameters.get("length", 30.0),
            "thread_size": self.standard_size,
            "standard_size": self.standard_size,
            "fastener_type": self.fastener_type,
            "has_washer": self.has_washer
        }

    def set_parameters(self, new_params: Dict[str, Union[float, str, bool]]) -> None:
        """Met à jour les paramètres de la quincaillerie."""
        for name, val in new_params.items():
            if name == "length" and isinstance(val, (int, float)):
                self.parameters["length"] = float(val)
            elif name in ("thread_size", "standard_size") and isinstance(val, str):
                self.standard_size = val
            elif name == "fastener_type" and isinstance(val, str):
                self.fastener_type = "socket_screw" if val in ("socket_cap", "socket_screw") else val
            elif name == "has_washer" and isinstance(val, bool):
                self.has_washer = val
                self.parameters["has_washer"] = 1.0 if val else 0.0
        self.status = FeatureStatus.OUTDATED

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la pièce de quincaillerie selon les normes industrielles."""
        l_val = self.parameters.get("length", 30.0)
        solid: Solid

        if self.fastener_type == "socket_screw":
            solid = create_socket_head_cap_screw(self.standard_size, l_val, self.name)
        elif self.fastener_type == "hex_nut":
            solid = create_hex_nut(self.standard_size, self.name)
        elif self.fastener_type == "washer":
            solid = create_washer(self.standard_size, self.name)
        else:  # hex_bolt
            solid = create_hex_bolt(self.standard_size, l_val, self.name)

        if self.has_washer and self.fastener_type in ("hex_bolt", "socket_screw"):
            washer_solid = create_washer(self.standard_size, f"{self.name}_Rondelle")
            solid = solid.union(washer_solid)

        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)
