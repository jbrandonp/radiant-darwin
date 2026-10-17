"""
Matrice de Simulations Multi-Physiques Différenciées (Multi-Domain Simulation Matrix).
Exécute 8 simulations approfondies couvrant des domaines d'ingénierie avancés :
1. Aérodynamique & Aéroélasticité (Polaire mince, VLM et flexion de poutre Timoshenko/Euler-Bernoulli)
2. Éléments Finis Non-Linéaires (Tet10 quadratiques, écrouissage élasto-plastique Von Mises, contact Coulomb)
3. Robotique Industrielle 6 Axes (Cinématique directe/inverse, Jacobienne, manipulabilité, export URDF)
4. Fabrication Composite Aéronautique AFP (Placement robotisé guidé par les contraintes principales σ₁)
5. Métrologie 3D Scan-to-CAD (Recalage SVD-ICP avec bruit gaussien, conformité GD&T ISO GPS)
6. Jumeau Numérique Thermique ECAD (Échauffement Joule sur PCB multicouche, diffusion thermique)
7. Rendu Spatial XR 90 FPS (Streaming LOD continu, décimation adaptative et budget de trame 11.1 ms)
8. Passerelles Industrielles CalculiX & OpenFOAM (Génération et validation des jeux de données d'entrée)

Architecture strictement typée (zéro Any, zéro object) et complexité cognitive <= 25.
"""

from __future__ import annotations
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

# Insertion de la racine du projet dans sys.path
_PROJECT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.cam.fiber_placement_afp import (
    AutomatedFiberPlacementEngine,
    FiberTowTrajectory,
    StressTensor3D,
)
from src.cam.metrology_cmm_icp import (
    IterativeClosestPointAligner,
    MetrologyInspectionReport,
)
from src.core.types import Vector3D
from src.fea.calculix_bridge import (
    CalculixSimulationDeck,
    FeaElementType,
    FeaMaterial,
    NodalForce,
)
from src.fea.nonlinear_fem import (
    BilinearPlasticMaterial,
    FrictionalContactPair,
    NonlinearFEASolver,
    Tet10Element,
)
from src.fea.openfoam_bridge import (
    CfdFluidType,
    CfdTurbulenceModel,
    OpenFoamCase,
)
from src.specialized.aerodynamics_solver import (
    AerodynamicsSolver,
    AirfoilSurfaceData,
    BeamBoundaryCondition,
    BeamCrossSection,
    BeamStructuralAnalysisResult,
    FluidFlowProperties,
    StructuralBeamSolver,
    ThinAirfoilPolar,
    VortexLatticeResult,
)
from src.specialized.ecad_thermal_twin import (
    CopperTrace,
    ECADThermalReport,
    ECADThermalTwin,
    SMTComponent,
)
from src.specialized.robot_kinematics import (
    DHParameter,
    RobotArm6Axis,
)
from src.viewport.spatial_xr_lod import (
    ContinuousLODDecimator,
    LODStage,
    SpatialMeshChunk,
    XRStreamingFrameReport,
)


@dataclass
class SimulationDomainResult:
    """Résultat quantitatif d'un domaine de simulation."""
    domain_name: str
    status: str
    elapsed_ms: float
    summary_metrics: Dict[str, Union[float, int, str, bool]]


def run_aerodynamics_and_aeroelasticity_simulation() -> SimulationDomainResult:
    """
    Simulation 1 : Aérodynamique & Aéroélasticité d'une voilure.
    Calcule la polaire de portance/traînée et la déformée du longeron d'aile sous charge VLM.
    """
    t0 = time.perf_counter()
    solver = AerodynamicsSolver()
    flow = FluidFlowProperties(velocity_m_s=45.0, air_density=1.225, dynamic_viscosity=1.81e-5)
    airfoil = AirfoilSurfaceData(chord=0.8, span=4.0, angle_of_attack_deg=5.0, oswald_efficiency=0.88)

    # 1. Balayage d'incidence (Polar Sweep)
    angles_deg: List[float] = [-4.0, 0.0, 4.0, 8.0, 12.0, 16.0]
    cl_values: List[float] = []
    cd_values: List[float] = []
    for alpha in angles_deg:
        pol = solver.calculate_thin_airfoil_polar(alpha_deg=alpha, aspect_ratio=5.0, oswald_efficiency=0.88)
        cl_values.append(pol.lift_coefficient_cl)
        cd_values.append(pol.total_drag_cd)

    # 2. Couplage aéroélastique aile-longeron (Timoshenko vs Euler-Bernoulli)
    spar_section = BeamCrossSection.create_rectangular(
        width_m=0.035,
        height_m=0.075,
        youngs_modulus_e_pa=72.0e9, # Aluminium 7075-T6
        poissons_ratio_nu=0.33
    )
    beam_solver = StructuralBeamSolver()
    vlm_res, beam_res = beam_solver.solve_wing_aeroelastic_spar(
        airfoil=airfoil,
        flow=flow,
        spar_cross_section=spar_section,
        num_stations=41
    )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Aérodynamique & Aéroélasticité (VLM + Timoshenko)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "flow_velocity_m_s": flow.velocity_m_s,
            "total_lift_force_n": round(vlm_res.total_lift_n, 2),
            "total_induced_drag_n": round(vlm_res.total_induced_drag_n, 2),
            "cl_at_5deg": round(vlm_res.total_lift_coefficient_cl, 4),
            "wing_semi_span_m": 2.0,
            "max_spar_deflection_mm": round(beam_res.max_deflection_timoshenko_m * 1000.0, 3),
            "max_bending_stress_mpa": round(beam_res.max_bending_stress_pa * 1e-6, 2),
            "polar_sweep_angles_count": len(angles_deg)
        }
    )


def run_nonlinear_fem_simulation() -> SimulationDomainResult:
    """
    Simulation 2 : Éléments Finis Non-Linéaires Tet10, Plasticité & Contact frottant.
    Évalue l'écrouissage post-plastique et l'équilibre mécanique de contact.
    """
    t0 = time.perf_counter()
    material = BilinearPlasticMaterial(
        youngs_modulus_mpa=210000.0, # Acier structural
        poissons_ratio=0.30,
        yield_strength_mpa=355.0,
        tangent_modulus_mpa=15000.0 # Écrouissage linéaire
    )

    # Coordonnées nodales de deux tétraèdres adjacents Tet10
    coords = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [5.0, 10.0, 0.0],
        [5.0, 5.0, 10.0],
        [5.0, 0.0, 0.0],
        [7.5, 5.0, 0.0],
        [2.5, 5.0, 0.0],
        [2.5, 2.5, 5.0],
        [7.5, 2.5, 5.0],
        [5.0, 7.5, 5.0]
    ], dtype=np.float64)

    elem1 = Tet10Element(element_id=1, node_indices=list(range(10)))
    vol = elem1.calculate_volume(coords)
    ke = elem1.calculate_stiffness_matrix(coords, material)

    # Résolution non-linéaire avec plastification
    solver = NonlinearFEASolver()
    contact_pair = FrictionalContactPair(
        slave_node_coords=np.array([5.0, 5.0, -0.05]),
        master_plane_origin=np.array([5.0, 5.0, 0.0]),
        master_plane_normal=np.array([0.0, 0.0, 1.0]),
        penalty_stiffness=8000.0,
        friction_coefficient=0.25
    )

    eq_res = solver.solve_contact_equilibrium(
        material=material,
        applied_load_newtons=180000.0,
        cross_section_area_mm2=450.0,
        contact_pairs=[contact_pair],
        max_iterations=10
    )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Éléments Finis Non-Linéaires (Tet10, Plasticité & Contact)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "element_volume_mm3": round(vol, 2),
            "stiffness_matrix_dim": f"{ke.shape[0]}x{ke.shape[1]}",
            "applied_nominal_stress_mpa": 400.0,
            "final_von_mises_stress_mpa": round(float(eq_res["final_stress_mpa"]), 2),
            "plastic_strain": round(float(eq_res["plastic_strain"]), 6),
            "is_yielded": bool(eq_res["is_yielded"]),
            "normal_contact_force_n": round(float(eq_res["total_normal_contact_force_n"]), 2),
            "friction_force_n": round(float(eq_res["total_friction_force_n"]), 2)
        }
    )


def run_robotics_kinematics_simulation() -> SimulationDomainResult:
    """
    Simulation 3 : Robotique Industrielle 6 Axes & Analyse de Singularités.
    Planifie une trajectoire cartésienne et évalue la matrice Jacobienne et la manipulabilité.
    """
    t0 = time.perf_counter()
    robot = RobotArm6Axis(model_name="Kuka_KR10_Radiant")

    # Définition des angles nominaux (radians)
    test_angles = [0.0, 0.35, -0.70, 0.0, 0.50, 0.0]
    t_end = robot.forward_kinematics(test_angles)
    pos_end = (float(t_end[0, 3]), float(t_end[1, 3]), float(t_end[2, 3]))

    # Matrice Jacobienne 6x6
    j_mat = robot.calculate_jacobian(test_angles)
    det_j = float(np.linalg.det(j_mat))
    # Indice de manipulabilité de Yoshikawa w = sqrt(det(J * J^T))
    jj_t = j_mat @ j_mat.T
    det_jj_t = float(np.linalg.det(jj_t))
    manipulability = math.sqrt(max(0.0, det_jj_t))
    is_sing = robot.is_singular(test_angles, threshold=1e-3)

    # Trajectoire cartésienne de 10 points
    target_p1 = (pos_end[0] + 50.0, pos_end[1] - 30.0, pos_end[2] + 40.0)
    traj_pts = robot.plan_cartesian_trajectory(pos_end, target_p1, num_waypoints=10)

    # Export URDF
    urdf_xml = robot.to_urdf()

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Robotique Industrielle 6 Axes (Cinématique & Jacobienne)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "robot_model": robot.model_name,
            "tcp_x_mm": round(pos_end[0], 2),
            "tcp_y_mm": round(pos_end[1], 2),
            "tcp_z_mm": round(pos_end[2], 2),
            "jacobian_determinant": round(det_j, 4),
            "yoshikawa_manipulability": round(manipulability, 4),
            "is_near_singularity": is_sing,
            "trajectory_waypoints_count": len(traj_pts),
            "urdf_xml_length_bytes": len(urdf_xml)
        }
    )


def run_afp_composite_simulation() -> SimulationDomainResult:
    """
    Simulation 4 : Fabrication Aéronautique Composite AFP (Automated Fiber Placement).
    Calcule les lignes de courant des contraintes principales σ₁ pour la dépose robotisée.
    """
    t0 = time.perf_counter()
    afp_engine = AutomatedFiberPlacementEngine(
        tow_width_mm=6.35,
        tow_thickness_mm=0.15,
        min_steering_radius_mm=300.0,
        nominal_compaction_n=250.0,
        nominal_speed_mm_s=180.0
    )

    # Champ de contraintes analytique simulant un panneau d'avion percé
    def mock_stress_field(pt: Vector3D) -> StressTensor3D:
        # Contrainte biaxiale avec concentration de contraintes
        dist = math.sqrt(pt.x ** 2 + pt.y ** 2)
        factor = 1.0 + 50.0 / max(25.0, dist ** 2)
        return StressTensor3D(
            sig_xx=180.0 * factor,
            sig_yy=60.0,
            sig_zz=0.0,
            tau_xy=35.0,
            tau_yz=0.0,
            tau_xz=0.0
        )

    seed_pt = Vector3D(10.0, 50.0, 0.0)
    pref_dir = Vector3D(1.0, 0.2, 0.0).normalized()

    trajectory = afp_engine.trace_fiber_trajectory_from_stress_field(
        tow_id="TOW_001_CARBON_T800",
        material="HexTow_AS4D_Prepreg",
        seed_point=seed_pt,
        stress_field_fn=mock_stress_field,
        step_size_mm=3.0,
        max_steps=40,
        preferred_initial_direction=pref_dir
    )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Fabrication Composite AFP (Placement de Fibres σ₁)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "tow_material": trajectory.material_name,
            "tow_width_mm": trajectory.tow_width_mm,
            "tow_thickness_mm": trajectory.tow_thickness_mm,
            "total_waypoints": len(trajectory.waypoints),
            "total_deposited_length_mm": round(trajectory.total_length_mm, 2),
            "roller_compaction_force_n": afp_engine.nominal_compaction,
            "min_steering_radius_mm": afp_engine.min_steering_radius
        }
    )


def run_scan_to_cad_metrology_simulation() -> SimulationDomainResult:
    """
    Simulation 5 : Métrologie 3D Scan-to-CAD & Contrôle Dimensionnel GD&T (SVD-ICP).
    Recale un nuage de points numérisé bruité sur la géométrie CAO nominale.
    """
    t0 = time.perf_counter()
    rng = np.random.default_rng(101)

    # Grille nominale de référence (ex: face plane usinée 100x100 mm)
    grid_coords: List[Vector3D] = []
    normals: List[Vector3D] = []
    for x in np.linspace(0.0, 100.0, 15):
        for y in np.linspace(0.0, 100.0, 15):
            grid_coords.append(Vector3D(float(x), float(y), 0.0))
            normals.append(Vector3D(0.0, 0.0, 1.0))

    # Génération du scan mesuré avec désalignement rigide (+2 mm en X, -1.5 mm en Y) et bruit gaussien (σ = 0.015 mm)
    scanned_coords: List[Vector3D] = []
    for pt in grid_coords:
        noise = float(rng.normal(0.0, 0.015))
        scanned_coords.append(Vector3D(pt.x + 2.0, pt.y - 1.5, pt.z + noise))

    # Recalage SVD-ICP
    icp = IterativeClosestPointAligner(
        max_iterations=40,
        tolerance_epsilon=1e-6,
        upper_gdt_limit_mm=0.04,
        lower_gdt_limit_mm=-0.04
    )
    report = icp.align_and_inspect(scanned_coords, grid_coords, normals)

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Métrologie 3D Scan-to-CAD (Recalage SVD-ICP & GD&T)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "measured_points_count": report.total_points,
            "in_tolerance_percentage": round(report.in_tolerance_percentage, 2),
            "rms_deviation_um": round(report.rms_deviation_mm * 1000.0, 2),
            "max_positive_deviation_um": round(report.max_positive_deviation_mm * 1000.0, 2),
            "max_negative_deviation_um": round(report.max_negative_deviation_mm * 1000.0, 2),
            "recovered_translation_x_mm": round(report.rigid_transform_translation.x, 3),
            "recovered_translation_y_mm": round(report.rigid_transform_translation.y, 3)
        }
    )


def run_ecad_thermal_simulation() -> SimulationDomainResult:
    """
    Simulation 6 : Jumeau Numérique Thermique ECAD (Power PCB Joule Heating).
    Modélise l'échauffement Joule de pistes conductrices de forte puissance et composants actifs.
    """
    t0 = time.perf_counter()
    twin = ECADThermalTwin(board_width_mm=100.0, board_length_mm=80.0, layer_count=4)

    # Ajout de pistes cuivre transportant de forts courants
    t1 = CopperTrace("TRACE_VCC_1", "TOP_SIGNAL", 60.0, 2.5, 70.0, 6.5)
    t2 = CopperTrace("TRACE_VCC_2", "TOP_SIGNAL", 45.0, 2.0, 70.0, 5.0)
    twin.add_copper_trace(t1)
    twin.add_copper_trace(t2)

    # Ajout de composants actifs générant de la chaleur
    comp1 = SMTComponent("MOSFET_HIGH_SIDE", "DPAK", 30.0, 40.0, power_dissipation_watts=3.2, max_junction_temp_c=150.0)
    comp2 = SMTComponent("MOSFET_LOW_SIDE", "DPAK", 50.0, 40.0, power_dissipation_watts=2.8, max_junction_temp_c=150.0)
    comp3 = SMTComponent("BUCK_REGULATOR", "SOIC-8", 75.0, 25.0, power_dissipation_watts=1.4, max_junction_temp_c=125.0)
    twin.add_component(comp1)
    twin.add_component(comp2)
    twin.add_component(comp3)

    # Calcul du bilan thermique
    report = twin.solve_thermal_equilibrium(ambient_temp_c=25.0, convection_coeff_h=15.0)

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Thermique Électronique ECAD (Joule Heating & Hotspots)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "ambient_temp_c": report.ambient_temp_c,
            "max_board_temperature_c": round(report.max_board_temp_c, 2),
            "hottest_component_id": report.hottest_component_id,
            "total_joule_and_semiconductor_watts": round(report.total_electrical_heat_watts, 2),
            "is_thermally_safe": report.is_thermally_safe,
            "grid_dimensions": f"{report.temperature_grid.shape[0]}x{report.temperature_grid.shape[1]}"
        }
    )


def run_spatial_xr_lod_simulation() -> SimulationDomainResult:
    """
    Simulation 7 : Moteur Spatial XR LOD & Streaming Haute Fréquence 90 FPS.
    Garantit le respect du budget de trame de 11.1 ms par décimation géométrique adaptative.
    """
    t0 = time.perf_counter()
    decimator = ContinuousLODDecimator(target_fps=90.0, lod1_distance_m=2.0, lod2_distance_m=8.0, lod3_distance_m=20.0)

    # Création de 30 morceaux de maillage répartis à des distances variées de l'utilisateur
    chunks: List[SpatialMeshChunk] = []
    rng = np.random.default_rng(202)

    for i in range(30):
        # Distance comprise entre 0.8 m et 35.0 m
        dist_m = float(rng.uniform(0.8, 35.0))
        center = Vector3D(0.0, 0.0, dist_m * 1000.0)
        # Maillage fictif de 600 triangles
        verts = np.zeros((300, 3), dtype=np.float32)
        idxs = np.zeros((600, 3), dtype=np.int32)
        chunk = SpatialMeshChunk(
            chunk_id=f"chunk_{i:02d}",
            vertices=verts,
            indices=idxs,
            bounding_center=center,
            bounding_radius_mm=250.0
        )
        chunks.append(chunk)

    eye_pos = Vector3D(0.0, 0.0, 0.0)
    frame_report = decimator.evaluate_frame_stream(
        chunks=chunks,
        eye_position=eye_pos,
        simulated_gpu_time_ms=8.5
    )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Rendu Spatial XR & Streaming LOD 90 FPS",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "target_framerate_fps": decimator.target_fps,
            "frame_budget_ms": round(frame_report.frame_budget_ms, 2),
            "actual_render_time_ms": round(frame_report.actual_render_time_ms, 2),
            "is_frame_budget_respected": frame_report.is_frame_budget_respected,
            "total_triangles_rendered": frame_report.total_triangles_rendered,
            "lod_0_full_chunks": frame_report.lod_distribution.get(LODStage.LOD_0_FULL.value, 0),
            "lod_1_medium_chunks": frame_report.lod_distribution.get(LODStage.LOD_1_MEDIUM.value, 0),
            "lod_2_coarse_chunks": frame_report.lod_distribution.get(LODStage.LOD_2_COARSE.value, 0),
            "lod_3_proxy_chunks": frame_report.lod_distribution.get(LODStage.LOD_3_PROXY.value, 0)
        }
    )


def run_industrial_bridges_simulation() -> SimulationDomainResult:
    """
    Simulation 8 : Passerelles Solveurs Externes CalculiX (FEA .INP) & OpenFOAM (CFD Case).
    Génère les jeux de données Abaqus/CalculiX et dictionnaires OpenFOAM complets.
    """
    t0 = time.perf_counter()
    output_dir = os.path.join(_PROJECT_ROOT, "demo_output", "simulations")
    os.makedirs(output_dir, exist_ok=True)

    # 1. CalculiX Deck Generation (*.inp)
    steel = FeaMaterial(name="316L_Stainless", young_modulus_mpa=195000.0, poisson_ratio=0.28, density_kg_m3=8000.0)
    deck = CalculixSimulationDeck(
        job_name="bracket_tensile_test",
        material=steel,
        element_type=FeaElementType.C3D10
    )
    # Ajout de nœuds et d'un élément quadratique
    for i in range(1, 11):
        deck.add_node(i, Vector3D(float(i * 10.0), 0.0, 0.0))
    deck.add_tetrahedron(1, list(range(1, 11)))
    deck.fix_node(1)
    deck.apply_load(10, 1, 25000.0)

    inp_file = os.path.join(output_dir, "bracket_calculix.inp")
    deck.write_to_file(inp_file)

    # 2. OpenFOAM CFD Case Generation
    foam_case = OpenFoamCase(
        case_name="airfoil_transonic_cfd",
        domain_min=Vector3D(-2.0, -1.0, -0.5),
        domain_max=Vector3D(4.0, 1.0, 0.5),
        cells_x=30,
        cells_y=15,
        cells_z=5,
        fluid=CfdFluidType.AIR_20C,
        turbulence_model=CfdTurbulenceModel.K_OMEGA_SST,
        inlet_velocity=Vector3D(35.0, 2.0, 0.0),
        max_iterations=200
    )
    case_dir = os.path.join(output_dir, "openfoam_case")
    foam_case.write_case_to_directory(case_dir)

    elapsed = (time.perf_counter() - t0) * 1000.0
    return SimulationDomainResult(
        domain_name="Ponts Industriels Multi-Physiques (CalculiX & OpenFOAM)",
        status="SUCCESS",
        elapsed_ms=elapsed,
        summary_metrics={
            "calculix_inp_file": os.path.basename(inp_file),
            "calculix_nodes_count": len(deck.nodes),
            "calculix_element_type": deck.element_type.value,
            "openfoam_case_dir": os.path.basename(case_dir),
            "openfoam_fluid": foam_case.fluid.value,
            "openfoam_turbulence": foam_case.turbulence_model.value,
            "openfoam_inlet_speed_m_s": round(foam_case.inlet_velocity.length(), 2)
        }
    )


def execute_full_simulation_matrix() -> List[SimulationDomainResult]:
    """Exécute la matrice complète des 8 simulations multi-physiques différenciées."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 80)
    print("🔬 DÉMARRAGE DE LA MATRICE DE SIMULATIONS MULTI-PHYSIQUES DIFFÉRENCIÉES")
    print("=" * 80)

    simulations = [
        run_aerodynamics_and_aeroelasticity_simulation,
        run_nonlinear_fem_simulation,
        run_robotics_kinematics_simulation,
        run_afp_composite_simulation,
        run_scan_to_cad_metrology_simulation,
        run_ecad_thermal_simulation,
        run_spatial_xr_lod_simulation,
        run_industrial_bridges_simulation,
    ]

    results: List[SimulationDomainResult] = []

    for idx, sim_fn in enumerate(simulations, start=1):
        print(f"\n[{idx}/8] Exécution : {sim_fn.__name__}...")
        res = sim_fn()
        results.append(res)
        print(f"  ✅ Domaine : {res.domain_name} ({res.elapsed_ms:.1f} ms)")
        for k, v in res.summary_metrics.items():
            print(f"     - {k} : {v}")

    # Export du rapport global au format JSON
    output_dir = os.path.join(_PROJECT_ROOT, "demo_output", "simulations")
    os.makedirs(output_dir, exist_ok=True)
    report_json_path = os.path.join(output_dir, "simulation_matrix_report.json")

    report_payload = {
        "timestamp": time.time(),
        "total_simulations": len(results),
        "all_passed": all(r.status == "SUCCESS" for r in results),
        "domains": [asdict(r) for r in results]
    }

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"🏆 LES 8 SIMULATIONS DIFFÉRENCIÉES SE SONT EXÉCUTÉES AVEC 100% DE SUCCÈS !")
    print(f"📄 Rapport numérique JSON exporté : {report_json_path}")
    print("=" * 80)

    return results


if __name__ == "__main__":
    execute_full_simulation_matrix()
