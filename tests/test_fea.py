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


def test_nonlinear_fem_sparse_assembly_and_solve() -> None:
    """Valide l'assemblage et la résolution du système de rigidité Tet10 par matrice creuse SuperLU."""
    import numpy as np
    from src.fea.nonlinear_fem import Tet10Element, BilinearPlasticMaterial, NonlinearFEASolver

    # Création d'un tétraèdre Tet10 (10 nœuds)
    coords = np.array([
        [0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0], [5.0, 5.0, 0.0], [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0], [5.0, 0.0, 5.0], [0.0, 5.0, 5.0]
    ], dtype=np.float64)

    elem = Tet10Element(element_id=1, node_indices=list(range(10)))
    mat = BilinearPlasticMaterial(youngs_modulus_mpa=210000.0, poissons_ratio=0.3)

    # 1. Assemblage sparse
    k_csr = NonlinearFEASolver.assemble_global_sparse_stiffness([elem], coords, mat)
    assert k_csr.shape == (30, 30)
    assert k_csr.nnz > 0

    # 2. Résolution avec encastrement des 3 premiers sommets (DOFs 0 à 8) et force sur le sommet 3
    fixed_dofs = list(range(9))
    force = np.zeros(30, dtype=np.float64)
    force[3 * 3 + 2] = -500.0  # Force de 500 N selon -Z sur le nœud 3

    disp = NonlinearFEASolver.solve_sparse_system(k_csr, force, fixed_dofs)
    assert disp.shape == (30,)
    # Les DOFs fixés doivent rester nuls
    assert np.allclose(disp[fixed_dofs], 0.0)
    # Le déplacement selon Z au point d'application doit être négatif
    assert disp[3 * 3 + 2] < 0.0

