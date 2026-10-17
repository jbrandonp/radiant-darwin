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
"""

from __future__ import annotations
import os
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
    """Vérifie la portance VLM et la flexion de longeron de Timoshenko."""
    res = run_aerodynamics_and_aeroelasticity_simulation()
    assert res.status == "SUCCESS"
    assert res.elapsed_ms > 0.0
    assert float(res.summary_metrics["total_lift_force_n"]) > 500.0
    assert float(res.summary_metrics["max_spar_deflection_mm"]) > 0.0
    assert float(res.summary_metrics["max_spar_deflection_mm"]) < 50.0
    assert float(res.summary_metrics["max_bending_stress_mpa"]) > 5.0


@pytest.mark.multiphysics
def test_simulation_domain_nonlinear_fem_and_contact() -> None:
    """Vérifie le volume Tet10, la plastification post-élastique et la force de contact."""
    res = run_nonlinear_fem_simulation()
    assert res.status == "SUCCESS"
    assert float(res.summary_metrics["element_volume_mm3"]) > 0.0
    assert bool(res.summary_metrics["is_yielded"]) is True
    assert float(res.summary_metrics["plastic_strain"]) > 0.0
    assert float(res.summary_metrics["normal_contact_force_n"]) == 400.0


@pytest.mark.multiphysics
def test_simulation_domain_robotics_kinematics_and_urdf() -> None:
    """Vérifie la cinématique directe, les waypoints et l'export URDF."""
    res = run_robotics_kinematics_simulation()
    assert res.status == "SUCCESS"
    assert int(res.summary_metrics["trajectory_waypoints_count"]) == 10
    assert int(res.summary_metrics["urdf_xml_length_bytes"]) > 1000
    assert float(res.summary_metrics["tcp_z_mm"]) > 0.0


@pytest.mark.multiphysics
def test_simulation_domain_afp_composite_placement() -> None:
    """Vérifie le tracé des fibres continues et les paramètres de dépose."""
    res = run_afp_composite_simulation()
    assert res.status == "SUCCESS"
    assert int(res.summary_metrics["total_waypoints"]) >= 20
    assert float(res.summary_metrics["total_deposited_length_mm"]) > 50.0
    assert float(res.summary_metrics["roller_compaction_force_n"]) == 250.0


@pytest.mark.multiphysics
def test_simulation_domain_scan_to_cad_metrology() -> None:
    """Vérifie le recalage optimal SVD-ICP et la conformité GD&T."""
    res = run_scan_to_cad_metrology_simulation()
    assert res.status == "SUCCESS"
    assert int(res.summary_metrics["measured_points_count"]) == 225
    assert float(res.summary_metrics["in_tolerance_percentage"]) >= 95.0
    assert float(res.summary_metrics["rms_deviation_um"]) < 30.0


@pytest.mark.multiphysics
def test_simulation_domain_ecad_thermal_twin() -> None:
    """Vérifie la résolution de Fourier et la détection du point chaud MOSFET."""
    res = run_ecad_thermal_simulation()
    assert res.status == "SUCCESS"
    assert float(res.summary_metrics["max_board_temperature_c"]) > 30.0
    assert float(res.summary_metrics["max_board_temperature_c"]) < 120.0
    assert str(res.summary_metrics["hottest_component_id"]) == "MOSFET_HIGH_SIDE"
    assert bool(res.summary_metrics["is_thermally_safe"]) is True


@pytest.mark.multiphysics
def test_simulation_domain_spatial_xr_lod() -> None:
    """Vérifie le budget de trame à 90 FPS et la distribution LOD."""
    res = run_spatial_xr_lod_simulation()
    assert res.status == "SUCCESS"
    assert bool(res.summary_metrics["is_frame_budget_respected"]) is True
    assert int(res.summary_metrics["total_triangles_rendered"]) > 0


@pytest.mark.multiphysics
def test_simulation_domain_calculix_and_openfoam_bridges() -> None:
    """Vérifie la génération des jeux de données d'entrée CalculiX et OpenFOAM."""
    res = run_industrial_bridges_simulation()
    assert res.status == "SUCCESS"
    assert int(res.summary_metrics["calculix_nodes_count"]) == 10
    assert str(res.summary_metrics["calculix_element_type"]) == "C3D10"
    assert str(res.summary_metrics["openfoam_fluid"]) == "air"
    assert float(res.summary_metrics["openfoam_inlet_speed_m_s"]) > 30.0


@pytest.mark.integration
def test_full_simulation_matrix_orchestration() -> None:
    """Exécute la matrice complète et vérifie le rapport global JSON."""
    results = execute_full_simulation_matrix()
    assert len(results) == 8
    assert all(r.status == "SUCCESS" for r in results)
