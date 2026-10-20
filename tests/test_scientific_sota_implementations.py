"""
Suite de tests unitaires pour les implémentations scientifiques SOTA 2026 :
1. Théorème de Laman & Décomposition de Dulmage-Mendelsohn (src/solver/structural_rigidity.py)
2. Lissage de trajectoire 5-axes à Jerk Minimal (src/cam/minimal_jerk_planner.py)
3. Prédicats géométriques exacts de Shewchuk (src/core/adaptive_predicates.py)
4. Commande d'audit des compétences (src/cli.py audit-skills)

Typage statique strict : strictement zéro Any et zéro object, complexité cognitive <= 15.
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple
import pytest

from src.core.types import Vector3D
from src.core.adaptive_predicates import (
    two_sum,
    two_product,
    ShewchukAdaptivePredicates,
)
from src.solver.structural_rigidity import (
    LamanRigidityOracle,
    LamanRigidityResult,
    DulmageMendelsohnPartitioner,
    DulmageMendelsohnResult,
)
from src.cam.minimal_jerk_planner import (
    Waypoint5Axis,
    TrajectoryPlanningResult,
    MinimalJerkTrajectoryPlanner,
)
from src.cli import main as cli_main


class TestLamanAndDulmageMendelsohn:
    """Tests de validation de la rigidité de Laman et du partitionnement de Dulmage-Mendelsohn."""

    def test_laman_triangle_rigid(self) -> None:
        """Un triangle (3 sommets, 3 arêtes) doit être génériquement rigide (2*3 - 3 = 3)."""
        edges: List[Tuple[int, int]] = [(0, 1), (1, 2), (2, 0)]
        res: LamanRigidityResult = LamanRigidityOracle.evaluate_graph(3, edges)

        assert res.vertex_count == 3
        assert res.edge_count == 3
        assert res.is_rigid is True
        assert res.degrees_of_freedom == 0
        assert len(res.violating_subgraphs) == 0

    def test_laman_square_under_constrained(self) -> None:
        """Un carré articulé (4 sommets, 4 arêtes) possède 1 DDL (2*4 - 3 = 5, manque 1 arête)."""
        edges: List[Tuple[int, int]] = [(0, 1), (1, 2), (2, 3), (3, 0)]
        res: LamanRigidityResult = LamanRigidityOracle.evaluate_graph(4, edges)

        assert res.is_rigid is False
        assert res.degrees_of_freedom == 1

    def test_laman_double_triangle_rigid(self) -> None:
        """Deux triangles partageant une arête (4 sommets, 5 arêtes) sont rigides."""
        edges: List[Tuple[int, int]] = [(0, 1), (1, 2), (2, 0), (2, 3), (3, 1)]
        res: LamanRigidityResult = LamanRigidityOracle.evaluate_graph(4, edges)

        assert res.is_rigid is True
        assert res.degrees_of_freedom == 0

    def test_dulmage_mendelsohn_well_constrained(self) -> None:
        """Un système 2x2 carré indépendant doit être classifié comme bien contraint."""
        params = ["x", "y"]
        constraints = ["c1", "c2"]
        incidence: Dict[str, List[str]] = {
            "c1": ["x"],
            "c2": ["y"],
        }
        res: DulmageMendelsohnResult = DulmageMendelsohnPartitioner.partition(
            params, constraints, incidence
        )

        assert res.is_well_constrained is True
        assert len(res.under_constrained_params) == 0
        assert len(res.over_constrained_constraints) == 0
        assert res.matching_size == 2

    def test_dulmage_mendelsohn_under_and_over(self) -> None:
        """Détecte les variables libres et les contraintes redondantes sans couplage."""
        params = ["x", "y", "z"]
        constraints = ["c1", "c2", "c3", "c4"]
        incidence: Dict[str, List[str]] = {
            "c1": ["x"],
            "c2": ["y"],
            "c3": ["x", "y"],
            "c4": ["x"],
        }
        res: DulmageMendelsohnResult = DulmageMendelsohnPartitioner.partition(
            params, constraints, incidence
        )

        assert res.is_well_constrained is False
        assert "z" in res.under_constrained_params
        assert len(res.over_constrained_constraints) >= 2


class TestMinimalJerkPlanner:
    """Tests du planificateur de trajectoire à jerk minimal 5-axes."""

    def test_quintic_boundary_conditions(self) -> None:
        """Vérifie que le profil quintique annule vitesse et accélération aux bornes."""
        s0, v0, a0, j0 = MinimalJerkTrajectoryPlanner.quintic_profile(0.0)
        assert pytest.approx(s0, abs=1e-6) == 0.0
        assert pytest.approx(v0, abs=1e-6) == 0.0
        assert pytest.approx(a0, abs=1e-6) == 0.0

        s1, v1, a1, j1 = MinimalJerkTrajectoryPlanner.quintic_profile(1.0)
        assert pytest.approx(s1, abs=1e-6) == 1.0
        assert pytest.approx(v1, abs=1e-6) == 0.0
        assert pytest.approx(a1, abs=1e-6) == 0.0

    def test_multi_segment_toolpath_planning(self) -> None:
        """Planifie une trajectoire 3 points et vérifie la continuité et le jerk fini."""
        w1 = Waypoint5Axis(Vector3D(0.0, 0.0, 0.0), Vector3D(0.0, 0.0, 1.0), 1200.0)
        w2 = Waypoint5Axis(Vector3D(50.0, 0.0, 10.0), Vector3D(0.1, 0.0, 0.99), 1200.0)
        w3 = Waypoint5Axis(Vector3D(100.0, 50.0, 20.0), Vector3D(0.0, 0.2, 0.98), 1200.0)

        result: TrajectoryPlanningResult = MinimalJerkTrajectoryPlanner.plan_toolpath(
            [w1, w2, w3], default_feedrate_mm_min=1200.0, step_dt_s=0.05
        )

        assert result.total_duration_s > 0.0
        assert result.sample_count > 10
        assert result.peak_linear_jerk_mm_s3 > 0.0
        assert not math.isinf(result.peak_linear_jerk_mm_s3)
        assert not math.isnan(result.peak_linear_jerk_mm_s3)

        # Vérification du premier et dernier point
        assert pytest.approx(result.samples[0].position.x, abs=1e-3) == 0.0
        assert pytest.approx(result.samples[-1].position.x, abs=1e-3) == 100.0


class TestShewchukExactPredicates:
    """Tests des prédicats adaptatifs de Shewchuk et arithmétique d'expansion."""

    def test_two_sum_and_two_product(self) -> None:
        """Vérifie l'exactitude de l'addition et de la multiplication exacte."""
        a = 1.0 + 1e-15
        b = 1.0 - 1e-15
        s, e = two_sum(a, b)
        assert pytest.approx(s, abs=1e-12) == 2.0

        p, pe = two_product(1.0000001, 1.0000002)
        assert pytest.approx(p + pe, abs=1e-15) == 1.0000001 * 1.0000002

    def test_orient2d_triangles_and_collinear(self) -> None:
        """Vérifie le sens trigonométrique (>0), horaire (<0) et la colinéarité (=0)."""
        pa = (0.0, 0.0)
        pb = (1.0, 0.0)
        pc = (0.0, 1.0)
        assert ShewchukAdaptivePredicates.orient2d(pa, pb, pc) > 0.0
        assert ShewchukAdaptivePredicates.orient2d(pa, pc, pb) < 0.0

        # Points colinéaires stricts
        p_col = (2.0, 0.0)
        assert ShewchukAdaptivePredicates.orient2d(pa, pb, p_col) == 0.0

    def test_orient3d_above_below_coplanar(self) -> None:
        """Vérifie l'orientation 3D relative d'un point par rapport à une facette."""
        pa = Vector3D(0.0, 0.0, 0.0)
        pb = Vector3D(1.0, 0.0, 0.0)
        pc = Vector3D(0.0, 1.0, 0.0)

        # Point en-dessous du plan z=0
        pd_below = Vector3D(0.2, 0.2, -1.0)
        assert ShewchukAdaptivePredicates.orient3d(pa, pb, pc, pd_below) > 0.0

        # Point au-dessus du plan z=0
        pd_above = Vector3D(0.2, 0.2, 1.0)
        assert ShewchukAdaptivePredicates.orient3d(pa, pb, pc, pd_above) < 0.0

        # Point coplanaire dans le plan z=0
        pd_coplanar = Vector3D(0.5, 0.5, 0.0)
        assert ShewchukAdaptivePredicates.orient3d(pa, pb, pc, pd_coplanar) == 0.0

    def test_incircle2d_delaunay(self) -> None:
        """Vérifie le test d'appartenance au cercle circonscrit 2D."""
        pa = (0.0, 0.0)
        pb = (1.0, 0.0)
        pc = (0.0, 1.0)

        # Le centre du cercle circonscrit est (0.5, 0.5), rayon sqrt(0.5) ~ 0.707
        # Point intérieur (0.2, 0.2)
        assert ShewchukAdaptivePredicates.incircle2d(pa, pb, pc, (0.2, 0.2)) > 0.0
        # Point extérieur (2.0, 2.0)
        assert ShewchukAdaptivePredicates.incircle2d(pa, pb, pc, (2.0, 2.0)) < 0.0


class TestSkillsCliIntegration:
    """Vérifie que la sous-commande audit-skills s'exécute correctement."""

    def test_cli_audit_skills_subcommand(self) -> None:
        """Exécute 'audit-skills' via le point d'entrée principal du CLI."""
        exit_code = cli_main(["audit-skills"])
        assert exit_code == 0
