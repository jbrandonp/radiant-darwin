"""
Base de données des matériaux physiques d'ingénierie et calculs de masse/inertie.
Inspiré de la bibliothèque de matériaux d'Autodesk Fusion 360.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.core.types import ColorRGBA, Vector3D
from src.core.geometry import Solid


@dataclass(frozen=True)
class PhysicalMaterial:
    """
    Propriétés physiques, mécaniques et thermiques réelles d'un matériau.
    Utilisé pour le calcul de masse, la simulation FEA et le rendu PBR.
    """
    name: str
    category: str
    density_g_cm3: float          # Densité en g/cm³
    young_modulus_gpa: float      # Module d'élasticité (Young) E en GPa
    poisson_ratio: float          # Coefficient de Poisson ν
    yield_strength_mpa: float     # Limite d'élasticité Re en MPa
    ultimate_strength_mpa: float  # Résistance à la traction Rm en MPa
    thermal_conductivity: float   # Conductivité thermique W/(m·K)
    color: ColorRGBA              # Rendu visuel PBR

    @property
    def density_kg_m3(self) -> float:
        """Convertit la densité en kg/m³."""
        return self.density_g_cm3 * 1000.0


# Bibliothèque standard des matériaux industriels
MATERIAL_LIBRARY: Dict[str, PhysicalMaterial] = {
    "Aluminium 6061-T6": PhysicalMaterial(
        name="Aluminium 6061-T6",
        category="Métaux",
        density_g_cm3=2.70,
        young_modulus_gpa=68.9,
        poisson_ratio=0.33,
        yield_strength_mpa=276.0,
        ultimate_strength_mpa=310.0,
        thermal_conductivity=167.0,
        color=ColorRGBA(0.85, 0.87, 0.90, 1.0)
    ),
    "Acier Inoxydable 304": PhysicalMaterial(
        name="Acier Inoxydable 304",
        category="Métaux",
        density_g_cm3=8.00,
        young_modulus_gpa=193.0,
        poisson_ratio=0.29,
        yield_strength_mpa=215.0,
        ultimate_strength_mpa=505.0,
        thermal_conductivity=16.2,
        color=ColorRGBA(0.70, 0.72, 0.75, 1.0)
    ),
    "Acier Carbone C45": PhysicalMaterial(
        name="Acier Carbone C45",
        category="Métaux",
        density_g_cm3=7.85,
        young_modulus_gpa=210.0,
        poisson_ratio=0.30,
        yield_strength_mpa=370.0,
        ultimate_strength_mpa=600.0,
        thermal_conductivity=50.0,
        color=ColorRGBA(0.60, 0.62, 0.65, 1.0)
    ),
    "Titane Grade 5 (Ti-6Al-4V)": PhysicalMaterial(
        name="Titane Grade 5 (Ti-6Al-4V)",
        category="Métaux",
        density_g_cm3=4.43,
        young_modulus_gpa=113.8,
        poisson_ratio=0.34,
        yield_strength_mpa=880.0,
        ultimate_strength_mpa=950.0,
        thermal_conductivity=6.7,
        color=ColorRGBA(0.55, 0.58, 0.62, 1.0)
    ),
    "Laiton CuZn39Pb3": PhysicalMaterial(
        name="Laiton CuZn39Pb3",
        category="Métaux",
        density_g_cm3=8.50,
        young_modulus_gpa=102.0,
        poisson_ratio=0.35,
        yield_strength_mpa=250.0,
        ultimate_strength_mpa=440.0,
        thermal_conductivity=120.0,
        color=ColorRGBA(0.88, 0.75, 0.35, 1.0)
    ),
    "Plastique PLA (Impression 3D)": PhysicalMaterial(
        name="Plastique PLA (Impression 3D)",
        category="Plastiques",
        density_g_cm3=1.24,
        young_modulus_gpa=3.5,
        poisson_ratio=0.36,
        yield_strength_mpa=45.0,
        ultimate_strength_mpa=60.0,
        thermal_conductivity=0.13,
        color=ColorRGBA(0.20, 0.60, 0.90, 1.0)
    ),
    "Plastique ABS": PhysicalMaterial(
        name="Plastique ABS",
        category="Plastiques",
        density_g_cm3=1.04,
        young_modulus_gpa=2.3,
        poisson_ratio=0.35,
        yield_strength_mpa=40.0,
        ultimate_strength_mpa=45.0,
        thermal_conductivity=0.17,
        color=ColorRGBA(0.92, 0.40, 0.20, 1.0)
    ),
    "Fibre de Carbone (Composite)": PhysicalMaterial(
        name="Fibre de Carbone (Composite)",
        category="Composites",
        density_g_cm3=1.60,
        young_modulus_gpa=140.0,
        poisson_ratio=0.28,
        yield_strength_mpa=600.0,
        ultimate_strength_mpa=850.0,
        thermal_conductivity=5.0,
        color=ColorRGBA(0.20, 0.22, 0.25, 1.0)
    )
}


class MaterialCalculator:
    """Calculateur des propriétés physiques (Masse, Poids, Centre de gravité)."""

    @staticmethod
    def calculate_mass_grams(volume_mm3: float, material: PhysicalMaterial) -> float:
        """
        Calcule la masse exacte en grammes à partir du volume en mm³.
        1 cm³ = 1000 mm³. Masse (g) = (Volume mm³ / 1000) * densité (g/cm³).
        """
        volume_cm3 = max(0.0, volume_mm3) / 1000.0
        return float(volume_cm3 * material.density_g_cm3)

    @staticmethod
    def calculate_mass_kg(volume_mm3: float, material: PhysicalMaterial) -> float:
        """Calcule la masse en kilogrammes."""
        return MaterialCalculator.calculate_mass_grams(volume_mm3, material) / 1000.0

    @staticmethod
    def calculate_center_of_mass(solid: Solid) -> Vector3D:
        """
        Calcule le centre de gravité volumique approximatif à partir de la géométrie.
        Pour un solide régulier, se base sur le centre de la boîte englobante ou des sommets.
        """
        if solid.is_empty():
            return Vector3D(0.0, 0.0, 0.0)

        buf = solid.to_mesh_buffer()
        if buf.is_empty():
            b_min, b_max = solid.bounding_box()
            return Vector3D(
                (b_min.x + b_max.x) * 0.5,
                (b_min.y + b_max.y) * 0.5,
                (b_min.z + b_max.z) * 0.5
            )

        mean_xyz = np.mean(buf.vertices, axis=0)
        return Vector3D(float(mean_xyz[0]), float(mean_xyz[1]), float(mean_xyz[2]))
