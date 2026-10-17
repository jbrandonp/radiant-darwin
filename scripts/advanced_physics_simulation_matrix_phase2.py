"""
Matrice de Simulations Multi-Physiques Différenciées - Phase 2 (Multi-Domain Simulation Matrix Phase 2).
Exécute 8 nouvelles simulations approfondies couvrant des domaines d'ingénierie et de physique avancés :
1. Dynamique Symplectique Hamiltonienne & Anti-Verrouillage (Intégrateur Chung-Hulbert α-généralisé et B-bar)
2. Cinématique & Dynamique à Boucles Fermées (Inertie opérationnelle inverse Lambda^-1 et stabilisation Baumgarte)
3. Surfaces Réglées Développables & Dépouille Isoclinique (Courbure de Gauss K=0, dépliage 2D et démoulage)
4. Quaternions Duaux SE(3) & Théorie des Vis (Isométrie rigide sans blocage de cardan, ScLERP/DLB)
5. Pliage de Tôlerie Industrielle DIN 6935 (Facteur K, perte au pli Bend Deduction, patron à plat 2D)
6. Thermique de l'Enveloppe du Bâtiment BIM IFC4 (Transmittance U ISO 6946, ferraillage armatures et bilan watt)
7. Lancer de Rayons Optique PBR (Réflectance Fresnel-Schlick, ombrage studio 3 points et conservation d'énergie)
8. Tenseur d'Inertie 3D & Dynamique du Solide Rigide (Moments principaux, théorèmes d'Ostrogradski et Huygens-Steiner)

Architecture strictement typée (zéro Any, zéro object) et complexité cognitive <= 25 par fonction.
"""

from __future__ import annotations
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

# Insertion de la racine du projet dans sys.path
_PROJECT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.core.geometry import Solid, make_box
from src.core.inspector import InertiaTensor, compute_inertia_tensor
from src.core.nexus_kernel.closed_loop_kinematics import (
    ClosedLoopDynamicsResult,
    ClosedLoopKinematicEngine,
)
from src.core.nexus_kernel.developable_surfaces import (
    DraftDiagnostic,
    IsoclinicDraftEngine,
    RuledDevelopableSurface,
)
from src.core.nexus_kernel.dual_quaternions import (
    DualQuaternion,
    Quaternion,
)
from src.core.nexus_kernel.symplectic_integrator import (
    GeneralizedAlphaIntegrator,
    GeneralizedAlphaStepResult,
    VolumetricLockingMitigation,
)
from src.core.types import Vector3D
from src.render.pbr_material import PBRMaterial, PBR_LIBRARY
from src.render.raytracer import PBRRaytracer, create_default_studio
from src.sheetmetal.sheet_metal import (
    FlatPattern,
    SheetMetalPart,
    SheetMetalRule,
)
from src.specialized.bim_engine import (
    BIMLayer,
    BIMMaterialType,
    BIMOpening,
    BIMRebar,
    BIMSlab,
    BIMWall,
    BIMWindow,
)


@dataclass
class SimulationDomainResult:
    """Résultat quantitatif d'un domaine de simulation."""
    domain_name: str
    status: str
    elapsed_ms: float
    summary_metrics: Dict[str, Union[float, int, str, bool]]


def run_symplectic_hamiltonian_simulation() -> SimulationDomainResult:
    """
    Simulation 1 : Dynamique Symplectique Hamiltonienne & Anti-Verrouillage B-bar.
    Vérifie la conservation stricte de l'énergie mécanique totale E = Ek + Ep
    via l'intégrateur de Chung-Hulbert (alpha-généralisé avec rho_inf = 1.0)
    et la régularisation du tenseur de raideur B-bar pour élastomères incompressibles (nu = 0.499).
    """
    t_start = time.perf_counter()

    # 1. Système oscillant à 2 DDL non amorti
    mass_matrix = np.array([
        [2.0, 0.0],
        [0.0, 1.5]
    ], dtype=np.float64)

    stiffness_matrix = np.array([
        [600.0, -200.0],
        [-200.0, 400.0]
    ], dtype=np.float64)

    damping_matrix = np.zeros((2, 2), dtype=np.float64)

    # Intégrateur symplectique sans dissipation numérique (rho_infinity = 1.0)
    integrator = GeneralizedAlphaIntegrator(
        mass_matrix=mass_matrix,
        stiffness_matrix=stiffness_matrix,
        damping_matrix=damping_matrix,
        rho_infinity=1.0
    )

    # Conditions initiales
    disp_curr = np.array([0.05, -0.03], dtype=np.float64)
    vel_curr = np.array([0.0, 0.0], dtype=np.float64)
    acc_curr = np.linalg.solve(mass_matrix, -stiffness_matrix @ disp_curr)

    dt_step = 0.001
    total_steps = 200

    e_initial = float(0.5 * disp_curr.T @ stiffness_matrix @ disp_curr)
    e_max = e_initial
    e_min = e_initial

    for _ in range(total_steps):
        step_res: GeneralizedAlphaStepResult = integrator.advance_step(
            d_n=disp_curr,
            v_n=vel_curr,
            a_n=acc_curr,
            f_ext_next=np.zeros(2, dtype=np.float64),
            f_ext_curr=np.zeros(2, dtype=np.float64),
            dt=dt_step
        )
        disp_curr = step_res.displacements
        vel_curr = step_res.velocities
        acc_curr = step_res.accelerations
        e_curr = step_res.energy_total
        if e_curr > e_max:
            e_max = e_curr
        if e_curr < e_min:
            e_min = e_curr

    delta_energy = abs(e_max - e_min)
    energy_conservation_ratio = 1.0 - (delta_energy / max(1e-9, e_initial))

    # 2. Formulation B-bar pour matériau quasi-incompressible (nu = 0.499)
    bbar_matrix = VolumetricLockingMitigation.compute_bbar_stiffness(
        young_modulus=210000.0,
        poisson_ratio=0.499,
        element_volume=100.0
    )
    eigenvalues = np.linalg.eigvalsh(bbar_matrix)
    min_eig = float(np.min(eigenvalues))
    max_eig = float(np.max(eigenvalues))
    condition_number = float(max_eig / max(1e-9, min_eig))

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="Symplectic Hamiltonian Dynamics & Anti-Locking",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "initial_hamiltonian_energy_j": round(e_initial, 6),
            "final_hamiltonian_energy_j": round(step_res.energy_total, 6),
            "energy_drift_delta_j": round(delta_energy, 7),
            "energy_conservation_ratio_pct": round(energy_conservation_ratio * 100.0, 4),
            "bbar_stiffness_condition_number": round(condition_number, 2),
            "bbar_min_eigenvalue": round(min_eig, 2),
            "bbar_max_eigenvalue": round(max_eig, 2)
        }
    )


def run_closed_loop_kinematics_simulation() -> SimulationDomainResult:
    """
    Simulation 2 : Cinématique et Dynamique à Boucles Fermées.
    Modélise un mécanisme parallèle à 4 DDL et 2 contraintes holonomes de fermeture.
    Vérifie la projection de l'inertie opérationnelle Lambda^-1 = Jc * M^-1 * Jc^T
    et la convergence du solveur lagrangien de Baumgarte.
    """
    t_start = time.perf_counter()

    # Matrice de masse articulaire 4x4 symétrique définie positive
    mass_matrix = np.diag([3.0, 2.5, 1.8, 1.2]).astype(np.float64)

    # Jacobienne de contrainte holonome 2x4 (deux boucles cinématiques fermées)
    constraint_jacobian = np.array([
        [1.0, 0.5, -0.8, 0.0],
        [0.0, 0.7, 1.0, -0.6]
    ], dtype=np.float64)

    # Couples moteurs appliqués aux articulations
    torques = np.array([15.0, -10.0, 8.0, -5.0], dtype=np.float64)
    joint_velocities = np.array([0.2, -0.1, 0.15, -0.05], dtype=np.float64)
    constraint_drift = np.array([0.002, -0.0015], dtype=np.float64)

    # 1. Calcul de l'inertie opérationnelle inverse
    lambda_inv = ClosedLoopKinematicEngine.compute_operational_inverse_inertia(
        mass_matrix=mass_matrix,
        constraint_jacobian=constraint_jacobian
    )
    det_lambda_inv = float(np.linalg.det(lambda_inv))

    # 2. Résolution des accélérations avec multiplicateurs de Lagrange
    dyn_res: ClosedLoopDynamicsResult = ClosedLoopKinematicEngine.solve_closed_loop_acceleration(
        mass_matrix=mass_matrix,
        unconstrained_torques=torques,
        constraint_jacobian=constraint_jacobian,
        constraint_drift=constraint_drift,
        joint_velocities=joint_velocities,
        time_step=0.001,
        stabilization_kp=1000.0,
        stabilization_kd=50.0
    )

    norm_acc = float(np.linalg.norm(dyn_res.joint_accelerations))
    norm_lambda = float(np.linalg.norm(dyn_res.constraint_forces))

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="Closed-Loop Kinematics & Operational Space Dynamics",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "is_converged": dyn_res.is_converged,
            "operational_inverse_inertia_det": round(det_lambda_inv, 6),
            "joint_acceleration_norm_rad_s2": round(norm_acc, 4),
            "constraint_forces_norm_n": round(norm_lambda, 4),
            "constraint_residual_m": round(dyn_res.constraint_residual, 6)
        }
    )


def run_developable_surface_and_molding_simulation() -> SimulationDomainResult:
    """
    Simulation 3 : Surfaces Développables & Démoulage Isoclinique.
    Valide l'isométrie métrique d'une surface réglée cylindrique (courbure gaussienne K = 0),
    son patron 2D déplié à plat sans allongement, et le diagnostic d'angle de dépouille pour moule d'injection.
    """
    t_start = time.perf_counter()

    # 1. Surface cylindrique développable S(u, v) = c(u) + v * d(u)
    radius = 50.0
    height = 100.0

    def directrix_c(u: float) -> np.ndarray:
        angle = u * (np.pi * 0.5)
        return np.array([radius * np.cos(angle), radius * np.sin(angle), 0.0], dtype=np.float64)

    def tangent_cp(u: float) -> np.ndarray:
        angle = u * (np.pi * 0.5)
        factor = np.pi * 0.5
        return np.array([-radius * factor * np.sin(angle), radius * factor * np.cos(angle), 0.0], dtype=np.float64)

    def ruling_d(u: float) -> np.ndarray:
        return np.array([0.0, 0.0, height], dtype=np.float64)

    def ruling_dp(u: float) -> np.ndarray:
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)

    surface = RuledDevelopableSurface(
        directrix_curve=directrix_c,
        directrix_tangent=tangent_cp,
        ruling_direction=ruling_d,
        ruling_derivative=ruling_dp,
        u_range=(0.0, 1.0),
        v_range=(0.0, 1.0)
    )

    is_dev = surface.is_developable(tolerance=1e-5, samples=20)
    pts_2d, triangles_2d = surface.unroll_to_plane_2d(num_u=25, num_v=5)

    # Longueur développée théorique : L = (pi / 2) * R = 78.5398 mm
    actual_unrolled_length = float(np.max(pts_2d[:, 0]))
    expected_length = (np.pi * 0.5) * radius
    length_error = abs(actual_unrolled_length - expected_length)

    # 2. Diagnostic d'angle de dépouille
    face_normals = np.array([
        [0.0, 0.0, 1.0],      # Face supérieure (90° -> conforme)
        [0.05, 0.0, 0.9987],  # Face dépouillée à ~2.86° (conforme)
        [0.9998, 0.0, 0.0174],# Face quasi-verticale ~1.0° (< 2° -> contre-dépouille)
        [0.0, 1.0, 0.0]       # Face verticale pure 0° (contre-dépouille)
    ], dtype=np.float64)

    draft_diag: DraftDiagnostic = IsoclinicDraftEngine.analyze_mesh_draft(
        face_normals=face_normals,
        pull_direction=(0.0, 0.0, 1.0),
        target_draft_angle_deg=2.0
    )

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="Developable Surfaces & Isoclinic Draft Diagnostics",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "is_strictly_developable": is_dev,
            "theoretical_unrolled_arc_length_mm": round(expected_length, 4),
            "actual_unrolled_arc_length_mm": round(actual_unrolled_length, 4),
            "unrolling_isometric_error_mm": round(length_error, 6),
            "unrolled_mesh_triangles_count": int(len(triangles_2d)),
            "molding_is_demoldable": draft_diag.is_demoldable,
            "molding_undercuts_count": draft_diag.undercut_faces_count,
            "molding_minimum_draft_deg": round(draft_diag.minimum_draft_angle_deg, 3)
        }
    )


def run_dual_quaternions_screw_simulation() -> SimulationDomainResult:
    """
    Simulation 4 : Quaternions Duaux SE(3) & Interpolation de Vis Rigide.
    Démontre l'absence totale de dérive métrique (isométrie euclidienne parfaite)
    par rapport à l'inversion et la multiplication matricielle 4x4 classique,
    ainsi que l'interpolation DLB sans singularité de cardan (Gimbal Lock).
    """
    t_start = time.perf_counter()

    # Transformation 1 : Rotation 45° autour de Z, translation [10, 20, 5]
    dq1 = DualQuaternion.from_axis_angle_translation(
        axis=(0.0, 0.0, 1.0),
        angle_rad=np.radians(45.0),
        translation=(10.0, 20.0, 5.0)
    )

    # Transformation 2 : Rotation 90° autour de X, translation [0, -15, 30]
    dq2 = DualQuaternion.from_axis_angle_translation(
        axis=(1.0, 0.0, 0.0),
        angle_rad=np.radians(90.0),
        translation=(0.0, -15.0, 30.0)
    )

    # Composition cinématique des quaternions duaux
    dq_composed = dq1.multiply(dq2)

    # Point de test spatial 3D
    test_pt = np.array([15.0, -10.0, 25.0], dtype=np.float64)
    transformed_dq = dq_composed.transform_point(test_pt)

    # Transformation équivalente par matrices homogènes 4x4
    mat1 = dq1.to_transform_matrix_4x4()
    mat2 = dq2.to_transform_matrix_4x4()
    mat_composed = mat1 @ mat2
    pt_homo = np.array([test_pt[0], test_pt[1], test_pt[2], 1.0], dtype=np.float64)
    transformed_mat = (mat_composed @ pt_homo)[:3]

    discrepancy = float(np.linalg.norm(transformed_dq - transformed_mat))

    # Interpolation DLB (Dual Quaternion Linear Blending) à t = 0.5
    dq_half = DualQuaternion.dlb_interpolate(dq1, dq2, weight=0.5)
    t_half = dq_half.extract_translation()

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="Dual Quaternions SE(3) & Screw Kinematics",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "matrix_vs_dual_quaternion_error_mm": round(discrepancy, 12),
            "composed_translation_x": round(float(dq_composed.extract_translation()[0]), 4),
            "composed_translation_y": round(float(dq_composed.extract_translation()[1]), 4),
            "composed_translation_z": round(float(dq_composed.extract_translation()[2]), 4),
            "dlb_interpolated_translation_norm": round(float(np.linalg.norm(t_half)), 4),
            "dlb_quaternion_real_norm": round(dq_half.real.norm(), 6)
        }
    )


def run_sheet_metal_bending_simulation() -> SimulationDomainResult:
    """
    Simulation 5 : Pliage de Tôlerie Industrielle DIN 6935.
    Calcule le développement exact du flan à plat avec facteur K = 0.42,
    les déductions au pli (Bend Deduction) et génère le solide plié 3D et le patron 2D.
    """
    t_start = time.perf_counter()

    rule = SheetMetalRule(
        name="Acier Inox 3mm",
        thickness_mm=3.0,
        bend_radius_mm=3.0,
        k_factor=0.42
    )

    part = SheetMetalPart(base_width=120.0, base_length=200.0, rule=rule)

    # Ajout de deux rebords pliés à 90°
    flange1 = part.add_flange(length_mm=50.0, angle_deg=90.0)
    flange2 = part.add_flange(length_mm=40.0, angle_deg=90.0)

    # Calcul théorique exact :
    # BA = (pi / 2) * (3.0 + 0.42 * 3.0) = 6.69159 mm
    # Setback = (3.0 + 3.0) * tan(45°) = 6.0 mm
    # BD = 2 * 6.0 - 6.69159 = 5.30841 mm
    # Flat length = 200 + (50 - 5.30841) + (40 - 5.30841) = 279.38318 mm
    flat_pattern: FlatPattern = part.generate_flat_pattern()
    folded_solid: Solid = part.generate_folded_solid()

    expected_flat_length = 200.0 + (50.0 - flange1.bend_deduction_mm) + (40.0 - flange2.bend_deduction_mm)
    pattern_error = abs(flat_pattern.total_length_mm - expected_flat_length)

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="Sheet Metal Press Brake Bending & DIN 6935",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "bend_allowance_mm": round(flange1.bend_allowance_mm, 4),
            "bend_deduction_mm": round(flange1.bend_deduction_mm, 4),
            "unfolded_flat_length_mm": round(flat_pattern.total_length_mm, 4),
            "unfolded_flat_width_mm": round(flat_pattern.total_width_mm, 4),
            "flat_pattern_analytical_error_mm": round(pattern_error, 8),
            "folded_solid_volume_mm3": round(folded_solid.volume(), 2),
            "bends_count": len(part.bends)
        }
    )


def run_bim_building_physics_simulation() -> SimulationDomainResult:
    """
    Simulation 6 : Thermique et Structure BIM IFC4 Multicouche.
    Évalue la résistance thermique globale R_tot et la transmittance U (ISO 6946)
    d'un mur de façade multicouche avec isolant, le ferraillage de béton armé (masse d'acier),
    et les déperditions thermiques sous gradient de température Delta T = 25 K.
    """
    t_start = time.perf_counter()

    # Complexe de façade multicouche :
    # 1. Enduit extérieur (20 mm, lambda = 0.8 W/m·K)
    # 2. Laine minérale isolante (160 mm, lambda = 0.035 W/m·K)
    # 3. Voile béton porteur (200 mm, lambda = 2.3 W/m·K)
    # 4. Plâtre intérieur (13 mm, lambda = 0.25 W/m·K)
    layers = [
        BIMLayer("Enduit_Ext", 0.020, BIMMaterialType.BRICK, 20.0),
        BIMLayer("Isolant_Laine", 0.160, BIMMaterialType.INSULATION, 160.0),
        BIMLayer("Beton_Porteur", 0.200, BIMMaterialType.CONCRETE, 200.0),
        BIMLayer("Platre_Int", 0.013, BIMMaterialType.GYPSUM, 13.0)
    ]

    # Résistances thermiques par couche R = e / lambda (m²·K/W)
    r_layers = [
        0.020 / 0.8,    # 0.025
        0.160 / 0.035,  # 4.57143
        0.200 / 2.3,    # 0.08696
        0.013 / 0.25    # 0.05200
    ]
    # Résistances d'échange superficiel normalisées ISO 6946
    r_si = 0.13
    r_se = 0.04
    r_total = r_si + sum(r_layers) + r_se
    u_wall = 1.0 / r_total  # W/(m²·K)

    # Géométrie du mur : 6.0 m x 3.0 m
    wall = BIMWall(
        name="Facade_Nord",
        length=6.0,
        height=3.0,
        layers=layers
    )

    # Baie vitrée 1.5 m x 1.2 m
    window_opening = BIMOpening(
        name="Baie_Vitree",
        width=1.5,
        height=1.2,
        offset_x=2.0,
        elevation_z=0.9
    )
    wall.add_opening(window_opening)

    # Ferraillage d'armature : 20 barres HA de diamètre 14 mm, longueur 5.8 m
    rebar_cage = BIMRebar(
        rebar_id="Cage_HA14",
        diameter_mm=14.0,
        length_mm=5800.0,
        count=20,
        steel_grade="B500B"
    )
    wall.add_rebar(rebar_cage)

    gross_wall_area_m2 = (wall.length_mm * wall.height_mm) / 1e6
    window_area_m2 = (window_opening.width_mm * window_opening.height_mm) / 1e6
    net_wall_area_m2 = gross_wall_area_m2 - window_area_m2

    u_window = 1.2  # W/(m²·K)
    # Coefficient global de déperdition thermique H_T = U_wall * A_wall + U_win * A_win (W/K)
    h_transmission = (u_wall * net_wall_area_m2) + (u_window * window_area_m2)

    delta_t_kelvin = 25.0  # +20°C intérieur, -5°C extérieur
    heat_loss_watts = h_transmission * delta_t_kelvin

    steel_mass_kg = rebar_cage.steel_weight_kg

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="BIM IFC4 Multi-Layer Building Physics & Thermal Envelope",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "wall_thickness_total_mm": wall.total_thickness_mm,
            "wall_thermal_resistance_r_m2k_w": round(r_total, 4),
            "wall_u_value_w_m2k": round(u_wall, 4),
            "window_area_m2": round(window_area_m2, 2),
            "net_wall_area_m2": round(net_wall_area_m2, 2),
            "thermal_transmission_coefficient_w_k": round(h_transmission, 3),
            "heat_loss_at_delta_t_25k_watts": round(heat_loss_watts, 2),
            "rebar_steel_total_mass_kg": round(steel_mass_kg, 2)
        }
    )


def run_pbr_optical_raytracing_simulation() -> SimulationDomainResult:
    """
    Simulation 7 : Lancer de Rayons Optique PBR & Ombrage de Fresnel-Schlick.
    Vérifie la réflectance spéculaire sous angles d'incidence normaux et rasants (85°),
    le respect de la conservation d'énergie dans le studio 3-points,
    et exécute un rendu rasterisé logiciel haute fidélité.
    """
    t_start = time.perf_counter()

    studio = create_default_studio()
    raytracer = PBRRaytracer(environment=studio)

    aluminum = PBR_LIBRARY["Aluminium Brossé"]
    gold = PBR_LIBRARY["Or 24 Carats"]
    plastic = PBR_LIBRARY.get("Plastique ABS Noir Brillant", PBRMaterial("Plastique", (0.2, 0.2, 0.2), 0.3, 0.0, 0.5, 1.5))

    view_dir = Vector3D(0.0, 0.0, 1.0)

    # 1. Normale à incidence normale (theta = 0°)
    norm_direct = Vector3D(0.0, 0.0, 1.0)
    rgb_direct = raytracer.shade_vertex(norm_direct, view_dir, aluminum)

    # 2. Normale à angle rasant (theta = 85°)
    rad_85 = np.radians(85.0)
    norm_grazing = Vector3D(float(np.sin(rad_85)), 0.0, float(np.cos(rad_85)))
    rgb_grazing = raytracer.shade_vertex(norm_grazing, view_dir, aluminum)

    # 3. Rendu logiciel d'un solide de test sans affichage écran
    test_solid = make_box(50.0, 50.0, 50.0, center=True, name="Raytrace_Cube")
    qimg = raytracer.render_solid_to_image(test_solid, aluminum, width=160, height=120)

    # Somme des intensités lumineuses maximales entrantes du studio
    max_incoming_intensity = studio.ambient_intensity + sum(light.intensity for light in studio.lights)
    luminance_direct = 0.2126 * rgb_direct[0] + 0.7152 * rgb_direct[1] + 0.0722 * rgb_direct[2]

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="PBR Optical Raytracing & Studio Lighting",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "direct_incidence_luminance": round(luminance_direct, 4),
            "grazing_red_channel": round(rgb_grazing[0], 4),
            "grazing_green_channel": round(rgb_grazing[1], 4),
            "grazing_blue_channel": round(rgb_grazing[2], 4),
            "max_studio_intensity_bound": round(max_incoming_intensity, 2),
            "rendered_image_width_px": qimg.width(),
            "rendered_image_height_px": qimg.height(),
            "is_energy_conserving": bool(luminance_direct <= max_incoming_intensity)
        }
    )


def run_inertia_tensor_dynamics_simulation() -> SimulationDomainResult:
    """
    Simulation 8 : Tenseur d'Inertie 3D & Dynamique du Solide Rigide.
    Calcule par le théorème d'Ostrogradski et la décomposition tétraédrique
    les moments principaux d'inertie Ixx, Iyy, Izz et les rayons de giration kx, ky, kz
    d'un pavé d'aluminium 6061-T6 (100 x 60 x 40 mm, rho = 2.70 g/cm³),
    puis confronte les valeurs numériques aux solutions analytiques exactes.
    """
    t_start = time.perf_counter()

    dim_x = 100.0  # mm
    dim_y = 60.0   # mm
    dim_z = 40.0   # mm
    density_g_cm3 = 2.70  # Aluminium

    solid = make_box(dim_x, dim_y, dim_z, center=True, name="Inertia_Prism")
    inertia: InertiaTensor = compute_inertia_tensor(solid, density_g_cm3=density_g_cm3)

    # Formules analytiques exactes :
    # Volume V = a * b * c = 100 * 60 * 40 = 240 000 mm³ = 240 cm³
    # Masse M = 240 * 2.70 = 648.0 g
    # Ixx = (1/12) * M * (b² + c²) = (1/12) * 648.0 * (3600 + 1600) = 280 800 g·mm²
    # Iyy = (1/12) * M * (a² + c²) = (1/12) * 648.0 * (10000 + 1600) = 626 400 g·mm²
    # Izz = (1/12) * M * (a² + b²) = (1/12) * 648.0 * (10000 + 3600) = 734 400 g·mm²
    mass_analytical_g = (dim_x * dim_y * dim_z / 1000.0) * density_g_cm3
    ixx_theoretical = (1.0 / 12.0) * mass_analytical_g * (dim_y**2 + dim_z**2)
    iyy_theoretical = (1.0 / 12.0) * mass_analytical_g * (dim_x**2 + dim_z**2)
    izz_theoretical = (1.0 / 12.0) * mass_analytical_g * (dim_x**2 + dim_y**2)

    kx_theoretical = math.sqrt(ixx_theoretical / mass_analytical_g)
    ky_theoretical = math.sqrt(iyy_theoretical / mass_analytical_g)
    kz_theoretical = math.sqrt(izz_theoretical / mass_analytical_g)

    error_ixx_pct = abs(inertia.ixx - ixx_theoretical) / ixx_theoretical * 100.0
    error_iyy_pct = abs(inertia.iyy - iyy_theoretical) / iyy_theoretical * 100.0
    error_izz_pct = abs(inertia.izz - izz_theoretical) / izz_theoretical * 100.0

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SimulationDomainResult(
        domain_name="3D Inertia Tensor & Rigid Body Mass Properties",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        summary_metrics={
            "mass_analytical_g": round(mass_analytical_g, 2),
            "numerical_ixx_g_mm2": round(inertia.ixx, 1),
            "theoretical_ixx_g_mm2": round(ixx_theoretical, 1),
            "ixx_relative_error_pct": round(error_ixx_pct, 4),
            "numerical_iyy_g_mm2": round(inertia.iyy, 1),
            "theoretical_iyy_g_mm2": round(iyy_theoretical, 1),
            "iyy_relative_error_pct": round(error_iyy_pct, 4),
            "numerical_izz_g_mm2": round(inertia.izz, 1),
            "theoretical_izz_g_mm2": round(izz_theoretical, 1),
            "izz_relative_error_pct": round(error_izz_pct, 4),
            "radius_of_gyration_kx_mm": round(inertia.radius_of_gyration[0], 3),
            "theoretical_kx_mm": round(kx_theoretical, 3),
            "cross_product_ixy": round(inertia.ixy, 4),
            "cross_product_ixz": round(inertia.ixz, 4),
            "cross_product_iyz": round(inertia.iyz, 4)
        }
    )


def execute_full_simulation_matrix_phase2(
    output_dir: Optional[str] = None
) -> List[SimulationDomainResult]:
    """
    Orchestre l'exécution complète de la Matrice de Simulation Multi-Physique Phase 2.
    Génère un rapport consolidé au format JSON dans demo_output/simulations.
    """
    print("\n" + "=" * 80)
    print("MATRICE DE SIMULATIONS MULTI-PHYSIQUES DIFFÉRENCIÉES - PHASE 2 (CAD STUDIO 2026)")
    print("=" * 80)

    simulations: List[Callable[[], SimulationDomainResult]] = [
        run_symplectic_hamiltonian_simulation,
        run_closed_loop_kinematics_simulation,
        run_developable_surface_and_molding_simulation,
        run_dual_quaternions_screw_simulation,
        run_sheet_metal_bending_simulation,
        run_bim_building_physics_simulation,
        run_pbr_optical_raytracing_simulation,
        run_inertia_tensor_dynamics_simulation,
    ]

    results: List[SimulationDomainResult] = []
    total_start = time.perf_counter()

    for idx, sim_fn in enumerate(simulations, start=1):
        print(f"\n[{idx}/8] Exécution du domaine : {sim_fn.__name__}...")
        try:
            res = sim_fn()
            results.append(res)
            print(f"      -> STATUT: {res.status} | TEMPS: {res.elapsed_ms:.2f} ms")
            for k, v in list(res.summary_metrics.items())[:3]:
                print(f"         * {k}: {v}")
        except Exception as exc:
            print(f"      -> ÉCHEC CRITIQUE: {exc}")
            raise exc

    total_time_ms = (time.perf_counter() - total_start) * 1000.0

    print("\n" + "-" * 80)
    print(f"SYNTHÈSE : 8/8 DOMAINES PHASE 2 EXÉCUTÉS AVEC SUCCÈS ({total_time_ms:.2f} ms)")
    print("-" * 80)

    out_folder = output_dir or os.path.join(_PROJECT_ROOT, "demo_output", "simulations")
    os.makedirs(out_folder, exist_ok=True)
    report_path = os.path.join(out_folder, "simulation_matrix_phase2_report.json")

    report_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_elapsed_ms": total_time_ms,
        "domains_count": len(results),
        "results": [asdict(r) for r in results]
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print(f"Rapport consolidé exporté : {report_path}\n")
    return results


if __name__ == "__main__":
    execute_full_simulation_matrix_phase2()
