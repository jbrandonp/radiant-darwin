"""
Suite de Tests de Non-Régression pour les Stress-Tests Destructifs Avancés & Bifurcations Non-Linéaires.
Valide mathématiquement et physiquement les 6 domaines de défaillance critique (Phase 4) :

1. Domaine 1 : Endommagement ductile continu de Lemaitre (D -> 1.0, striction et contrainte effective nulle).
2. Domaine 2 : Bifurcation de Hopf aéroélastique (flutter pitch-plunge, Re(lambda) > 0 à V > V_flutter).
3. Domaine 3 : Contact frottant Coulomb & Perforation de barrière de pénalité (|gap| > g_crit).
4. Domaine 4 : Saturation dynamique des couples moteurs de robot 6 axes (tau > tau_max = 150 N.m).
5. Domaine 5 : Prédicats exacts de Shewchuk orient3d (inversion d'élément, collapse coplanaire).
6. Domaine 6 : Instabilité symplectique & Explosion CFL (dt > 2 / omega_max, croissance d'énergie > 10^9).
7. Intégration globale : Exécution et certification du rapport JSON de la campagne.

Typage statique strict (zéro Any, zéro object) et complexité cognitive <= 25 par fonction.
"""

from __future__ import annotations
import json
import math
import os
from typing import Dict, List, Union

import numpy as np
import pytest

from scripts.advanced_destructive_bifurcation_tests import (
    AdvancedBifurcationResult,
    assemble_aeroelastic_system_matrix,
    compute_lemaitre_damage,
    compute_robot_joint_torques,
    run_aeroelastic_pitch_plunge_flutter_bifurcation_test,
    run_all_advanced_destructive_bifurcation_tests,
    run_continuum_damage_ductile_rupture_test,
    run_exact_predicates_brep_topological_collapse_test,
    run_frictional_penalty_barrier_breach_test,
    run_robot_dynamics_torque_saturation_bifurcation_test,
    run_symplectic_integrator_cfl_explosion_test,
)
from src.core.nexus_kernel.robust_predicates import RobustGeometricPredicates
from src.fea.nonlinear_fem import BilinearPlasticMaterial, FrictionalContactPair
from src.specialized.robot_kinematics import RobotArm6Axis


class TestAdvancedDestructiveBifurcations:
    """Banc de tests analytiques certifiant la précision des bifurcations non-linéaires."""

    def test_domain1_continuum_damage_ductile_rupture_bifurcation(self) -> None:
        """Vérifie la loi d'endommagement de Lemaitre et la striction plastique jusqu'à rupture."""
        res: AdvancedBifurcationResult = run_continuum_damage_ductile_rupture_test()

        assert res.status == "BIFURCATION_CONFIRMED"
        assert res.failure_step == 7
        assert res.critical_metric_name == "damage_variable_D"
        assert res.critical_metric_value == 1.0
        assert res.details["necking_fracture_confirmed"] is True
        assert float(res.details["final_effective_stress_mpa"]) == pytest.approx(0.0, abs=1e-5)
        assert float(res.details["total_plastic_work_mj_m3"]) > 50.0

        # Vérification du comportement analytique de la fonction scalaire d'endommagement
        assert compute_lemaitre_damage(plastic_strain=0.02, eps_thresh=0.05, eps_rupture=0.22) == 0.0
        assert compute_lemaitre_damage(plastic_strain=0.25, eps_thresh=0.05, eps_rupture=0.22) == 1.0

    def test_domain2_aeroelastic_pitch_plunge_flutter_hopf_bifurcation(self) -> None:
        """Vérifie la bifurcation de Hopf aéroélastique et la traversée de l'axe imaginaire."""
        res: AdvancedBifurcationResult = run_aeroelastic_pitch_plunge_flutter_bifurcation_test()

        assert res.status == "BIFURCATION_CONFIRMED"
        assert res.failure_step == 4
        assert res.critical_metric_name == "max_real_eigenvalue_sigma"
        assert res.critical_metric_value > 0.0
        assert res.details["hopf_bifurcation_detected"] is True

        # Vérification de la stabilité à basse vitesse et instabilité à haute vitesse
        a_stable = assemble_aeroelastic_system_matrix(
            airspeed_v=25.0,
            mass=12.0,
            inertia_alpha=1.5,
            x_alpha=0.15,
            semi_chord_b=0.5,
            omega_h=25.0,
            omega_alpha=50.0,
            c_l_alpha=2.0 * np.pi,
            air_density=1.225,
            elastic_axis_offset_e=0.15
        )
        max_re_stable = float(np.max(np.real(np.linalg.eigvals(a_stable))))
        assert max_re_stable < 0.0, "Le système doit être strictement stable et amorti à 25 m/s"

        a_flutter = assemble_aeroelastic_system_matrix(
            airspeed_v=55.0,
            mass=12.0,
            inertia_alpha=1.5,
            x_alpha=0.15,
            semi_chord_b=0.5,
            omega_h=25.0,
            omega_alpha=50.0,
            c_l_alpha=2.0 * np.pi,
            air_density=1.225,
            elastic_axis_offset_e=0.15
        )
        max_re_flutter = float(np.max(np.real(np.linalg.eigvals(a_flutter))))
        assert max_re_flutter > 0.0, "Le système doit diverger par flottement dynamique à 55 m/s"

    def test_domain3_frictional_penalty_barrier_breach_and_stick_slip(self) -> None:
        """Vérifie la transition Stick -> Slip et la perforation de la barrière de pénalité."""
        res: AdvancedBifurcationResult = run_frictional_penalty_barrier_breach_test()

        assert res.status == "BIFURCATION_CONFIRMED"
        assert res.failure_step == 4
        assert res.details["stick_to_slip_transition"] is True
        assert res.details["barrier_breach_detected"] is True
        assert float(res.critical_metric_value) > res.analytical_bound

        # Vérification unitaire de la formulation de pénalité frottante
        cp = FrictionalContactPair(
            slave_node_coords=np.array([0.0, 0.0, 0.0], dtype=np.float64),
            master_plane_origin=np.array([0.0, 0.0, 0.0], dtype=np.float64),
            master_plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
            friction_coefficient=0.30,
            penalty_stiffness=10000.0
        )
        fn, ft = cp.compute_contact_force(penetration_gap=-0.1, tangential_slip=0.001)
        assert fn == pytest.approx(1000.0, abs=1e-3)
        assert ft == pytest.approx(10.0, abs=1e-3)  # Régime Stick pur (10 < 300 N)

        fn_slip, ft_slip = cp.compute_contact_force(penetration_gap=-0.1, tangential_slip=0.05)
        assert ft_slip == pytest.approx(300.0, abs=1e-3)  # Régime Slip saturé à mu * Fn

    def test_domain4_robot_dynamics_torque_saturation_bifurcation(self) -> None:
        """Vérifie la saturation des actionneurs et dépassement du couple nominal admissible."""
        res: AdvancedBifurcationResult = run_robot_dynamics_torque_saturation_bifurcation_test()

        assert res.status == "BIFURCATION_CONFIRMED"
        assert res.failure_step == 3
        assert res.critical_metric_value > res.analytical_bound
        assert res.critical_metric_value == pytest.approx(154.836, rel=1e-2)
        assert res.details["actuator_saturation_exceeded"] is True

        # Vérification du dimensionnement à faible accélération (régime sûr)
        arm = RobotArm6Axis()
        q = np.array([0.0, np.pi / 4.0, -np.pi / 4.0, 0.0, np.pi / 6.0, 0.0], dtype=np.float64)
        _, tau_safe = compute_robot_joint_torques(arm, q, cartesian_accel_m_s2=1.0, payload_mass_kg=6.0)
        assert tau_safe < 100.0, "À 1 m/s^2, le couple doit rester sous 100 N.m (marge confortable)"

    def test_domain5_exact_shewchuk_predicates_brep_topological_collapse(self) -> None:
        """Vérifie les prédicats exacts de Shewchuk et l'inversion d'élément volumique."""
        res: AdvancedBifurcationResult = run_exact_predicates_brep_topological_collapse_test()

        assert res.status == "BIFURCATION_CONFIRMED"
        assert res.failure_step == 5
        assert res.critical_metric_value == -1.0
        assert res.details["inverted_orient_detected"] is True
        assert res.details["coplanar_degeneracy_step"] == 4

        # Vérification directe des 3 régimes d'orientation géométrique
        pt_a = (0.0, 0.0, 0.0)
        pt_c = (5.0, 8.660254037844386, 0.0)
        pt_b = (10.0, 0.0, 0.0)

        # 1. Apex au-dessus : volume positif non-dégénéré
        assert RobustGeometricPredicates.orient3d(pt_a, pt_c, pt_b, (5.0, 2.886751, 5.0)) == 1
        # 2. Apex coplanaire : volume nul, singularité limite
        assert RobustGeometricPredicates.orient3d(pt_a, pt_c, pt_b, (5.0, 2.886751, 0.0)) == 0
        # 3. Apex traversant : inversion topologique de frontière B-Rep
        assert RobustGeometricPredicates.orient3d(pt_a, pt_c, pt_b, (5.0, 2.886751, -2.0)) == -1

    def test_domain6_symplectic_integrator_cfl_explosion(self) -> None:
        """Vérifie la limite de stabilité de Courant-Friedrichs-Lewy (CFL) et la divergence d'énergie."""
        res: AdvancedBifurcationResult = run_symplectic_integrator_cfl_explosion_test()

        assert res.status == "BIFURCATION_CONFIRMED"
        assert res.failure_step == 4
        assert res.critical_metric_value == pytest.approx(0.0085, abs=1e-4)
        assert res.critical_metric_value > res.analytical_bound
        assert res.details["energy_growth_ratio"] > 1e9
        assert res.details["numerical_explosion_confirmed"] is True

        # Vérification du pas critique analytique dt_cfl = 2 / omega_max
        omega_max = math.sqrt(60000.0)
        dt_cfl_theoretical = 2.0 / omega_max
        assert res.analytical_bound == pytest.approx(dt_cfl_theoretical, rel=1e-4)

    def test_full_advanced_destructive_bifurcation_campaign_orchestration(self) -> None:
        """Vérifie l'exécution globale des 6 bancs et la génération du rapport JSON certifié."""
        payload = run_all_advanced_destructive_bifurcation_tests()

        assert payload["phase"] == 4
        assert payload["total_domains_tested"] == 6
        assert payload["bifurcations_confirmed"] == 6
        assert isinstance(payload["elapsed_seconds"], float)
        assert payload["elapsed_seconds"] < 2.0, "La campagne de stress-tests doit s'exécuter en moins de 2s"

        results_list = payload["results"]
        assert isinstance(results_list, list)
        assert len(results_list) == 6

        # Vérification de la persistance sur le disque
        report_path = os.path.join("demo_output", "simulations", "advanced_destructive_bifurcation_report.json")
        assert os.path.isfile(report_path)
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["bifurcations_confirmed"] == 6
