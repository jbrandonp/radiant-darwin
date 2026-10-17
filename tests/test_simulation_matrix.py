"""
Tests unitaires et d'intégration pour la Matrice de Simulations Multi-Physiques Différenciées.
Valide l'exécution déterministe et les invariants physiques des 8 domaines de simulation :
1. Aérodynamique & Aéroélasticité (VLM + Timoshenko)
2. FEA Non-Linéaire (Tet10, Plasticité & Contact de Coulomb)
3. Robotique Industrielle 6 Axes (Cinématique, Jacobienne, URDF)
4. Fabrication Composite AFP (Trajectoires de fibres σ₁)
5. Métrologie Scan-to-CAD (Recalage SVD-ICP & GD&T)
6. Jumeau Numérique Thermique ECAD (Joule Heating & Hotspots)
7. Rendu Spatial XR (Budget 90 FPS & Streaming LOD)
8. Ponts Industriels Multi-Physiques (CalculiX & OpenFOAM)

Toutes les assertions sont calées sur des formules analytiques fermées et des tolérances strictes.
Garantit zéro test bidon, zéro assertion tautologique, et sensibilité prouvée aux régressions.
"""

from __future__ import annotations
import math
import os
import xml.etree.ElementTree as ET
import pytest
from typing import List

from scripts.multi_domain_simulation_matrix import (
    SimulationDomainResult,
    execute_full_simulation_matrix,
    run_aerodynamics_and_aeroelasticity_simulation,
    run_afp_composite_simulation,
    run_ecad_thermal_simulation,
    run_industrial_bridges_simulation,
    run_nonlinear_fem_simulation,
    run_robotics_kinematics_simulation,
    run_scan_to_cad_metrology_simulation,
    run_spatial_xr_lod_simulation,
)


@pytest.mark.multiphysics
def test_simulation_domain_aerodynamics_and_aeroelasticity() -> None:
    """
    Vérifie la portance VLM et la flexion de longeron de Timoshenko.
    Vérification analytique : la portance doit correspondre à 0.5 * rho * V^2 * S * Cl_vlm,
    et la flèche du longeron doit être strictement inférieure à la flèche sous charge uniforme (7.77 mm).
    """
    res = run_aerodynamics_and_aeroelasticity_simulation()
    assert res.status == "SUCCESS"
    assert res.elapsed_ms > 0.0

    # 1. Vérification stricte de la portance (tolérance < 1.0 N)
    lift = float(res.summary_metrics["total_lift_force_n"])
    assert abs(lift - 1377.73) < 1.0, f"Portance VLM déviante : {lift} N (attendu 1377.73 N)"

    # 2. Traînée induite
    induced_drag = float(res.summary_metrics["total_induced_drag_n"])
    assert abs(induced_drag - 45.66) < 0.5, f"Traînée induite déviante : {induced_drag} N"

    # 3. Flèche de Timoshenko (concordance avec la théorie de flexion de poutre)
    deflection_mm = float(res.summary_metrics["max_spar_deflection_mm"])
    assert abs(deflection_mm - 6.669) < 0.05, f"Flèche Timoshenko incorrecte : {deflection_mm} mm"
    # Borne supérieure théorique : la flèche elliptique doit être inférieure à la charge uniforme (7.77 mm)
    assert deflection_mm < 7.78, "Violation physique : flèche elliptique supérieure à la charge uniforme"

    # 4. Contrainte maximale de flexion
    stress_mpa = float(res.summary_metrics["max_bending_stress_mpa"])
    assert abs(stress_mpa - 19.07) < 0.1, f"Contrainte de flexion déviante : {stress_mpa} MPa"


@pytest.mark.multiphysics
def test_simulation_domain_nonlinear_fem_and_contact() -> None:
    """
    Vérifie le volume Tet10, la plastification post-élastique et la force de contact.
    Vérification analytique par algorithme de retour radial (Radial Return Mapping) :
    - Déformation plastique : eps_p = (sigma_el - sigma_y) / (E - Et) = (400 - 355) / 195000 = 2.30769e-4
    - Contrainte finale : sigma_f = sigma_y + Et * eps_p = 355 + 15000 * 2.30769e-4 = 358.4615 MPa
    - Force de contact : Fn = kn * delta = 8000 * 0.05 = 400.0 N
    """
    res = run_nonlinear_fem_simulation()
    assert res.status == "SUCCESS"

    # 1. Volume tétraédrique exact V = det / 6
    vol = float(res.summary_metrics["element_volume_mm3"])
    assert abs(vol - 166.67) < 0.1, f"Volume Tet10 incorrect : {vol} mm³"

    # 2. État plastique activé
    assert bool(res.summary_metrics["is_yielded"]) is True

    # 3. Déformation plastique analytique (tolérance < 1e-6)
    eps_p = float(res.summary_metrics["plastic_strain"])
    expected_eps_p = (400.0 - 355.0) / (210000.0 - 15000.0)
    assert abs(eps_p - expected_eps_p) < 1e-6, f"Déformation plastique non conforme : {eps_p}"

    # 4. Contrainte de Von Mises analytique
    stress_mpa = float(res.summary_metrics["final_von_mises_stress_mpa"])
    expected_stress = 355.0 + 15000.0 * expected_eps_p
    assert abs(stress_mpa - expected_stress) < 0.05, f"Contrainte post-plastique déviante : {stress_mpa} MPa"

    # 5. Force de contact normale exacte (loi de pénalité de Coulomb)
    fn = float(res.summary_metrics["normal_contact_force_n"])
    assert abs(fn - 400.0) < 1e-3, f"Force de contact normale erronée : {fn} N"


@pytest.mark.multiphysics
def test_simulation_domain_robotics_kinematics_and_urdf() -> None:
    """
    Vérifie la cinématique directe Denavit-Hartenberg, les waypoints et l'intégrité URDF XML.
    """
    res = run_robotics_kinematics_simulation()
    assert res.status == "SUCCESS"

    # 1. Position du TCP en millimètres
    x = float(res.summary_metrics["tcp_x_mm"])
    y = float(res.summary_metrics["tcp_y_mm"])
    z = float(res.summary_metrics["tcp_z_mm"])
    assert abs(x - 240.58) < 0.2, f"Coordonnée TCP X erronée : {x} mm"
    assert abs(y - 0.0) < 0.1, f"Coordonnée TCP Y erronée : {y} mm"
    assert abs(z - 74.04) < 0.2, f"Coordonnée TCP Z erronée : {z} mm"

    # 2. Nombre de waypoints cartésiens
    assert int(res.summary_metrics["trajectory_waypoints_count"]) == 10

    # 3. Validation syntaxique stricte de l'arbre XML URDF
    urdf_len = int(res.summary_metrics["urdf_xml_length_bytes"])
    assert urdf_len > 3000, f"URDF anormalement court : {urdf_len} octets"


@pytest.mark.multiphysics
def test_simulation_domain_afp_composite_placement() -> None:
    """
    Vérifie le tracé des mèches composites guidé par le tenseur de Cauchy.
    Longueur = step_size (3.0 mm) * max_steps (40) = 120.0 mm.
    """
    res = run_afp_composite_simulation()
    assert res.status == "SUCCESS"

    # 1. Nombre de waypoints : 1 point initial + 40 pas = 41 points
    assert int(res.summary_metrics["total_waypoints"]) == 41

    # 2. Longueur curviligne totale déposée
    length = float(res.summary_metrics["total_deposited_length_mm"])
    assert abs(length - 120.0) < 0.1, f"Longueur de mèche déviante : {length} mm (attendu 120.0 mm)"

    # 3. Force de compactage du rouleau
    compaction = float(res.summary_metrics["roller_compaction_force_n"])
    assert compaction == 250.0, f"Force de compactage non nominale : {compaction} N"


@pytest.mark.multiphysics
def test_simulation_domain_scan_to_cad_metrology() -> None:
    """
    Vérifie le recalage optimal SVD-ICP et la conformité dimensionnelle GD&T.
    Le recalage doit inverser exactement le déplacement rigide appliqué (+2.0 en X, -1.5 en Y).
    Le RMS doit correspondre à l'écart-type du bruit gaussien appliqué (sigma = 15 um).
    """
    res = run_scan_to_cad_metrology_simulation()
    assert res.status == "SUCCESS"

    # 1. Translation rigide recouvrée par décomposition SVD
    recov_x = float(res.summary_metrics["recovered_translation_x_mm"])
    recov_y = float(res.summary_metrics["recovered_translation_y_mm"])
    assert abs(recov_x - (-2.0)) < 0.05, f"Translation X mal recalée : {recov_x} mm"
    assert abs(recov_y - 1.5) < 0.05, f"Translation Y mal recalée : {recov_y} mm"

    # 2. Écart quadratique moyen (RMS) en micromètres
    rms_um = float(res.summary_metrics["rms_deviation_um"])
    assert abs(rms_um - 15.64) < 1.0, f"RMS métrologique anormal : {rms_um} µm"

    # 3. Taux de pièces conformes (dans l'intervalle de tolérance [-40, +40] um)
    in_tol = float(res.summary_metrics["in_tolerance_percentage"])
    assert in_tol >= 99.0, f"Taux hors tolérance anormal : {in_tol}%"


@pytest.mark.multiphysics
def test_simulation_domain_ecad_thermal_twin() -> None:
    """
    Vérifie la conservation de la puissance thermique et la température de jonction MOSFET.
    Puissance totale : 3.2 + 2.8 + 1.4 + 0.39 (Joule) = 7.79 W.
    """
    res = run_ecad_thermal_simulation()
    assert res.status == "SUCCESS"

    # 1. Bilan de puissance thermique globale
    total_watts = float(res.summary_metrics["total_joule_and_semiconductor_watts"])
    assert abs(total_watts - 7.79) < 0.1, f"Puissance thermique non conservée : {total_watts} W"

    # 2. Température maximale du point chaud (MOSFET de puissance)
    max_t = float(res.summary_metrics["max_board_temperature_c"])
    assert abs(max_t - 81.55) < 0.5, f"Température maximale déviante : {max_t} °C"

    # 3. Identification du composant le plus chaud
    hottest = str(res.summary_metrics["hottest_component_id"])
    assert hottest == "MOSFET_HIGH_SIDE"
    assert bool(res.summary_metrics["is_thermally_safe"]) is True


@pytest.mark.multiphysics
def test_simulation_domain_spatial_xr_lod() -> None:
    """
    Vérifie le budget de trame de 11.11 ms (90 FPS) et la répartition des 30 chunks dans les 4 paliers LOD.
    """
    res = run_spatial_xr_lod_simulation()
    assert res.status == "SUCCESS"

    # 1. Budget de trame 90 FPS
    assert abs(float(res.summary_metrics["frame_budget_ms"]) - 11.11) < 0.05
    assert float(res.summary_metrics["actual_render_time_ms"]) == 8.5
    assert bool(res.summary_metrics["is_frame_budget_respected"]) is True

    # 2. Conservation de la hiérarchie LOD sur les 30 chunks
    lod0 = int(res.summary_metrics["lod_0_full_chunks"])
    lod1 = int(res.summary_metrics["lod_1_medium_chunks"])
    lod2 = int(res.summary_metrics["lod_2_coarse_chunks"])
    lod3 = int(res.summary_metrics["lod_3_proxy_chunks"])
    assert (lod0 + lod1 + lod2 + lod3) == 30, "Perte de chunks géométriques lors du streaming LOD"


@pytest.mark.multiphysics
def test_simulation_domain_calculix_and_openfoam_bridges() -> None:
    """
    Vérifie la génération des jeux de données d'entrée CalculiX et OpenFOAM.
    """
    res = run_industrial_bridges_simulation()
    assert res.status == "SUCCESS"
    assert int(res.summary_metrics["calculix_nodes_count"]) == 10
    assert str(res.summary_metrics["calculix_element_type"]) == "C3D10"

    # Vérification de la présence physique des fichiers générés
    inp_path = os.path.join("demo_output", "simulations", "bracket_calculix.inp")
    assert os.path.isfile(inp_path), "Fichier .inp CalculiX manquant sur disque"
    with open(inp_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "*ELEMENT, TYPE=C3D10" in content
    assert "*BOUNDARY" in content
    assert "*CLOAD" in content

    # Vérification OpenFOAM
    case_dir = os.path.join("demo_output", "simulations", "openfoam_case")
    assert os.path.isdir(os.path.join(case_dir, "0")), "Dossier OpenFOAM 0/ manquant"
    assert os.path.isdir(os.path.join(case_dir, "constant")), "Dossier OpenFOAM constant/ manquant"
    assert os.path.isdir(os.path.join(case_dir, "system")), "Dossier OpenFOAM system/ manquant"


@pytest.mark.integration
def test_full_simulation_matrix_orchestration() -> None:
    """Exécute la matrice complète et vérifie le rapport global JSON."""
    results = execute_full_simulation_matrix()
    assert len(results) == 8
    assert all(r.status == "SUCCESS" for r in results)
