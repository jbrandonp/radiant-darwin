"""
Modèle de matériaux physiques réalistes (PBR - Physically Based Rendering).
Définit les paramètres de réflectance optique (Albédo, Rugosité, Métallicité, Spécularité et IOR)
style Autodesk Fusion 360 / Blender Principled BSDF.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple
from src.core.types import ColorRGBA


@dataclass
class PBRMaterial:
    """
    Propriétés optiques et physiques d'un matériau réaliste.
    - albedo : Couleur de diffusion de base (RGB [0.0 - 1.0])
    - roughness : Rugosité de surface [0.0 = poli miroir, 1.0 = totalement mat]
    - metallic : Caractère métallique [0.0 = diélectrique/plastique, 1.0 = métal pur conducteur]
    - specular : Réflectivité spéculaire à incidence normale [0.0 - 1.0]
    - ior : Indice de réfraction (Index of Refraction, ex : 1.5 pour le verre/plastique)
    """
    name: str
    albedo: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    roughness: float = 0.3
    metallic: float = 0.0
    specular: float = 0.5
    ior: float = 1.5

    def get_fresnel_f0(self) -> Tuple[float, float, float]:
        """
        Calcule la réflectance de base à incidence normale F0 selon Schlick.
        Pour un métal, F0 est teinté par l'albédo. Pour un isolant, F0 ≈ ((ior - 1)/(ior + 1))^2.
        """
        dielectric_f0 = ((self.ior - 1.0) / (self.ior + 1.0)) ** 2.0
        r_f0 = (1.0 - self.metallic) * dielectric_f0 + self.metallic * self.albedo[0]
        g_f0 = (1.0 - self.metallic) * dielectric_f0 + self.metallic * self.albedo[1]
        b_f0 = (1.0 - self.metallic) * dielectric_f0 + self.metallic * self.albedo[2]
        return (r_f0, g_f0, b_f0)


# Bibliothèque de matériaux de studio réalistes
PBR_LIBRARY: Dict[str, PBRMaterial] = {
    "Aluminium Brossé": PBRMaterial(
        name="Aluminium Brossé",
        albedo=(0.91, 0.92, 0.92),
        roughness=0.35,
        metallic=0.92,
        specular=0.85,
        ior=1.45
    ),
    "Acier Inox Poli": PBRMaterial(
        name="Acier Inox Poli",
        albedo=(0.86, 0.86, 0.88),
        roughness=0.12,
        metallic=0.95,
        specular=0.95,
        ior=2.50
    ),
    "Chrome Miroir": PBRMaterial(
        name="Chrome Miroir",
        albedo=(0.98, 0.98, 0.99),
        roughness=0.03,
        metallic=1.00,
        specular=1.00,
        ior=3.05
    ),
    "Cuivre Rouge": PBRMaterial(
        name="Cuivre Rouge",
        albedo=(0.95, 0.64, 0.54),
        roughness=0.25,
        metallic=0.95,
        specular=0.90,
        ior=1.22
    ),
    "Laiton Doré": PBRMaterial(
        name="Laiton Doré",
        albedo=(0.93, 0.79, 0.43),
        roughness=0.22,
        metallic=0.88,
        specular=0.85,
        ior=1.35
    ),
    "Or 24 Carats": PBRMaterial(
        name="Or 24 Carats",
        albedo=(1.00, 0.86, 0.28),
        roughness=0.10,
        metallic=1.00,
        specular=0.98,
        ior=1.35
    ),
    "Titane Aéronautique": PBRMaterial(
        name="Titane Aéronautique",
        albedo=(0.67, 0.64, 0.61),
        roughness=0.28,
        metallic=0.85,
        specular=0.78,
        ior=2.16
    ),
    "Plastique ABS Noir Brillant": PBRMaterial(
        name="Plastique ABS Noir Brillant",
        albedo=(0.08, 0.08, 0.09),
        roughness=0.15,
        metallic=0.00,
        specular=0.60,
        ior=1.52
    ),
    "Plastique Technique Rouge": PBRMaterial(
        name="Plastique Technique Rouge",
        albedo=(0.88, 0.12, 0.14),
        roughness=0.25,
        metallic=0.00,
        specular=0.55,
        ior=1.50
    ),
    "Fibre de Carbone": PBRMaterial(
        name="Fibre de Carbone",
        albedo=(0.14, 0.14, 0.16),
        roughness=0.38,
        metallic=0.30,
        specular=0.70,
        ior=1.60
    ),
}
