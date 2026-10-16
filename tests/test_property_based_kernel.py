"""
Tests de Propriétés Formelles (Property-Based Testing avec Hypothesis SOTA) du Kernel CAO.
Valide mathématiquement et de manière exhaustive les invariants géométriques fondamentaux :
1. Formule topologique d'Euler-Poincaré : V - E + F = 2 pour les solides 2-manifold (et V - E + F = 2*(S - G)).
2. Invariance par translation et rotation rigide des volumes et centres d'inertie.
3. Semi-définitude positive de l'énergie de déformation élastique FEA (U >= 0).
4. Fuzzing différentiel CSG Manifold3D vs Quadratures géométriques alternatives.
"""

import pytest
import numpy as np
from hypothesis import given, settings, HealthCheck, strategies as st

from src.core.types import Vector3D
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere
from src.core.inspector import compute_center_of_mass, compute_inertia_tensor
from src.core.nexus_kernel.euler_operators import NexusEulerOperators, NexusBRep
from src.core.nexus_kernel.property_strategies import (
    bounded_dimension,
    bounded_translation_vector,
    bounded_rotation_angles,
    bounded_solid_primitive,
    bounded_2manifold_polyhedron,
    bounded_euler_brep_sequence,
    bounded_tet10_case,
    bounded_differential_csg_case,
    PolyhedralTopology,
    Tet10Case,
    DifferentialCSGCase
)
from src.core.nexus_kernel.property_and_differential_bench import (
    DivergenceBoundaryQuadrature,
    GeometricInvariantValidator,
    DifferentialCSGFuzzer
)
from src.core.nexus_kernel.saye_quadrature import SayeImplicitQuadrature


# -------------------------------------------------------------------------
# 1. Tests Hypothesis : Invariant Topologique d'Euler-Poincaré
# -------------------------------------------------------------------------

@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(poly=bounded_2manifold_polyhedron())
def test_prop_euler_poincare_polyhedra(poly: PolyhedralTopology) -> None:
    """
    Vérifie formellement que pour toute topologie polyédrique 2-variété fermée,
    la caractéristique d'Euler satisfait exactement : V - E + F = 2 * (S - G).
    Pour les solides simples sans trou (G=0, S=1), V - E + F = 2.
    """
    valid, chi, expected = GeometricInvariantValidator.verify_euler_poincare(
        num_vertices=poly.num_vertices,
        num_edges=poly.num_edges,
        num_faces=poly.num_faces,
        genus=poly.genus,
        shells=poly.shells
    )
    assert valid, f"Échec Euler-Poincaré pour {poly.name} : chi={chi} != {expected}"
    assert poly.is_euler_valid


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(brep=bounded_euler_brep_sequence())
def test_prop_euler_poincare_atomic_operators(brep: NexusBRep) -> None:
    """
    Vérifie que chaque solide B-Rep construit par une chaîne d'opérateurs
    d'Euler atomiques (MVFS, MEV, MEF) préserve strictement l'invariant d'Euler-Poincaré.
    """
    diag = NexusEulerOperators.verify_euler_poincare(brep, genus=0)
    assert diag.is_valid, f"Violation B-Rep Euler : {diag.diagnostic_message}"
    assert diag.euler_characteristic == 2


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(solid=bounded_solid_primitive())
def test_prop_euler_poincare_triangulated_solid_meshes(solid: Solid) -> None:
    """
    Vérifie que pour tout maillage triangulaire fermé 2-variété issu du moteur géométrique,
    le genre topologique G vérifie V - E + F = 2 * (1 - G).
    """
    mesh = solid.manifold.to_mesh()
    num_v = len(mesh.vert_properties)
    num_f = len(mesh.tri_verts)
    # Dans une variété triangulaire fermée, chaque facette a 3 arêtes et chaque arête est partagée par 2 facettes
    num_e = (3 * num_f) // 2

    g = solid.genus()
    valid, chi, expected = GeometricInvariantValidator.verify_euler_poincare(
        num_vertices=num_v,
        num_edges=num_e,
        num_faces=num_f,
        genus=g,
        shells=1
    )
    assert valid, f"Maillage non conforme à Euler : V={num_v}, E={num_e}, F={num_f}, G={g}, chi={chi} != {expected}"


# -------------------------------------------------------------------------
# 2. Tests Hypothesis : Invariance par Isométries Spatiales Rigides
# -------------------------------------------------------------------------

@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    solid=bounded_solid_primitive(),
    translation=bounded_translation_vector()
)
def test_prop_rigid_translation_invariance(solid: Solid, translation: Vector3D) -> None:
    """
    Vérifie l'invariance volumique et métrologique stricte par translation spatiale :
    - Volume(T(S)) == Volume(S)
    - Surface(T(S)) == Surface(S)
    - CoM(T(S)) == CoM(S) + T
    """
    is_valid, metrics = GeometricInvariantValidator.verify_rigid_translation_invariance(
        solid=solid,
        translation=translation,
        tol_vol_rel=1e-4,
        tol_com_abs=1e-3
    )
    assert is_valid, f"Violation d'invariance par translation : {metrics}"


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    solid=bounded_solid_primitive(),
    angles=bounded_rotation_angles()
)
def test_prop_rigid_rotation_invariance(solid: Solid, angles: tuple[float, float, float]) -> None:
    """
    Vérifie l'invariance par rotation 3D rigide quelconque :
    - Volume(R(S)) == Volume(S)
    - Surface(R(S)) == Surface(S)
    - CoM(R(S)) == R * CoM(S)
    """
    rx, ry, rz = angles
    is_valid, metrics = GeometricInvariantValidator.verify_rigid_rotation_invariance(
        solid=solid,
        rx_deg=rx,
        ry_deg=ry,
        rz_deg=rz,
        tol_vol_rel=1e-4,
        tol_com_abs=1e-3
    )
    assert is_valid, f"Violation d'invariance par rotation : {metrics}"


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    dx=bounded_dimension(min_value=10.0, max_value=60.0),
    dy=bounded_dimension(min_value=10.0, max_value=60.0),
    dz=bounded_dimension(min_value=10.0, max_value=60.0),
    angles=bounded_rotation_angles(),
    translation=bounded_translation_vector()
)
def test_prop_inertia_tensor_principal_moments_invariance(
    dx: float,
    dy: float,
    dz: float,
    angles: tuple[float, float, float],
    translation: Vector3D
) -> None:
    """
    Vérifie que les moments principaux d'inertie (valeurs propres du tenseur d'inertie)
    sont rigoureusement invariants sous translation et rotation rigide.
    """
    box = make_box(dx, dy, dz, center=True)
    inertia_orig = compute_inertia_tensor(box, density_g_cm3=1.0)
    p_orig = np.sort(inertia_orig.principal_moments)

    # 1. Translation seule
    box_trans = box.translate(translation)
    inertia_trans = compute_inertia_tensor(box_trans, density_g_cm3=1.0)
    p_trans = np.sort(inertia_trans.principal_moments)
    np.testing.assert_allclose(p_trans, p_orig, rtol=1e-3, err_msg="Translation a modifié les moments d'inertie principaux")

    # 2. Rotation seule
    rx, ry, rz = angles
    box_rot = box.rotate(rx, ry, rz)
    inertia_rot = compute_inertia_tensor(box_rot, density_g_cm3=1.0)
    p_rot = np.sort(inertia_rot.principal_moments)
    np.testing.assert_allclose(p_rot, p_orig, rtol=1e-3, err_msg="Rotation a modifié les moments d'inertie principaux")


# -------------------------------------------------------------------------
# 3. Tests Hypothesis : Semi-Définitude Positive FEA (U >= 0)
# -------------------------------------------------------------------------

@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=bounded_tet10_case())
def test_prop_fea_strain_energy_positive_semidefinite(case: Tet10Case) -> None:
    """
    Vérifie la semi-définitude positive de l'énergie de déformation élastique :
    1. U = 0.5 * u^T * K * u >= 0 pour tout champ de déplacement admissible u.
    2. Symétrie absolue de la matrice de rigidité élémentaire Ke.
    3. Non-négativité de toutes les valeurs propres de Ke (lambda_min >= -tol).
    """
    ke = case.element.calculate_stiffness_matrix(case.node_coords, case.material)
    u = case.displacement_vector

    is_valid, strain_energy, min_eig, sym_error = GeometricInvariantValidator.verify_fea_strain_energy_psd(
        stiffness_matrix=ke,
        displacement_vector=u,
        tol_energy_psd=-1e-8,
        tol_eig_psd=-1e-8
    )

    assert is_valid, (
        f"Violation physique FEA : U={strain_energy:.4e}, min_eig={min_eig:.4e}, "
        f"sym_error={sym_error:.4e}"
    )
    assert strain_energy >= -1e-8, f"Énergie de déformation élastique négative : {strain_energy}"
    assert min_eig >= -1e-8, f"Valeur propre de rigidité négative : {min_eig}"
    assert sym_error <= 1e-9, f"Matrice de rigidité non symétrique : {sym_error}"


# -------------------------------------------------------------------------
# 4. Tests Hypothesis : Fuzzing Différentiel CSG vs Quadrature Alternative
# -------------------------------------------------------------------------

@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(csg_case=bounded_differential_csg_case())
def test_prop_differential_fuzzing_csg_vs_quadrature(csg_case: DifferentialCSGCase) -> None:
    """
    Fuzzing différentiel comparant Manifold3D avec la quadrature de la divergence
    et validant les propriétés ensemblistes (Inclusion-Exclusion, Monotonicité).
    """
    report = DifferentialCSGFuzzer.evaluate_csg_differential(
        solid_a=csg_case.solid_a,
        solid_b=csg_case.solid_b,
        operation=csg_case.operation,
        tol_rel=1e-4
    )

    assert report.is_passed, f"Échec du fuzzing différentiel CSG : {report.diagnostic}"
    assert report.discrepancy_rel <= 1e-4
    assert report.inclusion_exclusion_error <= 0.05
    assert report.is_watertight or report.vol_manifold3d == 0.0


def test_prop_saye_implicit_quadrature_differential_comparison() -> None:
    """
    Compare directement l'intégration de volume d'une sphère entre Manifold3D
    et la quadrature numérique cartésienne de Saye sur cellules coupées.
    """
    radius = 12.0
    solid_sphere = make_sphere(radius)
    vol_manifold = solid_sphere.volume()

    # Fonction implicite phi(x, y, z) = sqrt(x^2 + y^2 + z^2) - R <= 0
    def sphere_sdf(x: float, y: float, z: float) -> float:
        return float(np.sqrt(x * x + y * y + z * z) - radius)

    # Intégration de Saye sur une grille de cellules coupées
    box_min = [-radius * 1.1, -radius * 1.1, -radius * 1.1]
    box_max = [radius * 1.1, radius * 1.1, radius * 1.1]
    vol_saye = SayeImplicitQuadrature.integrate_domain(sphere_sdf, box_min, box_max, subdivisions=4)

    # Volume théorique exact = 4/3 * pi * R^3
    vol_exact = (4.0 / 3.0) * np.pi * (radius ** 3)

    # Vérification que Manifold3D et la quadrature approchent le volume exact à moins de 3%
    assert abs(vol_manifold - vol_exact) / vol_exact < 0.03
    assert abs(vol_saye - vol_exact) / vol_exact < 0.03
