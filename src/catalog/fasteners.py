"""
Catalogue de Quincaillerie Mécanique & Visserie Standard (ISO / DIN).
Générateur géométrique paramétrique pour composants standards de visserie :
- Vis à tête hexagonale (ISO 4017 / DIN 933)
- Vis à six pans creux CHC / BTR (ISO 4762 / DIN 912)
- Écrous hexagonaux (ISO 4032 / DIN 934)
- Rondelles plates (ISO 7089 / DIN 125)
Tailles métriques normalisées de M3 à M20. Typage strict sans Any ni object.
Découplage strict pour éliminer toute dépendance circulaire avec src.core.
"""

from __future__ import annotations
import atexit
from typing import Dict, List, Optional, Tuple, Sequence, Union, TYPE_CHECKING
from dataclasses import dataclass
import numpy as np
import manifold3d as m

if TYPE_CHECKING:
    from src.core.geometry import Solid


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


_FASTENER_CACHE: Dict[Tuple[str, str, float], m.Manifold] = {}


def clear_fastener_cache() -> None:
    """Purge le cache mémoire de quincaillerie pour libérer les instances Manifold3D."""
    _FASTENER_CACHE.clear()


atexit.register(clear_fastener_cache)


def _make_regular_polygon_cross_section(radius: float, num_sides: int = 6) -> m.CrossSection:
    """Génère un contour 2D de polygone régulier centré."""
    angles = np.linspace(0.0, 2.0 * np.pi, num_sides, endpoint=False)
    pts = [[float(radius * np.cos(a)), float(radius * np.sin(a))] for a in angles]
    return m.CrossSection([pts])


def create_hex_bolt(standard_size: str = "M6", length: float = 30.0, name: str = "HexBolt") -> Solid:
    """Crée une vis à tête hexagonale conforme ISO 4017 / DIN 933 avec mémoïsation de forme."""
    from src.core.geometry import Solid
    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    safe_len = max(2.0, float(length))
    cache_key = ("hex_bolt", standard_size, safe_len)

    if cache_key in _FASTENER_CACHE:
        return Solid(_FASTENER_CACHE[cache_key], name)

    shank_rad = spec.nominal_dia * 0.5
    shank_m = m.Manifold.cylinder(safe_len, shank_rad, shank_rad, 36, False)

    r_circ = (spec.hex_s * 0.5) / float(np.cos(np.pi / 6.0))
    cs_hex = _make_regular_polygon_cross_section(r_circ, 6)
    head_m = m.Manifold.extrude(cs_hex, spec.hex_k).translate([0.0, 0.0, safe_len])

    combined = shank_m + head_m
    _FASTENER_CACHE[cache_key] = combined
    return Solid(combined, name)


def create_socket_head_cap_screw(standard_size: str = "M6", length: float = 25.0, name: str = "SocketScrew") -> Solid:
    """Crée une vis à six pans creux (CHC / BTR) conforme ISO 4762 / DIN 912 avec mémoïsation."""
    from src.core.geometry import Solid
    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    safe_len = max(2.0, float(length))
    cache_key = ("socket_screw", standard_size, safe_len)

    if cache_key in _FASTENER_CACHE:
        return Solid(_FASTENER_CACHE[cache_key], name)

    shank_rad = spec.nominal_dia * 0.5
    shank_m = m.Manifold.cylinder(safe_len, shank_rad, shank_rad, 36, False)

    head_rad = spec.socket_dk * 0.5
    head_m = m.Manifold.cylinder(spec.socket_k, head_rad, head_rad, 36, False).translate([0.0, 0.0, safe_len])

    r_hex_socket = (spec.socket_s * 0.5) / float(np.cos(np.pi / 6.0))
    socket_depth = spec.socket_k * 0.75
    cs_socket = _make_regular_polygon_cross_section(r_hex_socket, 6)
    socket_cutter = m.Manifold.extrude(cs_socket, socket_depth).translate([0.0, 0.0, safe_len + spec.socket_k - socket_depth])

    head_with_socket = head_m - socket_cutter
    combined = shank_m + head_with_socket
    _FASTENER_CACHE[cache_key] = combined
    return Solid(combined, name)


def create_hex_nut(standard_size: str = "M6", name: str = "HexNut") -> Solid:
    """Crée un écrou hexagonal conforme ISO 4032 / DIN 934 avec mémoïsation."""
    from src.core.geometry import Solid
    cache_key = ("hex_nut", standard_size, 0.0)
    if cache_key in _FASTENER_CACHE:
        return Solid(_FASTENER_CACHE[cache_key], name)

    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    r_circ = (spec.hex_s * 0.5) / float(np.cos(np.pi / 6.0))
    cs_hex = _make_regular_polygon_cross_section(r_circ, 6)
    nut_body = m.Manifold.extrude(cs_hex, spec.nut_m)

    hole_rad = spec.nominal_dia * 0.5
    hole_cutter = m.Manifold.cylinder(spec.nut_m * 1.2, hole_rad, hole_rad, 36, True).translate([0.0, 0.0, spec.nut_m * 0.5])

    nut_m_final = nut_body - hole_cutter
    _FASTENER_CACHE[cache_key] = nut_m_final
    return Solid(nut_m_final, name)


def create_washer(standard_size: str = "M6", name: str = "Washer") -> Solid:
    """Crée une rondelle plate conforme ISO 7089 / DIN 125 avec mémoïsation."""
    from src.core.geometry import Solid
    cache_key = ("washer", standard_size, 0.0)
    if cache_key in _FASTENER_CACHE:
        return Solid(_FASTENER_CACHE[cache_key], name)

    spec = ISO_METRIC_TABLE.get(standard_size, ISO_METRIC_TABLE["M6"])
    r_out = spec.washer_d2 * 0.5
    r_in = spec.washer_d1 * 0.5
    th = spec.washer_s

    outer_cyl = m.Manifold.cylinder(th, r_out, r_out, 36, False)
    inner_cyl = m.Manifold.cylinder(th * 1.2, r_in, r_in, 36, True).translate([0.0, 0.0, th * 0.5])

    washer_m = outer_cyl - inner_cyl
    _FASTENER_CACHE[cache_key] = washer_m
    return Solid(washer_m, name)
