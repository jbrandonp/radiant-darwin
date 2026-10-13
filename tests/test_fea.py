"""
Tests unitaires pour la simulation par éléments finis (FEA).
"""

import pytest
from src.core.geometry import make_box
from src.materials.material_db import MATERIAL_LIBRARY
from src.fea.fea_solver import FEASimulator


def test_fea_static_analysis() -> None:
    """Vérifie le calcul des contraintes de von Mises et du facteur de sécurité."""
    # Barreau rectangulaire de 15x15x60 mm en acier
    mat = MATERIAL_LIBRARY["Acier Carbone C45"]
    sim = FEASimulator(mat)
    bar = make_box(15.0, 15.0, 60.0)

    res = sim.run_static_analysis(bar, applied_force_newtons=1000.0)
    assert res is not None
    assert res.max_stress_mpa > 0.0
    assert res.max_displacement_mm > 0.0
    assert res.safety_factor > 0.0
    assert len(res.nodal_stresses) == len(bar.to_mesh_buffer().vertices)

    # Vérification de la génération du maillage déformé cartographique
    heat_mesh = sim.generate_stress_heatmap_mesh(bar, res)
    assert not heat_mesh.is_empty()
    assert len(heat_mesh.vertices) == len(bar.to_mesh_buffer().vertices)
