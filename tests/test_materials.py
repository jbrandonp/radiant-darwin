"""
Tests unitaires pour la bibliothèque de matériaux physiques et les calculs de masse.
"""

import pytest
from src.materials.material_db import MATERIAL_LIBRARY, MaterialCalculator, PhysicalMaterial
from src.core.geometry import make_box


def test_material_library_entries() -> None:
    """Vérifie la présence et la validité des constantes physiques des matériaux."""
    assert "Aluminium 6061-T6" in MATERIAL_LIBRARY
    assert "Acier Inoxydable 304" in MATERIAL_LIBRARY
    assert "Titane Grade 5 (Ti-6Al-4V)" in MATERIAL_LIBRARY
    assert "Plastique PLA (Impression 3D)" in MATERIAL_LIBRARY

    alu = MATERIAL_LIBRARY["Aluminium 6061-T6"]
    assert alu.density_g_cm3 == 2.70
    assert alu.density_kg_m3 == 2700.0
    assert alu.young_modulus_gpa > 50.0
    assert alu.yield_strength_mpa > 200.0


def test_mass_and_center_of_mass_calculation() -> None:
    """Vérifie le calcul de masse et du centre de gravité d'un cube."""
    # Cube de 10x10x10 mm = 1000 mm³ = 1 cm³
    cube = make_box(10.0, 10.0, 10.0, center=True)
    alu = MATERIAL_LIBRARY["Aluminium 6061-T6"]

    mass_g = MaterialCalculator.calculate_mass_grams(cube.volume(), alu)
    assert pytest.approx(mass_g, 0.05) == 2.70  # 1 cm³ d'alu = 2.70 g
    assert pytest.approx(MaterialCalculator.calculate_mass_kg(cube.volume(), alu), 1e-4) == 0.0027

    com = MaterialCalculator.calculate_center_of_mass(cube)
    assert pytest.approx(com.x, 0.1) == 0.0
    assert pytest.approx(com.y, 0.1) == 0.0
    assert pytest.approx(com.z, 0.1) == 0.0
