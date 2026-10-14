"""
Tests Unitaires et d'Intégration des 6 Piliers d'Élite Industriels (Résolution des 6 Angles Morts).
Couvre :
1. Quadrature de Saye sur cellules coupées pour CutFEM (réduction dimensionnelle 3D -> 2D -> 1D).
2. Surfaces développables (K=0) et opérateur d'angle de dépouille (Isoclinic Draft Engine).
3. Arithmétique d'intervalles et élagage d'arbre CSG/SDF par tuile (Architecture type Fidget).
4. Dynamique des chaînes cinématiques fermées via matrice d'inertie opérationnelle inverse Lambda^-1.
5. Arête 3D maîtresse et tessellation frontière coordonnée pour Trimmed NURBS étanches.
6. Intégrateur symplectique alpha-généralisé de Chung-Hulbert et formulation anti-verrouillage B-bar.
"""

import pytest
import numpy as np

from src.core.nexus_kernel import (
    SayeImplicitQuadrature, SayeQuadratureRule,
    RuledDevelopableSurface, IsoclinicDraftEngine, DraftDiagnostic,
    CSGOpType, SDFInterval, SDFIntervalTreeNode,
    ClosedLoopKinematicEngine, ClosedLoopDynamicsResult,
    WatertightTrimmedEdge, CoordinatedMeshSealer, WatertightEdgeReport,
    GeneralizedAlphaIntegrator, GeneralizedAlphaStepResult, VolumetricLockingMitigation
)


# =====================================================================
# 1. QUADRATURE NUMÉRIQUE DE SAYE SUR CELLULES COUPÉES (CUTFEM)
# =====================================================================

def test_saye_quadrature_full_and_cut_cells() -> None:
    """Vérifie la quadrature exacte de Saye sur cellules pleines et cellules coupées."""
    # Sphère de rayon R = 1.0 centrée en (0, 0, 0)
    def phi_sphere(x: float, y: float, z: float) -> float:
        return float(np.sqrt(x ** 2 + y ** 2 + z ** 2) - 1.0)

    # Voxel intérieur plein : [-0.3, 0.3]^3 -> distance au centre au plus 0.3*sqrt(3) ~= 0.519 < 1.0
    rule_full = SayeImplicitQuadrature.compute_cut_voxel_quadrature(
        phi_sphere, box_min=[-0.3, -0.3, -0.3], box_max=[0.3, 0.3, 0.3]
    )
    assert not rule_full.is_cut_cell
    assert rule_full.fractional_volume == pytest.approx(0.6 ** 3, rel=1e-5)

    # Voxel extérieur : [2.0, 3.0]^3 -> phi > 0 partout
    rule_empty = SayeImplicitQuadrature.compute_cut_voxel_quadrature(
        phi_sphere, box_min=[2.0, 2.0, 2.0], box_max=[3.0, 3.0, 3.0]
    )
    assert not rule_empty.is_cut_cell
    assert rule_empty.fractional_volume == 0.0

    # Voxel coupé par l'hémisphère supérieur : [0.0, 0.5] x [0.0, 0.5] x [0.5, 1.2]
    rule_cut = SayeImplicitQuadrature.compute_cut_voxel_quadrature(
        phi_sphere, box_min=[0.0, 0.0, 0.5], box_max=[0.5, 0.5, 1.2]
    )
    assert rule_cut.is_cut_cell
    assert rule_cut.fractional_volume > 0.0
    assert rule_cut.fractional_volume < (0.5 * 0.5 * 0.7)  # Volume partiel strictement inférieur au voxel entier
    assert len(rule_cut.points) > 0
    assert len(rule_cut.weights) == len(rule_cut.points)

    # Intégration de la fonction constante f = 1.0
    vol_integrated = SayeImplicitQuadrature.integrate_scalar(lambda x, y, z: 1.0, rule_cut)
    assert vol_integrated == pytest.approx(rule_cut.fractional_volume, rel=1e-5)


# =====================================================================
# 2. SURFACES DÉVELOPPABLES (K=0) ET DÉPOUILLE INDUSTRIELLE
# =====================================================================

def test_developable_surface_curvature_and_unrolling() -> None:
    """Vérifie la condition d'isométrie K=0 d'un cylindre réglé et son dépliage dans le plan."""
    radius = 20.0

    # Cylindre circulaire : c(u) = (R cos u, R sin u, 0), d(u) = (0, 0, 1)
    directrix = lambda u: np.array([radius * np.cos(u), radius * np.sin(u), 0.0])
    directrix_tangent = lambda u: np.array([-radius * np.sin(u), radius * np.cos(u), 0.0])
    ruling = lambda u: np.array([0.0, 0.0, 40.0])
    ruling_derivative = lambda u: np.array([0.0, 0.0, 0.0])

    surf = RuledDevelopableSurface(
        directrix, directrix_tangent, ruling, ruling_derivative,
        u_range=(0.0, float(np.pi * 0.5)), v_range=(0.0, 1.0)
    )

    # Vérification K = 0 (Déterminant nul)
    assert surf.is_developable(tolerance=1e-7)

    # Dépliage isométrique 2D
    pts_2d, triangles = surf.unroll_to_plane_2d(num_u=15, num_v=5)
    assert len(pts_2d) > 0
    assert len(triangles) > 0
    # La largeur développée doit être exactement l'arc de quart de cercle : R * pi / 2
    max_x = np.max(pts_2d[:, 0])
    expected_width = radius * (np.pi * 0.5)
    assert max_x == pytest.approx(expected_width, rel=1e-3)


def test_isoclinic_draft_angle_analysis_and_transform() -> None:
    """Vérifie l'identification des contre-dépouilles et la transformation géométrique de dépouille."""
    # Ensemble de normales contenant des faces verticales (angle = 0 deg)
    normals = np.array([
        [1.0, 0.0, 0.0],   # Verticale (0 deg de dépouille par rapport à +Z)
        [0.0, 1.0, 0.0],   # Verticale
        [0.0, 0.0, 1.0],   # Horizontale supérieure (90 deg)
        [0.05, 0.0, 0.99]  # Légèrement inclinée
    ], dtype=np.float64)

    diag = IsoclinicDraftEngine.analyze_mesh_draft(
        face_normals=normals, pull_direction=[0.0, 0.0, 1.0], target_draft_angle_deg=2.0
    )
    assert not diag.is_demoldable
    assert diag.undercut_faces_count == 2  # Les 2 faces verticales n'atteignent pas les 2 degrés requis

    # Application de la déformation d'angle de dépouille de 3 degrés
    box_vertices = np.array([
        [-10.0, -10.0, 0.0],
        [10.0, -10.0, 0.0],
        [10.0, 10.0, 0.0],
        [-10.0, 10.0, 0.0],
        [-10.0, -10.0, 50.0],
        [10.0, -10.0, 50.0],
        [10.0, 10.0, 50.0],
        [-10.0, 10.0, 50.0],
    ], dtype=np.float64)

    drafted_verts = IsoclinicDraftEngine.apply_draft_transformation(
        box_vertices, draft_angle_deg=3.0, neutral_plane_z=0.0
    )
    # Les sommets du haut (z=50) doivent s'être évasés vers l'extérieur
    assert drafted_verts[4, 0] < box_vertices[4, 0]
    assert drafted_verts[5, 0] > box_vertices[5, 0]


# =====================================================================
# 3. ÉLAGAGE D'ARBRES CSG / SDF PAR INTERVALLES (FIDGET)
# =====================================================================

def test_fidget_interval_arithmetic_and_tree_pruning() -> None:
    """Vérifie l'élagage spatial par arithmétique d'intervalles éliminant la divergence de warp GPU."""
    # Création d'une Union de deux sphères :
    # Sphère 1 au centre (0, 0, 0) de rayon 10
    # Sphère 2 très loin à (100, 100, 100) de rayon 5
    sp1 = SDFIntervalTreeNode(CSGOpType.SPHERE, params=(10.0, 0.0, 0.0, 0.0))
    sp2 = SDFIntervalTreeNode(CSGOpType.SPHERE, params=(5.0, 100.0, 100.0, 100.0))
    union_tree = SDFIntervalTreeNode(CSGOpType.UNION, left=sp1, right=sp2)

    assert union_tree.count_nodes() == 3

    # Tuile spatiale locale centrée sur la sphère 1 : [-8, 8]^3
    tile_x = SDFInterval(-8.0, 8.0)
    tile_y = SDFInterval(-8.0, 8.0)
    tile_z = SDFInterval(-8.0, 8.0)

    # Élagage de l'arbre pour cette tuile
    pruned_tree = union_tree.prune_for_tile(tile_x, tile_y, tile_z)

    # Dans cette tuile, la sphère 2 est à distance > 100, tandis que la sphère 1 est proche de zéro.
    # L'union min(S1, S2) doit avoir totalement élagué S2 !
    assert pruned_tree.count_nodes() == 1
    assert pruned_tree.op == CSGOpType.SPHERE
    assert pruned_tree.params[0] == 10.0  # Reste uniquement la sphère 1 !


# =====================================================================
# 4. CINÉMATIQUE ET DYNAMIQUE DES BOUCLES FERMÉES (LAMBDA^-1)
# =====================================================================

def test_closed_loop_kinematics_operational_space() -> None:
    """Vérifie la résolution dynamique d'une chaîne cinématique à boucle fermée via Lambda^-1."""
    # Système à 2 DDL avec matrice de masse diagonale
    M = np.array([[2.0, 0.0], [0.0, 3.0]], dtype=np.float64)
    tau = np.array([10.0, 15.0], dtype=np.float64)

    # Contrainte scalaire de fermeture de boucle reliant q1 et q2 : q1 - q2 = 0
    J_c = np.array([[1.0, -1.0]], dtype=np.float64)  # Shape (1, 2)
    c_drift = np.array([0.02], dtype=np.float64)     # Dérive initiale de 20 mm
    v_joints = np.array([0.5, 0.5], dtype=np.float64)

    # 1. Matrice d'inertie opérationnelle inverse : Lambda^-1 = J_c * M^-1 * J_c^T
    # M^-1 = diag(1/2, 1/3) -> J_c * M^-1 * J_c^T = 1*(1/2)*1 + (-1)*(1/3)*(-1) = 0.5 + 0.3333 = 0.8333
    lambda_inv = ClosedLoopKinematicEngine.compute_operational_inverse_inertia(M, J_c)
    assert lambda_inv[0, 0] == pytest.approx(5.0 / 6.0, rel=1e-5)

    # 2. Résolution complète avec correction d'accélération
    res = ClosedLoopKinematicEngine.solve_closed_loop_acceleration(
        mass_matrix=M,
        unconstrained_torques=tau,
        constraint_jacobian=J_c,
        constraint_drift=c_drift,
        joint_velocities=v_joints,
        stabilization_kp=500.0,
        stabilization_kd=20.0
    )
    assert res.is_converged
    assert len(res.joint_accelerations) == 2
    assert len(res.constraint_forces) == 1

    # L'accélération de contrainte J_c * q_ddot doit contrebalancer la dérive
    a_constraint = float((J_c @ res.joint_accelerations)[0])
    assert a_constraint < 0.0  # Force corrective ramenant la dérive positive vers 0


# =====================================================================
# 5. ARÊTE 3D MAÎTRESSE ET TOPOLOGIE ÉTANCHE (WATERTIGHT TRIMMED BREP)
# =====================================================================

def test_watertight_trimmed_brep_master_edge() -> None:
    """Vérifie l'éradication des fissures de tessellation via la courbe 3D maîtresse partagée."""
    # Courbe 3D maîtresse le long d'une hélice ou segment 3D
    master_curve = lambda t: np.array([10.0 * float(t), 20.0 * float(t), 5.0 * np.sin(float(t))])
    wt_edge = WatertightTrimmedEdge("E_master_1", master_curve, tolerance_radius=1e-3)

    # Évaluation paramétrique des deux faces adjacentes
    surf1_eval = lambda u, v: np.array([float(u), float(v), 5.0 * np.sin(float(u) / 10.0)])
    surf2_eval = lambda u, v: np.array([float(u), float(v), 5.0 * np.sin(float(u) / 10.0)])

    # Projection inverse triviale
    surf1_proj = lambda pt: (float(pt[0]), float(pt[1]))
    surf2_proj = lambda pt: (float(pt[0]), float(pt[1]))

    coord_verts, report = wt_edge.generate_coordinated_tessellation(
        surf1_eval, surf2_eval, surf1_proj, surf2_proj, num_samples=10
    )

    assert report.is_watertight
    assert report.shared_samples_count == 10
    assert report.max_boundary_gap < 1e-4

    # Scellement de maillages
    f1_v = np.array([[0.0, 0.0, 0.0], [5.0, 10.0, 2.0]], dtype=np.float64)
    f2_v = np.array([[0.001, 0.001, 0.0], [5.002, 9.998, 2.0]], dtype=np.float64)
    tris = np.array([[0, 1, 0]], dtype=np.int32)

    s_f1_v, _, s_f2_v, _ = CoordinatedMeshSealer.stitch_shared_boundary(
        tris, f1_v, tris, f2_v, coord_verts[:2]
    )
    # Les coordonnées sur les deux maillages doivent être exactement identiques
    np.testing.assert_allclose(s_f1_v[0], s_f2_v[0], atol=1e-12)


# =====================================================================
# 6. INTÉGRATEUR SYMPLECTIQUE ALPHA-GÉNÉRALISÉ ET FORMULATION B-BAR
# =====================================================================

def test_symplectic_generalized_alpha_energy_conservation() -> None:
    """Vérifie la conservation de l'énergie mécanique sur un oscillateur harmonique non amorti."""
    # Système oscillant non amorti : M = [[1]], K = [[100]] -> pulsation w = 10 rad/s
    M = np.array([[1.0]], dtype=np.float64)
    K = np.array([[100.0]], dtype=np.float64)

    # Intégrateur avec rho_infinity = 1.0 (strictement sans dissipation numérique)
    integrator = GeneralizedAlphaIntegrator(M, K, rho_infinity=1.0)

    d_n = np.array([1.0], dtype=np.float64)  # Déplacement initial = 1.0 m
    v_n = np.array([0.0], dtype=np.float64)  # Vitesse initiale nulle
    a_n = np.array([-100.0], dtype=np.float64)

    initial_energy = 0.5 * 100.0 * (1.0 ** 2)  # E = 50 Joules

    dt = 0.002
    for _ in range(50):
        res = integrator.advance_step(
            d_n=d_n, v_n=v_n, a_n=a_n,
            f_ext_next=np.array([0.0]), f_ext_curr=np.array([0.0]),
            dt=dt
        )
        d_n, v_n, a_n = res.displacements, res.velocities, res.accelerations

    # L'énergie mécanique totale finale doit être conservée
    assert res.energy_total == pytest.approx(initial_energy, rel=1e-2)


def test_volumetric_locking_mitigation_bbar() -> None:
    """Vérifie la stabilité de la matrice de rigidité B-bar pour un élastomère quasi-incompressible (nu = 0.499)."""
    # Élastomère quasi-incompressible nu = 0.499
    young = 10.0  # MPa
    nu_incompressible = 0.499

    k_elem = VolumetricLockingMitigation.compute_bbar_stiffness(
        young_modulus=young, poisson_ratio=nu_incompressible, element_volume=1.0
    )

    # La matrice doit être symétrique et définie positive sans singularité flottante
    assert np.allclose(k_elem, k_elem.T)
    eigenvals = np.linalg.eigvalsh(k_elem)
    assert (eigenvals > 0.0).all()
    # Le conditionnement doit rester modéré (pas d'explosion à 10^16)
    cond = np.linalg.cond(k_elem)
    assert cond < 1e5
