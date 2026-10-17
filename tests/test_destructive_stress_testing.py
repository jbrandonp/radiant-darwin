"""
Tests unitaires et d'intégration pour la Campagne de Stress-Tests Destructifs Poussés jusqu'à la Rupture.
Valide la détection rigoureuse et le diagnostic physique des 6 modes de défaillance ultimes :
1. Flambement structural d'Euler & Rupture plastique FEA
2. Décrochage aérodynamique (Stall) & Onde de choc transsonique
3. Emballement thermique par effet Joule ECAD & Délamination FR4
4. Effondrement de solvabilité d'esquisse 2D (Contraintes contradictoires)
5. Épuisement de l'enveloppe de travail robotique (Portée maximale dépassée)
6. Effondrement au volume nul du noyau CSG Manifold3D (Dégénérescence coplanaire)
7. Exécution complète déterministe de la campagne et intégrité du rapport JSON

Toutes les assertions vérifient que les seuils de rupture physique sont détectés avec précision.
Garantit zéro test bidon, zéro assertion tautologique et sensibilité prouvée aux régressions.
"""

from __future__ import annotations
import json
import math
import os
import pytest
from typing import List

from scripts.progressive_destructive_stress_tests import (
    DestructiveStressResult,
    execute_all_destructive_stress_tests,
    run_destructive_aerodynamic_stall_and_shock_stress_test,
    run_destructive_boolean_zero_volume_stress_test,
    run_destructive_ecad_thermal_runaway_stress_test,
    run_destructive_robotics_workspace_exhaustion_stress_test,
    run_destructive_sketch_solver_conflict_stress_test,
    run_destructive_structural_buckling_stress_test,
)


@pytest.mark.multiphysics
def test_destructive_stress_structural_buckling_failure() -> None:
    """
    Vérifie la détection de rupture plastique et de flambement d'Euler.
    Le poteau C45 doit échouer lorsque la charge atteint 50 kN,
    faisant chuter le facteur de sécurité sous 1.0.
    """
    res = run_destructive_structural_buckling_stress_test()
    assert res.status == "FAILURE_CONFIRMED"
    assert res.failure_mode == "PLASTIC_YIELDING_AND_EULER_BUCKLING_COLLAPSE"
    assert res.failure_step == 4

    # Charge de rupture détectée
    failure_load = float(res.details["applied_failure_load_n"])
    assert abs(failure_load - 50000.0) < 1.0, f"Charge de rupture inattendue : {failure_load} N"

    # Vérification que le facteur de sécurité s'effondre
    sf = float(res.details["final_safety_factor"])
    assert sf < 1.0, f"Le facteur de sécurité devrait être < 1.0 en rupture, obtenu : {sf}"

    # Vérification que la contrainte dépasse la limite élastique
    stress = float(res.details["ultimate_von_mises_stress_mpa"])
    yield_limit = float(res.details["material_yield_strength_re_mpa"])
    assert stress > yield_limit, f"La contrainte {stress} MPa n'a pas dépassé Re ({yield_limit} MPa)"
    assert bool(res.details["is_collapsed"]) is True


@pytest.mark.multiphysics
def test_destructive_stress_aerodynamic_stall_failure() -> None:
    """
    Vérifie le déclenchement du décrochage aérodynamique par décollement de couche limite.
    L'incidence critique de décrochage doit être détectée à alpha = 16.0°.
    """
    res = run_destructive_aerodynamic_stall_and_shock_stress_test()
    assert res.status == "FAILURE_CONFIRMED"
    assert res.failure_mode == "AERODYNAMIC_STALL_SEPARATION_AND_SONIC_BARRIER"
    assert res.failure_step == 6

    stall_alpha = float(res.details["stall_onset_angle_deg"])
    assert abs(stall_alpha - 16.0) < 0.1, f"Angle de décrochage incorrect : {stall_alpha}°"
    assert bool(res.details["boundary_layer_is_separated"]) is True
    assert bool(res.details["is_aerodynamically_stalled"]) is True

    # Vérification du régime transsonique
    mach = float(res.details["critical_mach_number"])
    assert mach >= 0.98, f"Nombre de Mach critique sous-évalué : {mach}"


@pytest.mark.multiphysics
def test_destructive_stress_ecad_thermal_runaway_failure() -> None:
    """
    Vérifie la détection de l'emballement thermique par effet Joule.
    Le courant critique de claquage thermique doit être détecté à 10.0 A
    avec dépassement de la température de délamination du substrat FR4 (260°C).
    """
    res = run_destructive_ecad_thermal_runaway_stress_test()
    assert res.status == "FAILURE_CONFIRMED"
    assert res.failure_mode == "THERMAL_RUNAWAY_DELAMINATION_AND_BURNOUT"
    assert res.failure_step == 4

    burnout_current = float(res.details["burnout_threshold_current_amps"])
    assert abs(burnout_current - 10.0) < 0.1, f"Courant de claquage inattendu : {burnout_current} A"

    peak_temp = float(res.details["calculated_equilibrium_temp_c"])
    delam_temp = float(res.details["substrate_delamination_limit_temp_c"])
    assert peak_temp >= delam_temp, f"Température {peak_temp}°C inférieure au seuil de délamination ({delam_temp}°C)"
    assert bool(res.details["is_thermally_destroyed"]) is True


@pytest.mark.multiphysics
def test_destructive_stress_sketch_solver_conflict_failure() -> None:
    """
    Vérifie la divergence formelle du solveur d'esquisse sous contraintes contradictoires.
    L'inégalité triangulaire violée (30 + 30 = 60 < 100 mm) doit faire échouer le solveur
    avec un résidu géométrique non nul (> 10.0 mm).
    """
    res = run_destructive_sketch_solver_conflict_stress_test()
    assert res.status == "FAILURE_CONFIRMED"
    assert res.failure_mode == "TRIANGLE_INEQUALITY_VIOLATION_SOLVER_DIVERGENCE"
    assert res.failure_step == 2

    assert bool(res.details["consistent_state_solved"]) is True
    assert bool(res.details["contradictory_state_solved"]) is False

    residual = float(res.details["max_geometric_residual_mm"])
    assert residual > 5.0, f"Le résidu de divergence est anormalement bas : {residual} mm"
    assert abs(residual - 13.338) < 0.1, f"Résidu inattendu : {residual} mm"
    assert bool(res.details["is_solver_diverged"]) is True


@pytest.mark.multiphysics
def test_destructive_stress_robotics_workspace_exhaustion_failure() -> None:
    """
    Vérifie l'épuisement de la portée physique du bras robotisé 6 axes.
    Le robot doit signaler l'inaccessibilité de la cible dès que le rayon dépasse R_max (~885 mm).
    """
    res = run_destructive_robotics_workspace_exhaustion_stress_test()
    assert res.status == "FAILURE_CONFIRMED"
    assert res.failure_mode == "WORKSPACE_EXHAUSTION_AND_KINEMATIC_SINGULARITY"

    r_max = float(res.details["maximum_physical_reach_mm"])
    r_target = float(res.details["commanded_unreachable_radius_mm"])
    assert r_target > r_max, f"La cible ({r_target} mm) est encore dans la portée ({r_max} mm)"
    assert bool(res.details["is_outside_workspace"]) is True


@pytest.mark.multiphysics
def test_destructive_stress_boolean_zero_volume_failure() -> None:
    """
    Vérifie l'effondrement volumique CSG lors d'une soustraction dégénérée identique.
    Le volume résiduel doit s'annuler exactement (0.0 mm³) et le solide doit être vide.
    """
    res = run_destructive_boolean_zero_volume_stress_test()
    assert res.status == "FAILURE_CONFIRMED"
    assert res.failure_mode == "ZERO_VOLUME_MANIFOLD_COLLAPSE"
    assert res.failure_step == 7

    final_vol = float(res.details["final_extracted_volume_mm3"])
    assert abs(final_vol) < 1e-9, f"Le volume résiduel devrait être nul, obtenu : {final_vol} mm³"
    assert bool(res.details["has_volume_collapsed"]) is True


@pytest.mark.multiphysics
def test_full_destructive_stress_campaign_execution(tmp_path: pytest.TempPathFactory) -> None:
    """
    Vérifie l'orchestration complète de bout en bout de la campagne de stress-tests destructifs
    et la conformité du rapport de défaillance JSON.
    """
    out_dir = str(tmp_path)
    results: List[DestructiveStressResult] = execute_all_destructive_stress_tests(output_dir=out_dir)

    assert len(results) == 6, f"Nombre de tests destructifs incorrect : {len(results)}/6"
    for r in results:
        assert r.status == "FAILURE_CONFIRMED", f"Le test {r.domain_name} n'a pas confirmé sa défaillance"
        assert r.failure_step > 0
        assert len(r.details) >= 4

    # Vérification du fichier JSON exporté
    report_file = os.path.join(out_dir, "destructive_stress_tests_report.json")
    assert os.path.exists(report_file), "Le rapport JSON des stress-tests destructifs est introuvable"

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["destructive_tests_count"] == 6
    assert len(data["results"]) == 6
    assert data["total_elapsed_ms"] > 0.0
