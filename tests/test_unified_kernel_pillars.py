"""
Tests unitaires formels des piliers technologiques de rupture du noyau unifié NEXUS-3D.
Couvre :
1. Prédicats géométriques exacts de Shewchuk (orient2d, orient3d, incircle).
2. Quaternions duaux SE(3) et pipeline multi-échelle Relative-To-Eye.
3. Arène mémoire générationnelle SlotMap O(1).
4. Graphe de calcul incrémental adressé par le contenu (DAG Salsa/BLAKE3).
5. Barrière logarithmique IPC et méthode de l'état adjoint pour l'optimisation inverse.
"""

import pytest
import numpy as np

from src.core.nexus_kernel import (
    RobustGeometricPredicates, Orientation,
    Quaternion, DualQuaternion, RelativeToEyePipeline,
    ArenaKey, GenerationalArena,
    DAGNode, IncrementalExecutionDAG, ExecutionStats,
    IncrementalPotentialContact, IPCBarrierResult,
    AdjointSensitivityEngine, AdjointSensitivityResult,
    CutFEMStabilizer, SmallDisplacementTorsor
)


# =====================================================================
# 1. PRÉDICATS GÉOMÉTRIQUES EXACTS DE SHEWCHUK
# =====================================================================

def test_orient2d_exact() -> None:
    """Vérifie l'orientation 2D sans erreur d'arrondi flottant."""
    a = (0.0, 0.0)
    b = (10.0, 0.0)

    # Point au-dessus (gauche)
    assert RobustGeometricPredicates.orient2d(a, b, (5.0, 2.0)) == 1
    # Point en-dessous (droite)
    assert RobustGeometricPredicates.orient2d(a, b, (5.0, -2.0)) == -1
    # Point strictement colinéaire
    assert RobustGeometricPredicates.orient2d(a, b, (5.0, 0.0)) == 0


def test_orient3d_exact() -> None:
    """Vérifie l'orientation 3D par rapport au plan orienté (XY)."""
    p1 = (0.0, 0.0, 0.0)
    p2 = (10.0, 0.0, 0.0)
    p3 = (0.0, 10.0, 0.0)

    # Selon la convention de Shewchuk pour un repère orienté CCW (normale +Z) :
    # Point au-dessus du plan XY (z > 0) -> -1
    assert RobustGeometricPredicates.orient3d(p1, p2, p3, (5.0, 5.0, 1.0)) == -1
    # Point en-dessous du plan XY (z < 0) -> +1
    assert RobustGeometricPredicates.orient3d(p1, p2, p3, (5.0, 5.0, -1.0)) == 1
    # Point strictement coplanaire -> 0
    assert RobustGeometricPredicates.orient3d(p1, p2, p3, (5.0, 5.0, 0.0)) == 0
    assert RobustGeometricPredicates.exact_coplanar(p1, p2, p3, (7.0, 3.0, 0.0))


def test_incircle_exact() -> None:
    """Vérifie le test d'appartenance au cercle circonscrit."""
    # Triangle rectangle inscrit dans le cercle de centre (5, 5) et rayon 5*sqrt(2)
    a = (0.0, 0.0)
    b = (10.0, 0.0)
    c = (0.0, 10.0)

    # Point au centre du cercle (intérieur)
    assert RobustGeometricPredicates.incircle(a, b, c, (2.0, 2.0)) == 1
    # Point très loin (extérieur)
    assert RobustGeometricPredicates.incircle(a, b, c, (50.0, 50.0)) == -1


def test_segment_intersection_and_point_in_triangle() -> None:
    """Vérifie l'intersection robuste de segments et point-in-triangle."""
    t_a = (0.0, 0.0)
    t_b = (10.0, 0.0)
    t_c = (5.0, 10.0)

    assert RobustGeometricPredicates.point_in_triangle_2d((5.0, 3.0), t_a, t_b, t_c)
    assert not RobustGeometricPredicates.point_in_triangle_2d((15.0, 3.0), t_a, t_b, t_c)

    # Intersection de deux segments croisés en croix
    s1_a, s1_b = (0.0, 5.0), (10.0, 5.0)
    s2_a, s2_b = (5.0, 0.0), (5.0, 10.0)
    assert RobustGeometricPredicates.segments_intersect_2d(s1_a, s1_b, s2_a, s2_b)


# =====================================================================
# 2. QUATERNIONS DUAUX ET PIPELINE MULTI-ÉCHELLE
# =====================================================================

def test_dual_quaternion_rigid_transformation() -> None:
    """Vérifie la transformation spatiale SE(3) pure par quaternions duaux."""
    # Rotation de 90 degrés autour de Z + Translation de (10, 20, 30)
    dq = DualQuaternion.from_axis_angle_translation(
        axis=[0.0, 0.0, 1.0],
        angle_rad=float(np.pi * 0.5),
        translation=[10.0, 20.0, 30.0]
    )

    pt_orig = np.array([5.0, 0.0, 0.0], dtype=np.float64)
    pt_trans = dq.transform_point(pt_orig)

    # Après rotation 90 deg autour de Z : (0, 5, 0) + (10, 20, 30) = (10, 25, 30)
    np.testing.assert_allclose(pt_trans, [10.0, 25.0, 30.0], atol=1e-6)

    # Vérification extraction de translation
    np.testing.assert_allclose(dq.extract_translation(), [10.0, 20.0, 30.0], atol=1e-6)


def test_dual_quaternion_dlb_interpolation() -> None:
    """Vérifie l'interpolation cinématique fluide DLB entre deux poses 3D."""
    dq1 = DualQuaternion.from_axis_angle_translation([0.0, 0.0, 1.0], 0.0, [0.0, 0.0, 0.0])
    dq2 = DualQuaternion.from_axis_angle_translation([0.0, 0.0, 1.0], 0.0, [100.0, 40.0, 0.0])

    mid_dq = DualQuaternion.dlb_interpolate(dq1, dq2, weight=0.5)
    mid_trans = mid_dq.extract_translation()

    # À mi-parcours, translation = (50, 20, 0)
    np.testing.assert_allclose(mid_trans, [50.0, 20.0, 0.0], atol=1e-5)


def test_relative_to_eye_pipeline() -> None:
    """Vérifie la soustraction f64 de la caméra avant projection f32."""
    world_coords = np.array([
        [50000.001, 20000.002, 1000.003],
        [50000.005, 20000.006, 1000.007]
    ], dtype=np.float64)

    cam_pos = [50000.0, 20000.0, 1000.0]
    rte_coords = RelativeToEyePipeline.compute_camera_relative_vertices(world_coords, cam_pos)

    assert rte_coords.dtype == np.float32
    # Précision sub-millimétrique conservée sans dérive
    np.testing.assert_allclose(rte_coords[0], [0.001, 0.002, 0.003], atol=1e-5)


# =====================================================================
# 3. ARÈNE MÉMOIRE GÉNÉRATIONNELLE (SLOTMAP)
# =====================================================================

def test_generational_arena_insert_get_remove() -> None:
    """Vérifie l'allocation O(1) et la détection instantanée de clés périmées."""
    arena: GenerationalArena[str] = GenerationalArena[str](initial_capacity=16)

    key1 = arena.insert("Vertex_A")
    key2 = arena.insert("Vertex_B")

    assert arena.get(key1) == "Vertex_A"
    assert arena.get(key2) == "Vertex_B"
    assert len(arena) == 2

    # Suppression de key1
    removed = arena.remove(key1)
    assert removed == "Vertex_A"
    assert len(arena) == 1

    # Accès avec l'ancienne clé : doit retourner None (clé périmée !)
    assert arena.get(key1) is None
    assert not arena.contains(key1)

    # Réinsertion : réutilise le slot avec une génération incrémentée
    key3 = arena.insert("Vertex_C")
    assert key3.index == key1.index
    assert key3.generation > key1.generation
    assert arena.get(key3) == "Vertex_C"
    # L'ancienne clé reste invalide
    assert arena.get(key1) is None


# =====================================================================
# 4. GRAPHE D'EXÉCUTION INCRÉMENTAL ADRESSÉ PAR CONTENU (DAG)
# =====================================================================

def test_incremental_dag_cache_memoization() -> None:
    """Vérifie qu'un nœud non modifié n'est jamais recalculé (100% cache hit)."""
    dag: IncrementalExecutionDAG[float] = IncrementalExecutionDAG[float]()

    # Opérateur d'addition
    def eval_sum(node: DAGNode, inputs: list[float]) -> float:
        base_val = float(node.params.get("val", 0.0))
        return base_val + sum(inputs)

    dag.register_operator("sum", eval_sum)

    # Nœud A -> Nœud B -> Nœud C
    dag.add_or_update_node("A", "sum", {"val": 10.0})
    dag.add_or_update_node("B", "sum", {"val": 20.0}, dependencies=["A"])
    dag.add_or_update_node("C", "sum", {"val": 5.0}, dependencies=["B"])

    # Première passe : tout doit être exécuté
    stats1 = dag.evaluate_incremental()
    assert stats1.total_nodes == 3
    assert stats1.executed_nodes_count == 3
    assert stats1.cached_nodes_count == 0
    assert dag.get_result("C") == 35.0

    # Deuxième passe sans modification : 100% en cache !
    stats2 = dag.evaluate_incremental()
    assert stats2.executed_nodes_count == 0
    assert stats2.cached_nodes_count == 3
    assert stats2.cache_hit_rate_percent == 100.0

    # Modification d'un nœud indépendant D
    dag.add_or_update_node("D", "sum", {"val": 50.0})
    stats3 = dag.evaluate_incremental()
    # Seul D doit s'exécuter, A, B, C restent en cache
    assert stats3.executed_nodes_count == 1
    assert stats3.cached_nodes_count == 3
    assert dag.get_result("D") == 50.0


# =====================================================================
# 5. BARRIÈRE IPC ET PHYSIQUE ADJOINTE
# =====================================================================

def test_ipc_logarithmic_barrier() -> None:
    """Vérifie le potentiel barrière IPC C2-continu et la force répulsive."""
    # Distance supérieure à d_hat (inactive)
    res_inactive = IncrementalPotentialContact.evaluate_barrier(distance=2.0, d_hat=1.0)
    assert not res_inactive.is_active
    assert res_inactive.barrier_energy == 0.0
    assert res_inactive.repulsive_force == 0.0

    # Distance inférieure à d_hat (active, répulsion positive)
    res_active = IncrementalPotentialContact.evaluate_barrier(distance=0.2, d_hat=1.0, kappa=1e4)
    assert res_active.is_active
    assert res_active.barrier_energy > 0.0
    assert res_active.repulsive_force > 0.0
    assert res_active.barrier_stiffness > 0.0


def test_adjoint_state_sensitivity() -> None:
    """Vérifie le calcul analytique du gradient adjoint en O(1)."""
    # Système linéaire 2x2 : K(theta) * u = f
    # K = [[theta, 0], [0, 2*theta]]
    # f = [10, 20] -> u = [10/theta, 10/theta]
    theta = 5.0
    k_mat = np.array([[theta, 0.0], [0.0, 2.0 * theta]], dtype=np.float64)
    f_vec = np.array([10.0, 20.0], dtype=np.float64)
    u_vec = np.linalg.solve(k_mat, f_vec)  # [2.0, 2.0]

    # Objectif J(u) = 0.5 * u^T * f (compliance élastique)
    dJ_du = f_vec  # [10.0, 20.0]

    dK_dtheta = {"theta": np.array([[1.0, 0.0], [0.0, 2.0]], dtype=np.float64)}
    df_dtheta = {"theta": np.zeros(2, dtype=np.float64)}

    res = AdjointSensitivityEngine.compute_adjoint_gradient(
        stiffness_matrix=k_mat,
        displacement_vector=u_vec,
        d_objective_d_displacement=dJ_du,
        d_stiffness_d_params=dK_dtheta,
        d_force_d_params=df_dtheta
    )

    # Sensibilité analytique exacte dJ/dtheta = - u^T * (dK/dtheta) * u = - (2^2 * 1 + 2^2 * 2) = - (4 + 8) = -12.0
    assert "theta" in res.parameter_gradients
    np.testing.assert_allclose(res.parameter_gradients["theta"], -12.0, atol=1e-5)


def test_cutfem_ghost_penalty_and_sdt() -> None:
    """Vérifie la pénalité fantôme CutFEM et le torseur des petits déplacements SDT."""
    # Fraction volumique saine >= 0.2 : pas de pénalité
    assert CutFEMStabilizer.compute_ghost_penalty_factor(0.5) == 0.0

    # Petite fraction volumique < 0.2 : pénalité active et positive
    penalty = CutFEMStabilizer.compute_ghost_penalty_factor(0.01)
    assert penalty > 0.0

    # Torseur des petits déplacements (SDT)
    sdt1 = SmallDisplacementTorsor(rot_alpha=1e-5, trans_u=0.005, tol_trans_max=0.02)
    sdt2 = SmallDisplacementTorsor(rot_alpha=2e-5, trans_u=0.008, tol_trans_max=0.02)
    acc = sdt1.accumulate(sdt2)

    assert acc.rot_alpha == pytest.approx(3e-5)
    assert acc.trans_u == pytest.approx(0.013)
    assert acc.is_within_tolerance()
