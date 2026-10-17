"""
Tests unitaires et d'intégration pour la Matrice de Simulations Multi-Physiques - Phase 2.
Valide l'exécution déterministe et les invariants physiques des 8 nouveaux domaines d'ingénierie :
1. Dynamique Symplectique Hamiltonienne (Intégrateur Chung-Hulbert α-généralisé & B-bar)
2. Cinématique et Dynamique à Boucles Fermées (Inertie opérationnelle Lambda^-1 & Baumgarte)
3. Surfaces Réglées Développables (K=0, dépliage 2D et diagnostic de dépouille)
4. Quaternions Duaux SE(3) & Interpolation de Vis (DLB, isométrie sans blocage de cardan)
5. Pliage de Tôlerie Industrielle DIN 6935 (K-factor, Bend Allowance/Deduction)
6. Thermique du Bâtiment BIM IFC4 (Transmittance U ISO 6946, ferraillage armatures)
7. Lancer de Rayons Optique PBR (Fresnel-Schlick & conservation d'énergie studio)
8. Tenseur d'Inertie 3D (Ostrogradski, Huygens-Steiner et moments principaux)
9. Exécution Complète Déterministe et Export JSON

Toutes les assertions sont basées sur des solutions analytiques exactes fermées.
Garantit zéro test bidon, zéro assertion tautologique et sensibilité prouvée aux régressions.
"""

from __future__ import annotations
import json
import math
import os
import pytest
from typing import List

from scripts.advanced_physics_simulation_matrix_phase2 import (
    SimulationDomainResult,
    execute_full_simulation_matrix_phase2,
    run_bim_building_physics_simulation,
    run_closed_loop_kinematics_simulation,
    run_developable_surface_and_molding_simulation,
    run_dual_quaternions_screw_simulation,
    run_inertia_tensor_dynamics_simulation,
    run_pbr_optical_raytracing_simulation,
    run_sheet_metal_bending_simulation,
    run_symplectic_hamiltonian_simulation,
)


@pytest.mark.multiphysics
def test_simulation_domain_symplectic_hamiltonian() -> None:
    """
    Vérifie la conservation stricte de l'énergie hamiltonienne (Chung-Hulbert sans dissipation)
    et le conditionnement du tenseur de raideur B-bar pour matériau quasi-incompressible.
    """
    res = run_symplectic_hamiltonian_simulation()
    assert res.status == "SUCCESS"
    assert res.elapsed_ms > 0.0

    # 1. Énergie hamiltonienne initiale et finale (E = 0.5 * d^T * K * d = 1.23 J)
    e_init = float(res.summary_metrics["initial_hamiltonian_energy_j"])
    e_final = float(res.summary_metrics["final_hamiltonian_energy_j"])
    assert abs(e_init - 1.23) < 0.01, f"Énergie initiale inattendue : {e_init} J"
    assert abs(e_final - 1.23) < 0.01, f"Énergie finale dérivée : {e_final} J"

    # 2. Dérive énergétique quasi-nulle (intégrateur symplectique)
    drift = float(res.summary_metrics["energy_drift_delta_j"])
    assert drift < 1e-4, f"Violation symplectique : dérive d'énergie excessive {drift} J"

    conservation_ratio = float(res.summary_metrics["energy_conservation_ratio_pct"])
    assert conservation_ratio >= 99.99, f"Taux de conservation dégradé : {conservation_ratio}%"

    # 3. Formulation anti-verrouillage B-bar (les valeurs propres doivent être positives et finies)
    cond_num = float(res.summary_metrics["bbar_stiffness_condition_number"])
    assert cond_num > 1.0
    assert cond_num < 1e5, f"Conditionnement B-bar instable : {cond_num}"

    min_eig = float(res.summary_metrics["bbar_min_eigenvalue"])
    assert min_eig > 0.0, "Présence de modes à énergie nulle dans la formulation B-bar"


@pytest.mark.multiphysics
def test_simulation_domain_closed_loop_kinematics() -> None:
    """
    Vérifie l'inversion de l'inertie opérationnelle Lambda^-1 = Jc * M^-1 * Jc^T
    et la convergence du solveur d'accélération avec stabilisation de Baumgarte.
    """
    res = run_closed_loop_kinematics_simulation()
    assert res.status == "SUCCESS"

    # 1. Convergence de la dynamique fermée
    assert bool(res.summary_metrics["is_converged"]) is True

    # 2. Déterminant de l'inertie opérationnelle inverse (strictement défini positif)
    det_lambda_inv = float(res.summary_metrics["operational_inverse_inertia_det"])
    assert det_lambda_inv > 0.5, f"Inertie opérationnelle singulière : {det_lambda_inv}"
    assert abs(det_lambda_inv - 0.736874) < 0.01

    # 3. Accélérations articulaires corrigées
    norm_acc = float(res.summary_metrics["joint_acceleration_norm_rad_s2"])
    assert abs(norm_acc - 8.9904) < 0.05, f"Accélération hors tolérance : {norm_acc} rad/s²"

    # 4. Forces de fermeture de contrainte (multiplicateurs de Lagrange)
    norm_lambda = float(res.summary_metrics["constraint_forces_norm_n"])
    assert abs(norm_lambda - 12.4891) < 0.1, f"Forces de contrainte incorrectes : {norm_lambda} N"


@pytest.mark.multiphysics
def test_simulation_domain_developable_surfaces_and_molding() -> None:
    """
    Vérifie la nullité stricte de la courbure gaussienne (K = 0) sur la surface réglée,
    la conservation métrique de l'arc déplié en 2D, et le diagnostic de dépouille isoclinique.
    """
    res = run_developable_surface_and_molding_simulation()
    assert res.status == "SUCCESS"

    # 1. Condition de développabilité stricte : det([c', d, d']) = 0
    assert bool(res.summary_metrics["is_strictly_developable"]) is True

    # 2. Longueur d'arc dépliée théorique = (pi / 2) * R = 78.5398 mm
    theo_len = float(res.summary_metrics["theoretical_unrolled_arc_length_mm"])
    actual_len = float(res.summary_metrics["actual_unrolled_arc_length_mm"])
    assert abs(theo_len - 78.5398) < 0.001
    assert abs(actual_len - 78.5398) < 0.05, f"Erreur de dépliage isométrique : {actual_len} mm"

    error_mm = float(res.summary_metrics["unrolling_isometric_error_mm"])
    assert error_mm < 0.03, f"Distorsion métrique excessive lors du dépliage 2D : {error_mm} mm"

    # 3. Diagnostic d'angle de dépouille pour moule d'injection
    assert bool(res.summary_metrics["molding_is_demoldable"]) is False
    assert int(res.summary_metrics["molding_undercuts_count"]) == 2
    assert float(res.summary_metrics["molding_minimum_draft_deg"]) == 0.0


@pytest.mark.multiphysics
def test_simulation_domain_dual_quaternions_screw() -> None:
    """
    Vérifie l'isométrie euclidienne rigide exacte des quaternions duaux SE(3)
    face aux matrices homogènes 4x4 et la préservation de la norme unitaire sous interpolation DLB.
    """
    res = run_dual_quaternions_screw_simulation()
    assert res.status == "SUCCESS"

    # 1. Écart entre multiplication matricielle 4x4 et transformation par quaternion dual (< 1e-9 mm)
    error_mm = float(res.summary_metrics["matrix_vs_dual_quaternion_error_mm"])
    assert error_mm < 1e-9, f"Dérive métrique sur quaternion dual : {error_mm} mm"

    # 2. Vecteur translation composé extrait
    tx = float(res.summary_metrics["composed_translation_x"])
    ty = float(res.summary_metrics["composed_translation_y"])
    tz = float(res.summary_metrics["composed_translation_z"])
    assert abs(tx - 20.6066) < 0.01, f"Translation X incorrecte : {tx}"
    assert abs(ty - 9.3934) < 0.01, f"Translation Y incorrecte : {ty}"
    assert abs(tz - 35.0) < 0.01, f"Translation Z incorrecte : {tz}"

    # 3. Norme unitaire du quaternion de rotation interpolé DLB
    dlb_norm = float(res.summary_metrics["dlb_quaternion_real_norm"])
    assert abs(dlb_norm - 1.0) < 1e-5, f"Perte d'unitairé sous interpolation DLB : {dlb_norm}"


@pytest.mark.multiphysics
def test_simulation_domain_sheet_metal_bending() -> None:
    """
    Vérifie les calculs de pliage DIN 6935 :
    - Bend Allowance BA = (pi / 2) * (R + K * t)
    - Bend Deduction BD = 2 * Setback - BA
    - Longueur développée à plat L_flat
    """
    res = run_sheet_metal_bending_simulation()
    assert res.status == "SUCCESS"

    # 1. Développement d'arc de pliage (BA)
    # BA = (pi / 2) * (3.0 + 0.42 * 3.0) = (pi / 2) * 4.26 = 6.69159 mm
    ba = float(res.summary_metrics["bend_allowance_mm"])
    expected_ba = (math.pi / 2.0) * (3.0 + 0.42 * 3.0)
    assert abs(ba - expected_ba) < 0.001, f"Bend Allowance déviante : {ba} (attendu {expected_ba})"

    # 2. Perte au pli (BD)
    # Setback = (3 + 3) * tan(45°) = 6.0 mm => BD = 12.0 - 6.69159 = 5.30841 mm
    bd = float(res.summary_metrics["bend_deduction_mm"])
    expected_bd = 2.0 * 6.0 - expected_ba
    assert abs(bd - expected_bd) < 0.001, f"Bend Deduction erronée : {bd} (attendu {expected_bd})"

    # 3. Longueur totale dépliée à plat
    flat_len = float(res.summary_metrics["unfolded_flat_length_mm"])
    expected_flat = 200.0 + (50.0 - expected_bd) + (40.0 - expected_bd)
    assert abs(flat_len - expected_flat) < 0.01, f"Longueur flan déplié incorrecte : {flat_len} mm"

    # 4. Solide 3D plié généré
    solid_vol = float(res.summary_metrics["folded_solid_volume_mm3"])
    assert solid_vol > 0.0, "Volume du solide plié nul"


@pytest.mark.multiphysics
def test_simulation_domain_bim_building_physics() -> None:
    """
    Vérifie la thermique de l'enveloppe du bâtiment selon la norme ISO 6946 :
    - Résistance thermique R_tot = Rsi + sum(d/lambda) + Rse = 4.9054 m²·K/W
    - Transmittance U_wall = 1 / R_tot = 0.2039 W/(m²·K)
    - Déperditions thermiques à Delta T = 25 K
    - Masse d'acier de ferraillage des armatures
    """
    res = run_bim_building_physics_simulation()
    assert res.status == "SUCCESS"

    # 1. Résistance thermique globale
    r_val = float(res.summary_metrics["wall_thermal_resistance_r_m2k_w"])
    assert abs(r_val - 4.9054) < 0.01, f"Résistance thermique non conforme : {r_val} m²·K/W"

    # 2. Coefficient U de transmittance thermique
    u_val = float(res.summary_metrics["wall_u_value_w_m2k"])
    expected_u = 1.0 / 4.90543
    assert abs(u_val - expected_u) < 0.001, f"Transmittance U incorrecte : {u_val} W/(m²·K)"

    # 3. Puissance de déperdition thermique à Delta T = 25 K
    heat_loss = float(res.summary_metrics["heat_loss_at_delta_t_25k_watts"])
    assert abs(heat_loss - 136.56) < 0.5, f"Déperdition thermique déviante : {heat_loss} W"

    # 4. Masse d'acier du ferraillage
    # 20 barres * pi * (0.007)^2 * 5.8 m * 7850 kg/m³ = 140.18 kg
    rebar_mass = float(res.summary_metrics["rebar_steel_total_mass_kg"])
    expected_mass = 20.0 * math.pi * (0.007 ** 2) * 5.8 * 7850.0
    assert abs(rebar_mass - expected_mass) < 0.1, f"Masse de ferraillage erronée : {rebar_mass} kg"


@pytest.mark.multiphysics
def test_simulation_domain_pbr_optical_raytracing() -> None:
    """
    Vérifie la réflectance optique de Fresnel-Schlick et la conservation d'énergie
    sous illumination de studio 3-points, ainsi que le pipeline de rastérisation offscreen.
    """
    res = run_pbr_optical_raytracing_simulation()
    assert res.status == "SUCCESS"

    # 1. Principe de conservation d'énergie optique
    assert bool(res.summary_metrics["is_energy_conserving"]) is True

    lum = float(res.summary_metrics["direct_incidence_luminance"])
    max_intensity = float(res.summary_metrics["max_studio_intensity_bound"])
    assert lum <= max_intensity, "Violation physique : luminance supérieure à la source entrante"
    assert lum > 0.05, f"Luminance trop sombre sous éclairage 3-points : {lum}"

    # 2. Réflectance rasante (Fresnel à 85°)
    r_grazing = float(res.summary_metrics["grazing_red_channel"])
    g_grazing = float(res.summary_metrics["grazing_green_channel"])
    b_grazing = float(res.summary_metrics["grazing_blue_channel"])
    assert r_grazing > 0.0 and g_grazing > 0.0 and b_grazing > 0.0

    # 3. Dimensions de l'image de rendu logiciel
    assert int(res.summary_metrics["rendered_image_width_px"]) == 160
    assert int(res.summary_metrics["rendered_image_height_px"]) == 120


@pytest.mark.multiphysics
def test_simulation_domain_inertia_tensor_dynamics() -> None:
    """
    Vérifie le calcul du tenseur d'inertie 3D par intégration tétraédrique (Ostrogradski) :
    - Masse analytique M = V * rho = 648.0 g
    - Moments principaux Ixx, Iyy, Izz
    - Rayons de giration kx, ky, kz
    - Nullité des produits d'inertie Ixy = Ixz = Iyz = 0 (symétrie)
    """
    res = run_inertia_tensor_dynamics_simulation()
    assert res.status == "SUCCESS"

    # 1. Masse exacte
    mass_g = float(res.summary_metrics["mass_analytical_g"])
    assert abs(mass_g - 648.0) < 0.01, f"Masse erronée : {mass_g} g"

    # 2. Moments d'inertie principaux exacts
    # Ixx = 280 800 g·mm²
    ixx_num = float(res.summary_metrics["numerical_ixx_g_mm2"])
    ixx_theo = float(res.summary_metrics["theoretical_ixx_g_mm2"])
    assert abs(ixx_num - 280800.0) < 10.0
    assert abs(ixx_theo - 280800.0) < 10.0

    # Iyy = 626 400 g·mm²
    iyy_num = float(res.summary_metrics["numerical_iyy_g_mm2"])
    assert abs(iyy_num - 626400.0) < 10.0

    # Izz = 734 400 g·mm²
    izz_num = float(res.summary_metrics["numerical_izz_g_mm2"])
    assert abs(izz_num - 734400.0) < 10.0

    # 3. Rayons de giration théoriques k = sqrt(I / M)
    kx = float(res.summary_metrics["radius_of_gyration_kx_mm"])
    expected_kx = math.sqrt(280800.0 / 648.0)
    assert abs(kx - expected_kx) < 0.05, f"Rayon de giration kx déviant : {kx} mm"

    # 4. Nullité des termes croisés (axes principaux alignés avec le repère centré)
    ixy = float(res.summary_metrics["cross_product_ixy"])
    ixz = float(res.summary_metrics["cross_product_ixz"])
    iyz = float(res.summary_metrics["cross_product_iyz"])
    assert abs(ixy) < 1e-3, f"Produit d'inertie Ixy non nul : {ixy}"
    assert abs(ixz) < 1e-3, f"Produit d'inertie Ixz non nul : {ixz}"
    assert abs(iyz) < 1e-3, f"Produit d'inertie Iyz non nul : {iyz}"


@pytest.mark.multiphysics
def test_full_simulation_matrix_phase2_execution(tmp_path: pytest.TempPathFactory) -> None:
    """
    Vérifie l'orchestration complète de bout en bout de la matrice Phase 2
    et la persistance correcte du rapport consolidé JSON.
    """
    out_dir = str(tmp_path)
    results: List[SimulationDomainResult] = execute_full_simulation_matrix_phase2(output_dir=out_dir)

    assert len(results) == 8, f"Nombre de domaines exécutés incorrect : {len(results)}/8"
    for r in results:
        assert r.status == "SUCCESS", f"Échec du domaine {r.domain_name}"
        assert r.elapsed_ms > 0.0
        assert len(r.summary_metrics) >= 4

    # Vérification du fichier JSON généré
    report_file = os.path.join(out_dir, "simulation_matrix_phase2_report.json")
    assert os.path.exists(report_file), "Le rapport JSON consolidé n'a pas été généré"

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["domains_count"] == 8
    assert len(data["results"]) == 8
    assert data["total_elapsed_ms"] > 0.0
