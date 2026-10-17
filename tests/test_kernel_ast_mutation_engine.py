"""
Suite de tests exhaustifs pour le Moteur de Mutation Testing In-Process (KernelAstMutationEngine).
Valide :
1. Le hot-patching de bytecode en RAM via compile() et sys.modules sans écriture disque.
2. Les 4 familles d'opérateurs géométriques spécialisés : G-AOR, G-ROR, G-TR, G-SOLV.
3. La cartographie des 90+ points névralgiques du kernel avec leurs micro-tests dédiés.
4. Le respect absolu du temps d'exécution < 3.0 secondes pour l'ensemble des mutants.
"""

from __future__ import annotations
import ast
import inspect
import sys
import textwrap
import time
import types
from typing import Callable, Dict, Union
import pytest
import numpy as np

from src.core.mutation_engine import (
    KernelAstMutationEngine,
    MutationFamily,
    MutantStatus,
    BytecodeHotPatcher,
    GAORTransformer,
    GRORTransformer,
    GTRTransformer,
    GSOLVTransformer,
    KernelMutationRegistry,
)
import src.core.geometry as geom
from src.core.types import Point2D, Vector3D
import src.solver.constraints_2d as solver2d
import src.specialized.robot_kinematics as rkin


class TestAstTransformers:
    """Tests unitaires des 4 familles de transformateurs AST géométriques."""

    def test_gaor_transformer_inverts_binary_and_unary_operators(self) -> None:
        """Vérifie que G-AOR inverse les additions/soustractions et les signes unaires."""
        code = textwrap.dedent("""
            def calc_vector(x, y):
                return -(x + y) - (x - y)
        """)
        tree = ast.parse(code)
        transformer = GAORTransformer(target_occurrence=0)
        mutated_tree = transformer.visit(tree)
        ast.fix_missing_locations(mutated_tree)

        compiled = compile(mutated_tree, "<gaor_test>", "exec")
        ns: Dict[str, Callable[[float, float], float]] = {}
        exec(compiled, {}, ns)
        mutated_func = ns["calc_vector"]
        assert callable(mutated_func)

        # Avec code d'origine : calc(10, 5) = -(15) - (5) = -20
        # Avec target_occurrence=0, le signe ou opérateur est modifié
        res = mutated_func(10, 5)
        assert res != -20

    def test_gror_transformer_alters_tolerances_and_comparisons(self) -> None:
        """Vérifie que G-ROR modifie les tolérances et les comparateurs logiques."""
        code = textwrap.dedent("""
            def check_threshold(val):
                eps = 1e-4
                return val < eps
        """)
        tree = ast.parse(code)
        transformer = GRORTransformer(target_occurrence=0, mode="compare")
        mutated_tree = transformer.visit(tree)
        ast.fix_missing_locations(mutated_tree)

        compiled = compile(mutated_tree, "<gror_test>", "exec")
        ns: Dict[str, Callable[[float], bool]] = {}
        exec(compiled, {}, ns)
        mutated_func = ns["check_threshold"]
        assert callable(mutated_func)

        # Dans l'original, check(1e-5) est True. Avec < muté en >=, devient False
        assert mutated_func(1e-5) is False

        # Vérifie également la mutation de constante epsilon
        transformer_const = GRORTransformer(target_occurrence=0, mode="constant", scale_epsilon=1e-5)
        tree_const = ast.parse(code)
        mutated_const = transformer_const.visit(tree_const)
        ast.fix_missing_locations(mutated_const)
        compiled_const = compile(mutated_const, "<gror_const_test>", "exec")
        ns_const: Dict[str, Callable[[float], bool]] = {}
        exec(compiled_const, {}, ns_const)
        mut_const_fn = ns_const["check_threshold"]
        # eps 1e-4 muté en 1e-9 -> 1e-5 < 1e-9 est False
        assert mut_const_fn(1e-5) is False

    def test_gtr_transformer_swaps_trigonometric_functions(self) -> None:
        """Vérifie que G-TR permute cosinus et sinus pour les rotations 3D."""
        code = textwrap.dedent("""
            import numpy as np
            def rot_component(theta):
                return np.cos(theta)
        """)
        tree = ast.parse(code)
        transformer = GTRTransformer(target_occurrence=0)
        mutated_tree = transformer.visit(tree)
        ast.fix_missing_locations(mutated_tree)

        compiled = compile(mutated_tree, "<gtr_test>", "exec")
        ns: Dict[str, Union[Callable[[float], float], types.ModuleType]] = {"np": np}
        exec(compiled, ns, ns)
        mutated_func = ns["rot_component"]
        assert callable(mutated_func)

        # np.cos(0.0) = 1.0. Avec permutation en np.sin(0.0), vaut 0.0
        assert abs(float(mutated_func(0.0)) - 0.0) < 1e-6

    def test_gsolv_transformer_perturbs_jacobian_matrix_assignments(self) -> None:
        """Vérifie que G-SOLV perturbe les affectations de la Jacobienne."""
        code = textwrap.dedent("""
            import numpy as np
            def fill_jac():
                j_mat = np.zeros((2, 2))
                j_mat[0, 0] = 1.0
                return j_mat
        """)
        tree = ast.parse(code)
        transformer = GSOLVTransformer(target_occurrence=0)
        mutated_tree = transformer.visit(tree)
        ast.fix_missing_locations(mutated_tree)

        compiled = compile(mutated_tree, "<gsolv_test>", "exec")
        ns: Dict[str, Union[Callable[[], np.ndarray], types.ModuleType]] = {"np": np}
        exec(compiled, ns, ns)
        mutated_func = ns["fill_jac"]
        assert callable(mutated_func)

        # Avec G-SOLV, j_mat[0, 0] = -1.0
        j = mutated_func()
        assert abs(float(j[0, 0]) - (-1.0)) < 1e-6


class TestBytecodeHotPatcher:
    """Tests unitaires du hot-patching de bytecode en RAM via compile() et sys.modules."""

    def test_hot_patch_in_memory_and_atomic_rollback(self) -> None:
        """Vérifie le remplacement de méthode en mémoire vive et sa restauration atomique."""
        arm = rkin.RobotArm6Axis()
        original_dh = rkin.RobotArm6Axis._dh_matrix

        def dummy_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
            return np.ones((4, 4), dtype=np.float64)

        with BytecodeHotPatcher.patch_callable(
            "src.specialized.robot_kinematics",
            "RobotArm6Axis",
            "_dh_matrix",
            dummy_dh
        ):
            res_patched = arm._dh_matrix(1, 2, 3, 4)
            assert np.all(res_patched == 1.0)

        # Après sortie du contexte, le comportement original doit être restauré
        res_restored = arm._dh_matrix(0, 0, 0, 0)
        assert res_restored[3, 3] == 1.0
        assert res_restored[0, 1] == 0.0
        assert rkin.RobotArm6Axis._dh_matrix is original_dh

    def test_patch_ast_directly_in_ram(self) -> None:
        """Vérifie l'application d'un transformateur AST directement en RAM sans fichier temporaire."""
        arm = rkin.RobotArm6Axis()
        t0 = arm.forward_kinematics([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])

        with BytecodeHotPatcher.patch_ast(
            "src.specialized.robot_kinematics",
            "RobotArm6Axis",
            "_dh_matrix",
            GAORTransformer(target_occurrence=0),
            identifier="test_dynamic_ram"
        ):
            t_mut = arm.forward_kinematics([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
            assert np.max(np.abs(t_mut - t0)) > 1.0

        # Vérifie restauration
        t_after = arm.forward_kinematics([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        assert np.max(np.abs(t_after - t0)) < 1e-9


class TestKernelAstMutationEngine:
    """Tests d'intégration du moteur de mutation testing sur l'ensemble du kernel CAO."""

    def test_engine_has_at_least_90_mapped_mutants(self) -> None:
        """Exigence #3 : Cartographie de 90+ points névralgiques du kernel."""
        engine = KernelAstMutationEngine()
        assert engine.total_count >= 90, f"Le moteur doit contenir au moins 90 mutants (actuel: {engine.total_count})"

        # Vérifie que les 3 sous-systèmes névralgiques sont abondamment couverts
        mutants = engine.mutants
        geom_mutants = [m for m in mutants if m.subsystem == "geometry"]
        solv_mutants = [m for m in mutants if m.subsystem == "solver_2d"]
        rob_mutants = [m for m in mutants if m.subsystem == "robotics"]

        assert len(geom_mutants) >= 30, "Sous-système geometry doit contenir au moins 30 mutants"
        assert len(solv_mutants) >= 30, "Sous-système solver_2d doit contenir au moins 30 mutants"
        assert len(rob_mutants) >= 20, "Sous-système robotics doit contenir au moins 20 mutants"

    def test_engine_covers_all_4_geometric_mutation_families(self) -> None:
        """Exigence #2 : Présence des 4 familles d'opérateurs géométriques spécialisés."""
        engine = KernelAstMutationEngine()
        families = set(m.family for m in engine.mutants)
        assert MutationFamily.G_AOR in families, "Famille G-AOR manquante"
        assert MutationFamily.G_ROR in families, "Famille G-ROR manquante"
        assert MutationFamily.G_TR in families, "Famille G-TR manquante"
        assert MutationFamily.G_SOLV in families, "Famille G-SOLV manquante"

    def test_full_mutation_campaign_execution_under_3_seconds(self) -> None:
        """Exigence #4 : Temps d'exécution total strictement inférieur à 3.0 secondes."""
        engine = KernelAstMutationEngine()
        t_start = time.perf_counter()
        report = engine.run_all()
        elapsed = time.perf_counter() - t_start

        # Temps d'exécution
        assert report.total_duration_seconds < 3.0, f"Temps d'exécution ({report.total_duration_seconds:.3f}s) > 3.0s"
        assert elapsed < 3.0, f"Temps total d'exécution ({elapsed:.3f}s) > 3.0s"

        # Taux de détection (Kill Rate) maximal
        assert report.total_mutants >= 90
        assert report.kill_rate_percent >= 95.0, f"Taux de mutants tués ({report.kill_rate_percent:.1f}%) < 95%"
        assert report.survived_count == 0, f"Certains mutants ont survécu : {report.survived_count}"
        assert report.errored_count == 0, f"Erreurs d'exécution anormales : {report.errored_count}"

    def test_subsystem_filter_geometry(self) -> None:
        """Vérifie l'exécution sélective du sous-système CSG géométrique."""
        engine = KernelAstMutationEngine()
        report = engine.run_all(filter_subsystem="geometry")
        assert report.total_mutants >= 30
        assert all(r.subsystem == "geometry" for r in report.results)
        assert report.kill_rate_percent == 100.0

    def test_subsystem_filter_solver_2d(self) -> None:
        """Vérifie l'exécution sélective du solveur Levenberg-Marquardt."""
        engine = KernelAstMutationEngine()
        report = engine.run_all(filter_subsystem="solver_2d")
        assert report.total_mutants >= 30
        assert all(r.subsystem == "solver_2d" for r in report.results)
        assert report.kill_rate_percent == 100.0

    def test_subsystem_filter_robotics(self) -> None:
        """Vérifie l'exécution sélective de la cinématique robotique."""
        engine = KernelAstMutationEngine()
        report = engine.run_all(filter_subsystem="robotics")
        assert report.total_mutants >= 20
        assert all(r.subsystem == "robotics" for r in report.results)
        assert report.kill_rate_percent == 100.0

    def test_family_filter_g_aor(self) -> None:
        """Vérifie l'exécution sélective de la famille G-AOR."""
        engine = KernelAstMutationEngine()
        report = engine.run_all(filter_family=MutationFamily.G_AOR)
        assert report.total_mutants >= 20
        assert all(r.family == MutationFamily.G_AOR for r in report.results)
        assert report.kill_rate_percent == 100.0

    def test_family_filter_g_solv(self) -> None:
        """Vérifie l'exécution sélective de la famille G-SOLV."""
        engine = KernelAstMutationEngine()
        report = engine.run_all(filter_family=MutationFamily.G_SOLV)
        assert report.total_mutants >= 20
        assert all(r.family == MutationFamily.G_SOLV for r in report.results)
        assert report.kill_rate_percent == 100.0
