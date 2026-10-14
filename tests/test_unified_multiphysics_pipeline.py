"""
Test d'Intégration Maître Multiphysique & Géométrique Unifié NEXUS-3D.
Valide l'orchestration continue et synergique de l'ensemble des piliers de rupture :
1. Modélisation topologique formelle B-Rep certifiée par les opérateurs d'Euler.
2. Placement spatial sans singularité par quaternions duaux SE(3) et pipeline Relative-To-Eye.
3. Détection de proximité et barrière non-linéaire inviolable IPC.
4. Analyse de sensibilité inverse par méthode de l'état adjoint O(1).
5. Stabilisation CutFEM par pénalité fantôme sur cellules coupées.
6. Empilement statistique des tolérances géométriques ISO GPS par torseurs SDT.
7. Allocation et sécurisation mémoire générationnelle O(1) via SlotMap Arena.
8. Graphe d'exécution DAG incrémental avec adressage par contenu et mémoisation intégrale.
"""

import pytest
import numpy as np
from typing import List, Dict

from src.core.nexus_kernel import (
    RobustGeometricPredicates,
    Quaternion, DualQuaternion, RelativeToEyePipeline,
    ArenaKey, GenerationalArena,
    DAGNode, IncrementalExecutionDAG, ExecutionStats,
    IncrementalPotentialContact, IPCBarrierResult,
    AdjointSensitivityEngine, AdjointSensitivityResult,
    CutFEMStabilizer, SmallDisplacementTorsor,
    NexusEulerOperators, EulerPoincareDiagnostic,
    NexusSolid
)


def test_complete_unified_geometric_and_multiphysics_workflow() -> None:
    """
    Exécute un workflow industriel complet unifiant la géométrie exacte B-Rep,
    la cinématique multi-corps SE(3), le contact inviolable IPC et la sensibilité adjointe.
    """
    # -------------------------------------------------------------------------
    # 1. Modélisation Topologique Exacte B-Rep & Solide Hybride Dual-BRep
    # -------------------------------------------------------------------------
    solid_a = NexusSolid.make_box(30.0, 30.0, 30.0, name="BaseBlock")
    assert not solid_a.is_empty()
    assert solid_a.volume() == pytest.approx(27000.0, rel=1e-3)

    diagnostic = NexusEulerOperators.verify_euler_poincare(solid_a.brep)
    assert diagnostic.is_valid, f"Diagnostic Euler invalide: {diagnostic.diagnostic_message}"
    assert diagnostic.vertices_count == 8
    assert diagnostic.edges_count == 12
    assert diagnostic.faces_count == 6
    assert diagnostic.euler_characteristic == 2

    # -------------------------------------------------------------------------
    # 3. Placement Cinématique SE(3) via Quaternions Duaux & Multi-Échelle RTE
    # -------------------------------------------------------------------------
    # Positionnement du composant B à 0.05 mm au-dessus du composant A (zone de contact critique)
    dq_placement = DualQuaternion.from_axis_angle_translation(
        axis=[0.0, 0.0, 1.0],
        angle_rad=0.0,
        translation=[0.0, 0.0, 30.05]
    )
    b_origin = dq_placement.transform_point(np.array([0.0, 0.0, 0.0]))
    np.testing.assert_allclose(b_origin, [0.0, 0.0, 30.05], atol=1e-6)

    # Pipeline Relative-to-Eye pour caméra industrielle centrée sur le composant
    camera_pos = [0.0, 0.0, 30.0]
    world_pts = np.array([[0.0, 0.0, 30.05], [30.0, 30.0, 60.05]], dtype=np.float64)
    rte_pts = RelativeToEyePipeline.compute_camera_relative_vertices(world_pts, camera_pos)
    assert rte_pts.dtype == np.float32
    np.testing.assert_allclose(rte_pts[0], [0.0, 0.0, 0.05], atol=1e-5)

    # -------------------------------------------------------------------------
    # 4. Barrière Inviolable IPC (Contact Multi-Corps)
    # -------------------------------------------------------------------------
    contact_gap = 0.05  # mm (inférieur au d_hat de sécurité de 0.1 mm)
    ipc_res = IncrementalPotentialContact.evaluate_barrier(
        distance=contact_gap,
        d_hat=0.1,
        kappa=5.0e4
    )
    assert ipc_res.is_active
    assert ipc_res.barrier_energy > 0.0
    assert ipc_res.repulsive_force > 0.0
    assert ipc_res.barrier_stiffness > 0.0

    # -------------------------------------------------------------------------
    # 5. Sensibilité Inverse Adjointe O(1) & Stabilisation CutFEM
    # -------------------------------------------------------------------------
    # Matrice de rigidité globale 2x2 paramétrée par la raideur k_struct
    k_val = 1200.0
    k_matrix = np.array([[k_val, -200.0], [-200.0, k_val]], dtype=np.float64)
    forces = np.array([100.0, 50.0], dtype=np.float64)
    u_disp = np.linalg.solve(k_matrix, forces)

    dK_dk = {"k_struct": np.eye(2, dtype=np.float64)}
    df_dk = {"k_struct": np.zeros(2, dtype=np.float64)}
    dJ_du = forces  # gradient de la compliance élastique J = 0.5 * u^T * f

    adjoint_res = AdjointSensitivityEngine.compute_adjoint_gradient(
        stiffness_matrix=k_matrix,
        displacement_vector=u_disp,
        d_objective_d_displacement=dJ_du,
        d_stiffness_d_params=dK_dk,
        d_force_d_params=df_dk
    )
    assert "k_struct" in adjoint_res.parameter_gradients
    # La sensibilité de la compliance par rapport à la rigidité est strictement négative
    assert adjoint_res.parameter_gradients["k_struct"] < 0.0

    # Stabilisation de frontière CutFEM (Ghost Penalty)
    ghost_alpha_low = CutFEMStabilizer.compute_ghost_penalty_factor(volume_fraction=0.04)
    ghost_alpha_high = CutFEMStabilizer.compute_ghost_penalty_factor(volume_fraction=0.5)
    assert ghost_alpha_low > 0.0
    assert ghost_alpha_high == 0.0

    # -------------------------------------------------------------------------
    # 6. Tolérancement Statistique SDT (Small Displacement Torsor)
    # -------------------------------------------------------------------------
    torsor_machining = SmallDisplacementTorsor(rot_alpha=1.2e-4, trans_u=0.008, tol_trans_max=0.02)
    torsor_assembly = SmallDisplacementTorsor(rot_alpha=0.8e-4, trans_u=0.005, tol_trans_max=0.02)
    torsor_total = torsor_machining.accumulate(torsor_assembly)
    assert torsor_total.is_within_tolerance()
    assert torsor_total.trans_u == pytest.approx(0.013, abs=1e-6)

    # -------------------------------------------------------------------------
    # 7. Arène Générationnelle SlotMap O(1)
    # -------------------------------------------------------------------------
    arena: GenerationalArena[NexusSolid] = GenerationalArena[NexusSolid]()
    key_a = arena.insert(solid_a)
    assert arena.contains(key_a)
    assert arena.get(key_a) is not None

    removed_solid = arena.remove(key_a)
    assert removed_solid is not None
    assert arena.get(key_a) is None  # Accès périmé interdit !

    # -------------------------------------------------------------------------
    # 8. Graphe d'Exécution Incrémental DAG avec Mémoisation 100%
    # -------------------------------------------------------------------------
    dag: IncrementalExecutionDAG[float] = IncrementalExecutionDAG[float]()

    def op_geom_volume(node: DAGNode, inputs: List[float]) -> float:
        l = float(node.params.get("length", 10.0))
        return l ** 3.0

    def op_ipc_force(node: DAGNode, inputs: List[float]) -> float:
        gap = float(node.params.get("gap", 0.05))
        res = IncrementalPotentialContact.evaluate_barrier(gap, d_hat=0.1)
        return float(res.repulsive_force)

    dag.register_operator("volume", op_geom_volume)
    dag.register_operator("contact", op_ipc_force)

    dag.add_or_update_node("geom_node", "volume", {"length": 30.0})
    dag.add_or_update_node("ipc_node", "contact", {"gap": 0.05}, dependencies=["geom_node"])

    stats1 = dag.evaluate_incremental()
    assert stats1.total_nodes == 2
    assert stats1.executed_nodes_count == 2
    assert stats1.cached_nodes_count == 0
    assert dag.get_result("geom_node") == pytest.approx(27000.0)

    # Deuxième évaluation sans modification : mémoisation totale en O(1)
    stats2 = dag.evaluate_incremental()
    assert stats2.executed_nodes_count == 0
    assert stats2.cached_nodes_count == 2
    assert stats2.cache_hit_rate_percent == 100.0
