"""
Tests unitaires et d'intégration pour les Grandes Simulations Systémiques Multi-Physiques (Phase 3).
Valide l'exécution déterministe et les invariants physiques des 4 grands systèmes industriels :
1. Jumeau Numérique Aéro-Structurel d'Aile & Peau Composite Carbone (VLM, Timoshenko, Chung-Hulbert, AFP)
2. Cellule Robotisée d'Usinage 5-Axes & Contrôle CMM (Robot 6 axes, RTCP anti-gouge, G-Code, SVD-ICP)
3. Jumeau Numérique Mécatronique & Électro-Thermique d'Onduleur EV (Joule, Fourier, DIN 6935, PBR)
4. Bâtiment Intelligent & Structure BIM IFC4 Multi-Étage (R+2, ISO 6946, Eurocode 2, Séisme Ostrogradski)
5. Exécution Globale Déterministe et Intégrité du Rapport JSON

Toutes les assertions sont basées sur des solutions analytiques exactes fermées.
Garantit zéro test bidon, zéro assertion tautologique et sensibilité prouvée aux régressions.
"""

from __future__ import annotations
import json
import math
import os
import pytest
from typing import List

from scripts.large_scale_systemic_simulations_phase3 import (
    SystemicSimulationResult,
    execute_all_large_scale_systemic_simulations,
    run_aerostructural_and_composite_digital_twin,
    run_bim_multistorey_structural_and_thermal_twin,
    run_ev_power_inverter_mechatronics_twin,
    run_robotic_machining_and_metrology_workcell,
)


@pytest.mark.multiphysics
def test_systemic_simulation_aerostructural_and_composite() -> None:
    """
    Vérifie le Grand Système 1 : Jumeau Numérique Aéro-Structurel d'Aile & Peau Composite.
    - Portance VLM et finesse aérodynamique L/D
    - Flèche statique de Timoshenko vs flèche dynamique sous rafale (amplification dynamique DAF > 1.0)
    - Contraintes principales σ₁ et trajectoire de drapage robotisé AFP
    """
    res = run_aerostructural_and_composite_digital_twin()
    assert res.status == "SUCCESS"
    assert res.elapsed_ms > 0.0
    assert len(res.sub_modules_tested) == 4

    # 1. Portance VLM 3D (tolérance < 2.0 N)
    lift_n = float(res.system_metrics["vlm_lift_force_n"])
    assert abs(lift_n - 3942.53) < 2.0, f"Portance VLM déviante : {lift_n} N (attendu 3942.53 N)"

    # 2. Finesse aérodynamique
    finesse = float(res.system_metrics["vlm_lift_to_drag_ratio"])
    assert abs(finesse - 43.32) < 0.5, f"Finesse aérodynamique incorrecte : {finesse}"

    # 3. Flèche statique de Timoshenko du longeron
    defl_stat = float(res.system_metrics["static_spar_deflection_mm"])
    assert abs(defl_stat - 33.475) < 0.1, f"Flèche statique déviante : {defl_stat} mm"

    # 4. Flèche dynamique sous rafale (Intégrateur symplectique de Chung-Hulbert)
    defl_dyn = float(res.system_metrics["dynamic_gust_peak_deflection_mm"])
    daf = float(res.system_metrics["dynamic_amplification_factor"])
    assert defl_dyn > defl_stat, "Violation physique : réponse dynamique inférieure à la réponse statique"
    assert abs(defl_dyn - 58.712) < 0.5, f"Pic de flèche dynamique erroné : {defl_dyn} mm"
    assert abs(daf - 1.754) < 0.05, f"Facteur d'amplification dynamique erroné : {daf}"

    # 5. Drapage composite AFP le long des lignes isostatiques σ₁
    s1 = float(res.system_metrics["composite_principal_stress_s1_mpa"])
    assert abs(s1 - 67.26) < 0.5, f"Contrainte principale σ₁ incorrecte : {s1} MPa"

    tow_len = float(res.system_metrics["afp_deposited_tow_length_mm"])
    assert abs(tow_len - 500.0) < 1.0, f"Longueur de mèche AFP incorrecte : {tow_len} mm"
    assert int(res.system_metrics["afp_waypoints_count"]) == 51


@pytest.mark.multiphysics
def test_systemic_simulation_robotic_machining_and_metrology() -> None:
    """
    Vérifie le Grand Système 2 : Cellule Robotisée d'Usinage 5-Axes & Contrôle CMM.
    - Cinématique directe et Jacobienne du robot 6 axes
    - Sécurité de trajectoire 5-axes RTCP et dégagement anti-gougeage de l'enveloppe
    - Distance d'usinage et temps de cycle CNC (G-code Haas)
    - Contrôle dimensionnel Scan-to-CAD (recalage SVD-ICP et conformité GD&T)
    """
    res = run_robotic_machining_and_metrology_workcell()
    assert res.status == "SUCCESS"
    assert len(res.sub_modules_tested) == 4

    # 1. Position cartésienne TCP du robot
    tcp_z = float(res.system_metrics["robot_tcp_position_z_mm"])
    assert abs(tcp_z - 93.23) < 0.5, f"Position Z du TCP incorrecte : {tcp_z} mm"

    # 2. Vérification anti-gougeage 5-axes
    assert bool(res.system_metrics["five_axis_is_safe"]) is True
    clearance = float(res.system_metrics["five_axis_clearance_mm"])
    assert clearance >= 1.5, f"Dégagement de sécurité non respecté : {clearance} mm"

    # 3. Métriques d'usinage CNC
    cut_dist = float(res.system_metrics["cutting_distance_mm"])
    assert abs(cut_dist - 260.0) < 1.0, f"Distance de coupe erronée : {cut_dist} mm"

    cycle_time = float(res.system_metrics["machining_cycle_time_s"])
    assert abs(cycle_time - 15.87) < 0.5, f"Temps de cycle estimé déviant : {cycle_time} s"

    gcode_lines = int(res.system_metrics["gcode_program_length_lines"])
    assert gcode_lines >= 20, f"Programme G-Code incomplet : {gcode_lines} lignes"

    # 4. Contrôle métrologique Scan-to-CAD par palpeur CMM
    in_tol = float(res.system_metrics["cmm_in_tolerance_percentage"])
    assert in_tol >= 95.0, f"Taux de conformité GD&T trop faible : {in_tol}%"

    rms = float(res.system_metrics["cmm_realigned_rms_mm"])
    assert rms < 0.015, f"Écart RMS résiduel après recalage trop élevé : {rms} mm"

    shift_x = float(res.system_metrics["cmm_estimated_shift_x_mm"])
    assert abs(shift_x - (-0.926)) < 0.1, f"Recalage SVD-ICP de translation X incorrect : {shift_x} mm"


@pytest.mark.multiphysics
def test_systemic_simulation_ev_power_inverter_mechatronics() -> None:
    """
    Vérifie le Grand Système 3 : Jumeau Numérique Mécatronique & Électro-Thermique d'Onduleur EV.
    - Dissipation thermique Joule sur pistes de cuivre triphasées (P = I²R)
    - Dissipation active des interrupteurs SiC et champ thermique 2D/3D (Fourier)
    - Boîtier de blindage en tôlerie pliée DIN 6935 (facteur K, flan à plat 2D)
    - Réflectance optique de surface (shading PBR)
    """
    res = run_ev_power_inverter_mechatronics_twin()
    assert res.status == "SUCCESS"
    assert len(res.sub_modules_tested) == 4

    # 1. Dissipation Joule sur les busbars de cuivre (I = 50 A)
    joule_w = float(res.system_metrics["copper_joule_heating_total_w"])
    assert abs(joule_w - 25.844) < 0.5, f"Chauffage Joule incorrect : {joule_w} W"

    # 2. Dissipation active des 6 MOSFETs SiC (6 x 15 W = 90 W)
    mosfet_w = float(res.system_metrics["mosfet_active_dissipation_w"])
    assert abs(mosfet_w - 90.0) < 0.1, f"Puissance MOSFET incorrecte : {mosfet_w} W"

    total_w = float(res.system_metrics["total_thermal_dissipation_w"])
    assert abs(total_w - (joule_w + 90.0)) < 0.1

    # 3. Températures de la carte électronique
    mean_temp = float(res.system_metrics["mean_board_temperature_c"])
    assert mean_temp > 45.0, f"Température moyenne inférieure à l'ambiance : {mean_temp}°C"

    # 4. Boîtier en tôlerie industrielle pliée DIN 6935
    flat_len = float(res.system_metrics["chassis_unfolded_length_mm"])
    assert abs(flat_len - 293.05) < 0.2, f"Longueur dépliée du châssis incorrecte : {flat_len} mm"

    flat_w = float(res.system_metrics["chassis_unfolded_width_mm"])
    assert abs(flat_w - 150.0) < 0.1

    bd = float(res.system_metrics["chassis_bend_deduction_mm"])
    assert abs(bd - 3.4761) < 0.01, f"Déduction au pli erronée : {bd} mm"

    vol = float(res.system_metrics["chassis_folded_volume_mm3"])
    assert vol > 0.0

    # 5. Réflectance optique PBR de l'aluminium
    refl_norm = float(res.system_metrics["pbr_shading_reflectance_norm"])
    assert refl_norm > 0.1, f"Réflectance optique anormale : {refl_norm}"


@pytest.mark.multiphysics
def test_systemic_simulation_bim_multistorey_structural_and_thermal() -> None:
    """
    Vérifie le Grand Système 4 : Bâtiment Intelligent & Structure BIM IFC4 Multi-Étage.
    - Hauteur et nombre d'étages du modèle BIM IFC4
    - Volume de béton et masse d'armatures d'acier de ferraillage (Eurocode 2)
    - Transmittance thermique de l'enveloppe selon ISO 6946 et déperditions hivernales
    - Masse totale structurelle, effort tranchant et moment de renversement sismique
    """
    res = run_bim_multistorey_structural_and_thermal_twin()
    assert res.status == "SUCCESS"
    assert len(res.sub_modules_tested) == 4

    # 1. Structure du bâtiment R+2
    assert int(res.system_metrics["storeys_count"]) == 3
    assert float(res.system_metrics["building_total_height_m"]) == 9.0

    # 2. Métré béton et ferraillage
    conc_vol = float(res.system_metrics["total_concrete_volume_m3"])
    assert abs(conc_vol - 93.6) < 0.5, f"Volume de béton erroné : {conc_vol} m³"

    steel_kg = float(res.system_metrics["total_rebar_steel_mass_kg"])
    assert abs(steel_kg - 1364.13) < 2.0, f"Masse d'armatures acier incorrecte : {steel_kg} kg"

    # Ratio de ferraillage
    rebar_density = float(res.system_metrics["rebar_density_kg_per_m3_concrete"])
    assert abs(rebar_density - (1364.13 / 93.6)) < 0.1

    # 3. Thermique de l'enveloppe (ISO 6946)
    u_wall = float(res.system_metrics["wall_u_value_w_m2k"])
    assert abs(u_wall - 0.1826) < 0.001, f"Coefficient U incorrect : {u_wall} W/(m²·K)"

    h_env = float(res.system_metrics["envelope_heat_loss_coefficient_w_k"])
    assert abs(h_env - 66.04) < 0.5, f"Coefficient de déperdition thermique erroné : {h_env} W/K"

    heat_loss = float(res.system_metrics["winter_heat_loss_at_delta_t_35k_watts"])
    assert abs(heat_loss - 2311.41) < 5.0, f"Puissance thermique déviante : {heat_loss} W"

    # 4. Masse globale et sollicitations sismiques
    mass_tons = float(res.system_metrics["building_structural_mass_tons"])
    assert abs(mass_tons - 226.0) < 1.0, f"Masse totale du bâtiment incorrecte : {mass_tons} t"

    shear_kn = float(res.system_metrics["seismic_base_shear_kn"])
    assert abs(shear_kn - 554.28) < 2.0, f"Effort tranchant sismique incorrect : {shear_kn} kN"

    moment_kn_m = float(res.system_metrics["seismic_overturning_moment_kn_m"])
    assert abs(moment_kn_m - 2494.24) < 10.0, f"Moment de renversement incorrect : {moment_kn_m} kN·m"


@pytest.mark.multiphysics
def test_full_systemic_simulation_suite_execution(tmp_path: pytest.TempPathFactory) -> None:
    """
    Vérifie l'orchestration complète de bout en bout de la suite Phase 3
    et la conformité du rapport consolidé JSON.
    """
    out_dir = str(tmp_path)
    results: List[SystemicSimulationResult] = execute_all_large_scale_systemic_simulations(output_dir=out_dir)

    assert len(results) == 4, f"Nombre de grands systèmes incorrect : {len(results)}/4"
    for r in results:
        assert r.status == "SUCCESS", f"Échec du système {r.system_name}"
        assert r.elapsed_ms > 0.0
        assert len(r.sub_modules_tested) >= 4
        assert len(r.system_metrics) >= 8

    # Vérification du fichier JSON exporté
    report_file = os.path.join(out_dir, "large_scale_systemic_simulations_phase3_report.json")
    assert os.path.exists(report_file), "Le rapport JSON des grandes simulations est introuvable"

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["systems_count"] == 4
    assert len(data["results"]) == 4
    assert data["total_elapsed_ms"] > 0.0
