"""
Module des matériaux physiques et calculs de propriétés d'ingénierie.
"""

from src.materials.material_db import PhysicalMaterial, MATERIAL_LIBRARY, MaterialCalculator

__all__ = [
    "PhysicalMaterial",
    "MATERIAL_LIBRARY",
    "MaterialCalculator",
]
