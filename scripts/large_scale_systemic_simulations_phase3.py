"""
Grandes Simulations Systémiques Multi-Physiques & Jumeaux Numériques Industriels (Phase 3).
Exécute 4 grandes simulations d'ingénierie intégrée à l'échelle système :

1. Grand Système 1 : Jumeau Numérique Aéro-Structurel & Composite (Aero-Structural Digital Twin)
   - Aérodynamique tridimensionnelle VLM (Vortex Lattice Method) avec polaire et traînée induite
   - Flexion aéroélastique couplée de longeron (théorie des poutres de Timoshenko)
   - Réponse dynamique en vibration sous rafale via intégration symplectique de Chung-Hulbert
   - Peau de voilure en composite carbone AFP robotisé le long des contraintes principales σ₁

2. Grand Système 2 : Cellule Robotisée d'Usinage 5-Axes & Métrologie CMM (Machining & Metrology Workcell)
   - Bras manipulateur polyarticulé 6 axes (modèle Denavit-Hartenberg, cinématique et Jacobienne)
   - Trajectoire 5-axes RTCP avec orientation Lead/Tilt et vérification anti-gougeage d'enveloppe
   - Génération de code machine CNC et calcul physique du temps de cycle d'usinage
   - Contrôle métrologique Scan-to-CAD par palpeur CMM (recalage SVD-ICP et tolérancement ISO GPS)

3. Grand Système 3 : Jumeau Numérique Mécatronique & Électro-Thermique d'Onduleur EV (Inverter Twin)
   - Circuit imprimé de puissance ECAD multicouche (busbars cuivre 70 µm sous courant fort 50 A)
   - Chauffage Joule P = I²R et conduction thermique Fourier 2D/3D avec semi-conducteurs SiC
   - Boîtier étanche en tôlerie industrielle pliée DIN 6935 (calcul facteur K et patron plat 2D)
   - Rendu optique physique PBR sous studio d'éclairage 3 points (réflectance Fresnel-Schlick)

4. Grand Système 4 : Bâtiment Intelligent & Structure BIM IFC4 Multi-Étage (BIM Structural & Building Twin)
   - Modélisation BIM complète d'un bâtiment R+2 (3 étages, dalles béton armé et voiles périphériques)
   - Bilan thermique de l'enveloppe selon ISO 6946 (résistance R_tot, coefficient U, déperditions à ΔT = 35 K)
   - Métré structurel Eurocode 2 : volume de béton et masse d'armatures d'acier de ferraillage
   - Tenseur d'inertie 3D global, centre de masse d'Ostrogradski et moment de renversement sismique

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

from src.cam.cam_engine import CNCTool, ToolType, ToolpathOperation, ToolpathPoint
from src.cam.fiber_placement_afp import (
    AutomatedFiberPlacementEngine,
    FiberTowTrajectory,
    StressTensor3D,
)
from src.cam.five_axis_cam import (
    FiveAxisGougeChecker,
    FiveAxisGougeReport,
    FiveAxisToolPoint,
    ToolHolderGeometry,
)
from src.cam.metrology_cmm_icp import (
    IterativeClosestPointAligner,
    MetrologyInspectionReport,
)
from src.cam.post_processors import IndustrialPostProcessor, MachiningMetrics
from src.core.geometry import Solid, make_box
from src.core.inspector import InertiaTensor, compute_inertia_tensor
from src.core.nexus_kernel.symplectic_integrator import (
    GeneralizedAlphaIntegrator,
    GeneralizedAlphaStepResult,
)
from src.core.types import Vector3D
from src.render.pbr_material import PBRMaterial, PBR_LIBRARY
from src.render.raytracer import PBRRaytracer, create_default_studio
from src.sheetmetal.sheet_metal import (
    FlatPattern,
    SheetMetalPart,
    SheetMetalRule,
)
from src.specialized.aerodynamics_solver import (
    AerodynamicsSolver,
    AirfoilSurfaceData,
    BeamCrossSection,
    FluidFlowProperties,
    StructuralBeamSolver,
    ThinAirfoilPolar,
    VortexLatticeResult,
)
from src.specialized.bim_engine import (
    BIMBuildingStorey,
    BIMLayer,
    BIMMaterialType,
    BIMOpening,
    BIMRebar,
    BIMSlab,
    BIMWall,
    BIMWindow,
)
from src.specialized.ecad_thermal_twin import (
    CopperTrace,
    ECADThermalReport,
    ECADThermalTwin,
    SMTComponent,
)
from src.specialized.robot_kinematics import RobotArm6Axis


@dataclass
class SystemicSimulationResult:
    """Résultat consolidé d'une grande simulation d'ingénierie systémique."""
    system_name: str
    status: str
    elapsed_ms: float
    sub_modules_tested: List[str]
    system_metrics: Dict[str, Union[float, int, str, bool]]


def run_aerostructural_and_composite_digital_twin() -> SystemicSimulationResult:
    """
    Grand Système 1 : Jumeau Numérique Aéro-Structurel d'Aile & Peau Composite Carbone.
    Intègre :
    1. Aérodynamique 3D VLM (Vortex Lattice Method) sous écoulement subsonique V = 60 m/s.
    2. Flexion aéroélastique du longeron sous charges de portance (poutre épaisse de Timoshenko).
    3. Réponse temporelle dynamique en vibration de rafale par intégrateur symplectique (Chung-Hulbert).
    4. Renforcement structural de l'extrados par placement robotisé de fibres AFP guidé par σ₁.
    """
    t_start = time.perf_counter()

    # 1. Aérodynamique VLM
    flow = FluidFlowProperties(velocity_m_s=60.0, air_density=1.225, dynamic_viscosity=1.81e-5)
    airfoil = AirfoilSurfaceData(chord=1.0, span=6.0, angle_of_attack_deg=4.0, oswald_efficiency=0.90)

    spar_section = BeamCrossSection.create_rectangular(
        width_m=0.040,
        height_m=0.090,
        youngs_modulus_e_pa=71.7e9,  # Aluminium aérospatial 7075-T6
        poissons_ratio_nu=0.33
    )

    beam_solver = StructuralBeamSolver()
    vlm_res, beam_res = beam_solver.solve_wing_aeroelastic_spar(
        airfoil=airfoil,
        flow=flow,
        spar_cross_section=spar_section,
        num_stations=31
    )

    # 2. Réponse dynamique sous rafale verticale par intégrateur symplectique de Chung-Hulbert
    # Système modal équivalent 2 DDL (Mode 1 flexion + Mode 2 torsion)
    mass_matrix = np.array([
        [30.0, 0.0],
        [0.0, 18.0]
    ], dtype=np.float64)

    stiffness_matrix = np.array([
        [15000.0, -3000.0],
        [-3000.0, 9500.0]
    ], dtype=np.float64)

    # Intégrateur α-généralisé avec dissipation haute fréquence contrôlée (rho_inf = 0.95)
    integrator = GeneralizedAlphaIntegrator(
        mass_matrix=mass_matrix,
        stiffness_matrix=stiffness_matrix,
        damping_matrix=np.zeros((2, 2), dtype=np.float64),
        rho_infinity=0.95
    )

    # Rafale 1-cosine de 50 ms : pic de portance transitoire
    dt = 0.001
    d_curr = np.zeros(2, dtype=np.float64)
    v_curr = np.zeros(2, dtype=np.float64)
    a_curr = np.zeros(2, dtype=np.float64)
    max_gust_deflection_mm = 0.0

    for step_i in range(150):
        t_sec = step_i * dt
        gust_force = 1200.0 * math.sin(math.pi * t_sec / 0.05) if t_sec <= 0.05 else 0.0
        f_ext = np.array([gust_force, 0.3 * gust_force], dtype=np.float64)

        step_res: GeneralizedAlphaStepResult = integrator.advance_step(
            d_n=d_curr,
            v_n=v_curr,
            a_n=a_curr,
            f_ext_next=f_ext,
            f_ext_curr=f_ext,
            dt=dt
        )
        d_curr = step_res.displacements
        v_curr = step_res.velocities
        a_curr = step_res.accelerations
        defl_mm = float(abs(d_curr[0])) * 1000.0
        if defl_mm > max_gust_deflection_mm:
            max_gust_deflection_mm = defl_mm

    # 3. Peau composite en carbone AFP orientée selon les contraintes principales σ₁
    # Contrainte maximale à l'encastrement issue de la flexion
    sig_bend = beam_res.max_bending_stress_pa * 1e-6  # MPa
    shear_tau = 25.0  # MPa cisaillement d'effort tranchant

    stress_tensor = StressTensor3D(
        sig_xx=sig_bend,
        sig_yy=30.0,
        sig_zz=0.0,
        tau_xy=shear_tau,
        tau_yz=0.0,
        tau_xz=0.0
    )
    (s1, s2, s3), (v1, v2, v3) = stress_tensor.compute_principal_stresses()

    afp_engine = AutomatedFiberPlacementEngine(
        tow_width_mm=6.35,
        tow_thickness_mm=0.15,
        min_steering_radius_mm=250.0,
        nominal_compaction_n=300.0
    )

    def stress_field(p: Vector3D) -> StressTensor3D:
        decay = 1.0 - (abs(p.x) / 3000.0)
        return StressTensor3D(sig_xx=sig_bend * decay, sig_yy=30.0, sig_zz=0.0, tau_xy=shear_tau, tau_yz=0.0, tau_xz=0.0)

    tow_traj: FiberTowTrajectory = afp_engine.trace_fiber_trajectory_from_stress_field(
        tow_id="TOW_WING_UPPER_01",
        material="Carbon_HexTow_IM7",
        seed_point=Vector3D(0.0, 0.0, 0.0),
        stress_field_fn=stress_field,
        step_size_mm=10.0,
        max_steps=50,
        preferred_initial_direction=v1
    )

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SystemicSimulationResult(
        system_name="Grand Système 1 : Jumeau Numérique Aéro-Structurel d'Aile & Peau Composite",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        sub_modules_tested=["AerodynamicsSolver_VLM", "StructuralBeamSolver_Timoshenko", "GeneralizedAlpha_Symplectic", "AutomatedFiberPlacement_AFP"],
        system_metrics={
            "vlm_lift_force_n": round(vlm_res.total_lift_n, 2),
            "vlm_induced_drag_n": round(vlm_res.total_induced_drag_n, 2),
            "vlm_lift_to_drag_ratio": round(vlm_res.total_lift_n / max(1e-3, vlm_res.total_induced_drag_n), 2),
            "static_spar_deflection_mm": round(beam_res.max_deflection_timoshenko_m * 1000.0, 3),
            "max_bending_stress_mpa": round(sig_bend, 2),
            "dynamic_gust_peak_deflection_mm": round(max_gust_deflection_mm, 3),
            "dynamic_amplification_factor": round(max_gust_deflection_mm / max(1e-4, beam_res.max_deflection_timoshenko_m * 1000.0), 3),
            "composite_principal_stress_s1_mpa": round(s1, 2),
            "afp_deposited_tow_length_mm": round(tow_traj.total_length_mm, 2),
            "afp_waypoints_count": len(tow_traj.waypoints)
        }
    )


def run_robotic_machining_and_metrology_workcell() -> SystemicSimulationResult:
    """
    Grand Système 2 : Cellule Robotisée d'Usinage 5-Axes Haute Précision & Contrôle CMM.
    Intègre :
    1. Modélisation cinématique d'un robot polyarticulé 6 axes (Jacobienne, manipulabilité).
    2. Usinage 5-axes continu avec orientation de coupe Lead/Tilt et vérification anti-gougeage.
    3. Post-traitement G-code certifié avec estimation du temps de cycle d'usinage.
    4. Contrôle métrologique Scan-to-CAD par palpeur tridimensionnel MMT (recalage SVD-ICP).
    """
    t_start = time.perf_counter()

    # 1. Bras robotisé 6 axes
    robot = RobotArm6Axis(model_name="Kuka_KR6_R900_Cell")
    nominal_joint_angles = [0.10, 0.45, -0.65, 0.0, 0.35, 0.0]

    tcp_pos, rot_mat = robot.forward_kinematics_pose(nominal_joint_angles)
    jac_mat = robot.calculate_jacobian(nominal_joint_angles)
    # Manipulabilité de Yoshikawa w = sqrt(det(J * J^T))
    jj_t = jac_mat @ jac_mat.T
    manipulability = float(math.sqrt(max(0.0, float(np.linalg.det(jj_t)))))
    is_singular = robot.is_singular(nominal_joint_angles, threshold=1e-3)

    # 2. CAM 5-axes anti-gougeage
    holder_geom = ToolHolderGeometry(
        cutter_radius=6.0,
        flute_length=25.0,
        shank_radius=8.0,
        shank_length=45.0,
        holder_bottom_radius=22.0,
        holder_top_radius=35.0,
        holder_length=60.0
    )
    gouge_checker = FiveAxisGougeChecker(holder=holder_geom, safety_clearance_mm=1.5)

    surf_norm = Vector3D(0.0, 0.0, 1.0)
    feed_dir = Vector3D(1.0, 0.0, 0.0)
    nominal_tool_vec = gouge_checker.compute_initial_orientation(
        surface_normal=surf_norm,
        feed_direction=feed_dir,
        lead_angle_deg=15.0,
        tilt_angle_deg=5.0
    )

    # Obstacle simulant la paroi voisine d'une aube de turbine
    obstacles = [Vector3D(15.0, 10.0, 30.0), Vector3D(15.0, -10.0, 30.0)]
    gouge_rep: FiveAxisGougeReport = gouge_checker.check_and_correct_point(
        tip_pos=Vector3D(0.0, 0.0, 0.0),
        initial_tool_vec=nominal_tool_vec,
        obstacle_points=obstacles
    )

    # 3. Trajectoire d'usinage et Post-Processeur G-Code
    tool_cutter = CNCTool(
        tool_id=1,
        name="Fraise_Hemispherique_D12",
        tool_type=ToolType.BALL_NOSE,
        diameter_mm=12.0,
        flute_length_mm=25.0,
        feedrate_mm_min=1800.0,
        plunge_rate_mm_min=400.0,
        spindle_speed_rpm=15000.0
    )

    # Contournage d'une passe d'usinage
    pts = [
        ToolpathPoint(Vector3D(0.0, 0.0, 10.0), is_rapid=True),
        ToolpathPoint(Vector3D(0.0, 0.0, 0.0), is_rapid=False),
        ToolpathPoint(Vector3D(100.0, 0.0, 0.0), is_rapid=False),
        ToolpathPoint(Vector3D(100.0, 50.0, 0.0), is_rapid=False),
        ToolpathPoint(Vector3D(0.0, 50.0, 0.0), is_rapid=False),
        ToolpathPoint(Vector3D(0.0, 50.0, 10.0), is_rapid=True)
    ]
    machining_op = ToolpathOperation(name="Contournage_Turbine", tool=tool_cutter, points=pts)
    metrics: MachiningMetrics = IndustrialPostProcessor.calculate_metrics([machining_op])
    gcode_txt: str = IndustrialPostProcessor.post_process_haas([machining_op], program_number=2026)

    # 4. Contrôle métrologique Scan-to-CAD par palpeur CMM
    # Nuage nominal de 50 points sur la trajectoire usinée
    nominal_pts: List[Vector3D] = []
    nominal_normals: List[Vector3D] = []
    measured_pts: List[Vector3D] = []
    # Simulation d'un décalage d'origine d'usinage [-1.0, 0.5, 0.0] mm + dispersion gaussienne 8 µm
    rng = np.random.default_rng(2026)
    for i in range(50):
        x = float(i * 2.0)
        y = float(math.sin(i * 0.1) * 10.0)
        z = 0.0
        p_nom = Vector3D(x, y, z)
        nominal_pts.append(p_nom)
        nominal_normals.append(Vector3D(0.0, 0.0, 1.0))

        noise = float(rng.normal(0.0, 0.008))
        p_meas = Vector3D(x - 1.0 + noise, y + 0.5 + noise, z + noise)
        measured_pts.append(p_meas)

    aligner = IterativeClosestPointAligner(
        max_iterations=30,
        upper_gdt_limit_mm=0.03,
        lower_gdt_limit_mm=-0.03
    )
    metro_rep: MetrologyInspectionReport = aligner.align_and_inspect(
        scanned_points=measured_pts,
        nominal_points=nominal_pts,
        nominal_normals=nominal_normals
    )

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SystemicSimulationResult(
        system_name="Grand Système 2 : Cellule Robotisée d'Usinage 5-Axes & Métrologie CMM",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        sub_modules_tested=["RobotArm6Axis", "FiveAxisGougeChecker", "IndustrialPostProcessor", "IterativeClosestPointAligner"],
        system_metrics={
            "robot_tcp_position_z_mm": round(float(tcp_pos[2]), 2),
            "yoshikawa_manipulability": round(manipulability, 4),
            "is_kinematically_singular": is_singular,
            "five_axis_is_safe": gouge_rep.is_safe,
            "five_axis_clearance_mm": round(gouge_rep.min_clearance_mm, 3),
            "cutting_distance_mm": round(metrics.cutting_distance_mm, 2),
            "machining_cycle_time_s": round(metrics.estimated_time_seconds, 2),
            "gcode_program_length_lines": len(gcode_txt.splitlines()),
            "cmm_in_tolerance_percentage": round(metro_rep.in_tolerance_percentage, 2),
            "cmm_realigned_rms_mm": round(metro_rep.rms_deviation_mm, 4),
            "cmm_estimated_shift_x_mm": round(metro_rep.rigid_transform_translation.x, 3)
        }
    )


def run_ev_power_inverter_mechatronics_twin() -> SystemicSimulationResult:
    """
    Grand Système 3 : Jumeau Numérique Mécatronique & Électro-Thermique d'Onduleur EV.
    Intègre :
    1. Circuit ECAD de puissance triphasé (busbars cuivre 70 µm sous courant fort 50 A).
    2. Chauffage Joule P = I²R et conduction thermique Fourier 2D/3D avec 6 MOSFETs SiC.
    3. Boîtier étanche en tôlerie industrielle pliée DIN 6935 (calcul facteur K et patron plat 2D).
    4. Rendu optique photoréaliste PBR sous studio d'éclairage 3 points (réflectance Fresnel-Schlick).
    """
    t_start = time.perf_counter()

    # 1. Circuit ECAD & Dissipation Joule
    # Trois pistes de puissance de phase (U, V, W)
    traces = [
        CopperTrace(trace_id="BUSBAR_PHASE_U", layer_name="TOP_SIGNAL", length_mm=120.0, width_mm=10.0, thickness_um=70.0, current_amps=50.0),
        CopperTrace(trace_id="BUSBAR_PHASE_V", layer_name="TOP_SIGNAL", length_mm=120.0, width_mm=10.0, thickness_um=70.0, current_amps=50.0),
        CopperTrace(trace_id="BUSBAR_PHASE_W", layer_name="TOP_SIGNAL", length_mm=120.0, width_mm=10.0, thickness_um=70.0, current_amps=50.0),
    ]

    total_joule_power_w = 0.0
    for tr in traces:
        r_ohm = tr.compute_electrical_resistance(temperature_c=70.0)
        p_w = (tr.current_amps ** 2) * r_ohm
        total_joule_power_w += p_w

    # Composants MOSFET SiC montés en surface (6 interrupteurs de puissance à 15 W chacun)
    mosfets = [
        SMTComponent(
            designator=f"Q{i+1}_SiC",
            package_name="TO-247-4L",
            position_x_mm=25.0 + float(i * 15.0),
            position_y_mm=40.0,
            power_dissipation_watts=15.0,
            thermal_resistance_jc_k_w=0.65,
            max_junction_temp_c=150.0
        )
        for i in range(6)
    ]
    total_active_power_w = sum(m.power_dissipation_watts for m in mosfets)

    # Jumeau thermique ECAD
    thermal_twin = ECADThermalTwin(
        board_width_mm=120.0,
        board_length_mm=180.0,
        board_thickness_mm=2.0
    )
    for tr in traces:
        thermal_twin.add_copper_trace(tr)
    for m in mosfets:
        thermal_twin.add_component(m)

    ecad_report: ECADThermalReport = thermal_twin.solve_thermal_equilibrium(
        ambient_temp_c=45.0,
        convection_coeff_h=35.0,
        grid_resolution=20
    )

    # 2. Boîtier en tôlerie industrielle pliée DIN 6935
    sheet_rule = SheetMetalRule(
        name="Aluminium_5754_H111_2mm",
        thickness_mm=2.0,
        bend_radius_mm=2.0,
        k_factor=0.44
    )
    chassis = SheetMetalPart(base_width=150.0, base_length=210.0, rule=sheet_rule)
    flange1 = chassis.add_flange(length_mm=45.0, angle_deg=90.0)
    flange2 = chassis.add_flange(length_mm=45.0, angle_deg=90.0)

    flat_pat: FlatPattern = chassis.generate_flat_pattern()
    chassis_solid: Solid = chassis.generate_folded_solid()

    # 3. Rendu optique PBR de l'enveloppe
    studio = create_default_studio()
    raytracer = PBRRaytracer(environment=studio)
    alu_mat = PBR_LIBRARY["Aluminium Brossé"]

    # Shading d'une normale de face du boîtier
    norm_face = Vector3D(0.0, 0.0, 1.0)
    view_vec = Vector3D(0.0, 0.0, 1.0)
    rgb_shaded = raytracer.shade_vertex(norm_face, view_vec, alu_mat)

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SystemicSimulationResult(
        system_name="Grand Système 3 : Jumeau Numérique Mécatronique & Électro-Thermique d'Onduleur EV",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        sub_modules_tested=["ECADThermalTwin", "CopperTrace_Joule", "SheetMetalPart_DIN6935", "PBRRaytracer"],
        system_metrics={
            "copper_joule_heating_total_w": round(total_joule_power_w, 3),
            "mosfet_active_dissipation_w": round(total_active_power_w, 2),
            "total_thermal_dissipation_w": round(total_joule_power_w + total_active_power_w, 2),
            "max_hotspot_temperature_c": round(ecad_report.max_board_temp_c, 2),
            "mean_board_temperature_c": round(float(np.mean(ecad_report.temperature_grid)), 2),
            "is_thermal_runaway_safe": bool(ecad_report.max_board_temp_c < 125.0),
            "chassis_unfolded_length_mm": round(flat_pat.total_length_mm, 2),
            "chassis_unfolded_width_mm": round(flat_pat.total_width_mm, 2),
            "chassis_bend_deduction_mm": round(flange1.bend_deduction_mm, 4),
            "chassis_folded_volume_mm3": round(chassis_solid.volume(), 2),
            "pbr_shading_reflectance_norm": round(math.sqrt(sum(c**2 for c in rgb_shaded)), 4)
        }
    )


def run_bim_multistorey_structural_and_thermal_twin() -> SystemicSimulationResult:
    """
    Grand Système 4 : Bâtiment Intelligent & Structure BIM IFC4 Multi-Étage.
    Intègre :
    1. Bâtiment R+2 modélisé en IFC4 (3 étages, 12 voiles multicouches, 3 dalles béton).
    2. Thermique globale de l'enveloppe selon ISO 6946 (coefficient U, déperditions hivernales sous ΔT = 35 K).
    3. Métré structurel Eurocode 2 : volume total de béton et masse des armatures d'acier.
    4. Tenseur d'inertie 3D global, centre de masse d'Ostrogradski et stabilité au renversement sismique.
    """
    t_start = time.perf_counter()

    # 1. Modélisation BIM R+2 (Rez-de-chaussée, R+1, R+2)
    # Complexe de façade passif : 20 mm enduit, 180 mm laine minérale (0.035 W/mK), 200 mm béton armé (2.3 W/mK), 13 mm plâtre (0.25 W/mK)
    layers = [
        BIMLayer("Enduit_Ext", 0.020, BIMMaterialType.BRICK, 20.0),
        BIMLayer("Laine_Minerale_180", 0.180, BIMMaterialType.INSULATION, 180.0),
        BIMLayer("Voile_Beton_200", 0.200, BIMMaterialType.CONCRETE, 200.0),
        BIMLayer("Platre_Int_13", 0.013, BIMMaterialType.GYPSUM, 13.0)
    ]

    r_tot = 0.13 + (0.020 / 0.8) + (0.180 / 0.035) + (0.200 / 2.3) + (0.013 / 0.25) + 0.04
    u_wall = 1.0 / r_tot

    storeys: List[BIMBuildingStorey] = []
    storey_height_mm = 3000.0
    dim_x_mm = 10000.0  # 10 m
    dim_y_mm = 6000.0   # 6 m

    total_concrete_volume_m3 = 0.0
    total_steel_mass_kg = 0.0
    total_envelope_loss_w_k = 0.0

    for level in range(3):
        st_name = f"Niveau_R+{level}" if level > 0 else "Rez_de_Chaussee"
        storey = BIMBuildingStorey(name=st_name, elevation=level * 3.0, height_mm=storey_height_mm)

        # Dalle béton armé 10m x 6m x 0.20m
        slab = BIMSlab(
            slab_id=f"Slab_{level}",
            thickness_mm=200.0,
            length_mm=dim_x_mm,
            width_mm=dim_y_mm,
            elevation_mm=level * storey_height_mm
        )
        total_concrete_volume_m3 += slab.volume_m3

        # Armatures nappe dalle : 30 barres HA14 longueur 9.8m
        slab_rebars = BIMRebar(
            rebar_id=f"Rebar_Slab_{level}",
            diameter_mm=14.0,
            length_mm=9800.0,
            count=30,
            steel_grade="B500B"
        )
        slab.add_rebar(slab_rebars)
        total_steel_mass_kg += slab_rebars.steel_weight_kg
        storey.add_slab(slab)

        # 4 Murs périphériques (2 longs de 10m, 2 courts de 6m)
        wall_lengths = [dim_x_mm, dim_y_mm, dim_x_mm, dim_y_mm]
        for w_idx, w_len in enumerate(wall_lengths):
            wall = BIMWall(
                name=f"Wall_{level}_{w_idx}",
                length=w_len / 1000.0,
                height=3.0,
                layers=layers
            )
            # Voile béton 200 mm seul pour le volume structurel
            vol_concrete_wall = (w_len / 1000.0) * 3.0 * 0.20
            total_concrete_volume_m3 += vol_concrete_wall

            # Baies vitrées (1 fenêtre par mur)
            win_op = BIMOpening(name=f"Win_{level}_{w_idx}", width=1.4, height=1.2, offset_x=2.0, elevation_z=0.9)
            wall.add_opening(win_op)

            # Armatures voile : 10 barres HA12 longueur 2.8m
            wall_rebar = BIMRebar(rebar_id=f"Rebar_W_{level}_{w_idx}", diameter_mm=12.0, length_mm=2800.0, count=10)
            wall.add_rebar(wall_rebar)
            total_steel_mass_kg += wall_rebar.steel_weight_kg

            # Bilan thermique du pan de mur
            gross_area = (w_len / 1000.0) * 3.0
            win_area = 1.4 * 1.2
            net_area = gross_area - win_area
            u_win = 0.85  # Triple vitrage
            h_wall_part = (u_wall * net_area) + (u_win * win_area)
            total_envelope_loss_w_k += h_wall_part

            storey.add_wall(wall)

        storeys.append(storey)

    delta_t_winter_k = 35.0  # +21°C intérieur, -14°C extérieur hivernal
    total_heat_loss_watts = total_envelope_loss_w_k * delta_t_winter_k

    # 2. Modèle volumique solide global du bâtiment et tenseur d'inertie 3D
    # Boîte enveloppe globale 10m x 6m x 9m
    building_solid = make_box(10000.0, 6000.0, 9000.0, center=False, name="BIM_Building_Volume")
    # Densité apparente équivalente du bâtiment complet (béton + planchers + cloisons ~ 350 kg/m³)
    inertia: InertiaTensor = compute_inertia_tensor(building_solid, density_g_cm3=0.35)

    total_mass_tons = (total_concrete_volume_m3 * 2400.0 + total_steel_mass_kg) / 1000.0
    gravity_g = 9.81
    # Effort tranchant sismique à la base V_b = 0.25 * M * g (Zone sismique Eurocode 8)
    seismic_base_shear_kn = 0.25 * (total_mass_tons * 1000.0) * gravity_g / 1000.0
    center_of_mass_z_m = 4.5  # Mi-hauteur du bâtiment
    seismic_overturning_moment_kn_m = seismic_base_shear_kn * center_of_mass_z_m

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return SystemicSimulationResult(
        system_name="Grand Système 4 : Bâtiment Intelligent & Structure BIM IFC4 Multi-Étage",
        status="SUCCESS",
        elapsed_ms=elapsed_ms,
        sub_modules_tested=["BIMBuildingStorey_IFC4", "BIMWall_ISO6946", "BIMSlab_Rebar", "compute_inertia_tensor_3D"],
        system_metrics={
            "storeys_count": len(storeys),
            "building_total_height_m": 9.0,
            "total_concrete_volume_m3": round(total_concrete_volume_m3, 2),
            "total_rebar_steel_mass_kg": round(total_steel_mass_kg, 2),
            "rebar_density_kg_per_m3_concrete": round(total_steel_mass_kg / max(1.0, total_concrete_volume_m3), 2),
            "wall_u_value_w_m2k": round(u_wall, 4),
            "envelope_heat_loss_coefficient_w_k": round(total_envelope_loss_w_k, 2),
            "winter_heat_loss_at_delta_t_35k_watts": round(total_heat_loss_watts, 2),
            "building_structural_mass_tons": round(total_mass_tons, 2),
            "seismic_base_shear_kn": round(seismic_base_shear_kn, 2),
            "seismic_overturning_moment_kn_m": round(seismic_overturning_moment_kn_m, 2),
            "building_gyration_radius_kx_m": round(inertia.radius_of_gyration[0] / 1000.0, 3)
        }
    )


def execute_all_large_scale_systemic_simulations(
    output_dir: Optional[str] = None
) -> List[SystemicSimulationResult]:
    """
    Exécute les 4 Grandes Simulations Systémiques Industrielles (Phase 3).
    Génère un rapport consolidé dans demo_output/simulations/large_scale_systemic_simulations_phase3_report.json.
    """
    print("\n" + "=" * 80)
    print("GRANDES SIMULATIONS SYSTÉMIQUES MULTI-PHYSIQUES & JUMEAUX NUMÉRIQUES (PHASE 3)")
    print("=" * 80)

    systems: List[Callable[[], SystemicSimulationResult]] = [
        run_aerostructural_and_composite_digital_twin,
        run_robotic_machining_and_metrology_workcell,
        run_ev_power_inverter_mechatronics_twin,
        run_bim_multistorey_structural_and_thermal_twin,
    ]

    results: List[SystemicSimulationResult] = []
    t_start_global = time.perf_counter()

    for idx, sys_fn in enumerate(systems, start=1):
        print(f"\n[{idx}/4] Exécution du grand système : {sys_fn.__name__}...")
        try:
            res = sys_fn()
            results.append(res)
            print(f"      -> STATUT: {res.status} | TEMPS: {res.elapsed_ms:.2f} ms")
            print(f"      -> Sous-modules : {', '.join(res.sub_modules_tested)}")
            for k, v in list(res.system_metrics.items())[:3]:
                print(f"         * {k}: {v}")
        except Exception as exc:
            print(f"      -> ÉCHEC CRITIQUE: {exc}")
            raise exc

    total_time_ms = (time.perf_counter() - t_start_global) * 1000.0

    print("\n" + "-" * 80)
    print(f"SYNTHÈSE : 4/4 GRANDES SIMULATIONS SYSTÉMIQUES EXÉCUTÉES AVEC SUCCÈS ({total_time_ms:.2f} ms)")
    print("-" * 80)

    out_folder = output_dir or os.path.join(_PROJECT_ROOT, "demo_output", "simulations")
    os.makedirs(out_folder, exist_ok=True)
    report_path = os.path.join(out_folder, "large_scale_systemic_simulations_phase3_report.json")

    report_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_elapsed_ms": total_time_ms,
        "systems_count": len(results),
        "results": [asdict(r) for r in results]
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print(f"Rapport consolidé exporté : {report_path}\n")
    return results


if __name__ == "__main__":
    execute_all_large_scale_systemic_simulations()
