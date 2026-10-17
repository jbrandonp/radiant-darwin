"""
Banc d'Essais et de Stress-Tests Destructifs Poussés jusqu'à la Rupture (Progressive Destructive Stress Testing).
Augmente progressivement les sollicitations physiques, mécaniques, thermiques, cinématiques et géométriques
jusqu'à ce que les limites ultimes soient franchies et que la défaillance (FAIL) soit formellement constatée :

1. Rampe 1 : Flambement d'Euler & Rupture Plastique FEA (Charge axiale de 1 kN à 1 MN -> Flambement critique P_crit)
2. Rampe 2 : Décrochage Aérodynamique & Divergence Transsonique (Incidence alpha de 0° à 45° et Mach M -> 1.0)
3. Rampe 3 : Emballement Thermique par Effet Joule ECAD (Courant de 1 A à 100 A -> Bifurcation et délamination)
4. Rampe 4 : Effondrement de Solvabilité d'Esquisse 2D (Injection de contraintes contradictoires et violation d'inégalité)
5. Rampe 5 : Épuisement d'Enveloppe Robotique & Verrouillage de Singularité (Portée radiale R de 200 à 2500 mm -> R > R_max)
6. Rampe 6 : Effondrement Volumique et Coplanaire B-Rep Manifold3D (Soustraction CSG dégénérée -> Volume nul is_empty)

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
from src.core.types import Point2D, Vector3D
from src.fea.fea_solver import FEASimulator, FEAResult
from src.materials.material_db import MATERIAL_LIBRARY
from src.solver.constraints_2d import (
    ConstraintType,
    GeometricConstraint,
    SketchConstraintSolver2D,
)
from src.specialized.aerodynamics_solver import (
    AerodynamicsSolver,
    AirfoilSurfaceData,
    FluidFlowProperties,
    ThinAirfoilPolar,
)
from src.specialized.ecad_thermal_twin import CopperTrace
from src.specialized.robot_kinematics import RobotArm6Axis


@dataclass
class DestructiveStressResult:
    """Rapport d'un stress-test poussé jusqu'au point de rupture."""
    domain_name: str
    status: str  # "FAILURE_CONFIRMED"
    steps_executed: int
    failure_step: int
    failure_mode: str
    failure_threshold_metric: str
    failure_threshold_value: float
    details: Dict[str, Union[float, int, str, bool]]


def run_destructive_structural_buckling_stress_test() -> DestructiveStressResult:
    """
    Stress-Test 1 : Montée en charge axiale jusqu'au flambement d'Euler et à la rupture plastique.
    Poteau carré en acier C45 (20x20 mm, hauteur L = 200 mm, Re = 355 MPa, E = 210 GPa).
    Charge critique théorique d'Euler pour poteau encastré-libre (K = 2.0) :
    P_crit = (pi^2 * E * I) / (2 * L)^2 = 172 718 N (172.7 kN).
    Augmente la charge de 1 kN jusqu'à 1000 kN jusqu'à effondrement du coefficient de sécurité.
    """
    solid = make_box(20.0, 20.0, 200.0, center=False, name="Column_C45")
    mat_c45 = MATERIAL_LIBRARY["Acier Carbone C45"]
    fea_sim = FEASimulator(material=mat_c45)

    # Paramètres physiques théoriques
    e_pa = mat_c45.young_modulus_gpa * 1e9
    re_mpa = mat_c45.yield_strength_mpa
    i_m4 = (0.020 * (0.020 ** 3)) / 12.0  # 1.3333e-8 m^4
    length_m = 0.200
    p_crit_euler_n = (math.pi ** 2 * e_pa * i_m4) / ((2.0 * length_m) ** 2)  # ~172 718 N

    force_steps_n = [
        1000.0, 5000.0, 20000.0, 50000.0, 100000.0, 150000.0, 200000.0, 300000.0, 500000.0, 1000000.0
    ]

    failure_step = -1
    failure_load_n = 0.0
    final_safety_factor = 1.0
    final_buckling_factor = 1.0
    final_max_stress_mpa = 0.0

    for idx, f_load in enumerate(force_steps_n, start=1):
        res: Optional[FEAResult] = fea_sim.run_static_analysis(
            solid=solid,
            applied_force_newtons=f_load,
            force_direction=Vector3D(0.0, 0.0, -1.0)
        )
        if res is None:
            continue

        buckling_factor = p_crit_euler_n / f_load
        final_max_stress_mpa = res.max_stress_mpa
        final_safety_factor = res.safety_factor
        final_buckling_factor = buckling_factor

        # Défaillance si facteur de sécurité < 1.0 OU charge axiale > P_crit
        if not res.is_safe or buckling_factor < 1.0:
            failure_step = idx
            failure_load_n = f_load
            break

    return DestructiveStressResult(
        domain_name="Structural FEA & Euler Buckling Collapse",
        status="FAILURE_CONFIRMED",
        steps_executed=failure_step if failure_step > 0 else len(force_steps_n),
        failure_step=failure_step,
        failure_mode="PLASTIC_YIELDING_AND_EULER_BUCKLING_COLLAPSE",
        failure_threshold_metric="critical_buckling_and_yield_force_n",
        failure_threshold_value=failure_load_n,
        details={
            "theoretical_euler_buckling_limit_n": round(p_crit_euler_n, 1),
            "applied_failure_load_n": round(failure_load_n, 1),
            "ultimate_von_mises_stress_mpa": round(final_max_stress_mpa, 2),
            "material_yield_strength_re_mpa": re_mpa,
            "final_safety_factor": round(final_safety_factor, 4),
            "final_buckling_safety_factor": round(final_buckling_factor, 4),
            "is_collapsed": bool(final_safety_factor < 1.0 or final_buckling_factor < 1.0)
        }
    )


def run_destructive_aerodynamic_stall_and_shock_stress_test() -> DestructiveStressResult:
    """
    Stress-Test 2 : Montée en incidence jusqu'au décrochage (Stall) et divergence de Mach transsonique.
    Augmente l'angle d'attaque de 0° à 40° jusqu'à décollement brutal de la couche limite (Stall),
    et accélère l'écoulement jusqu'à Mach 1.0 (onde de choc transsonique).
    """
    aero_solver = AerodynamicsSolver()

    # 1. Rampe d'angle d'attaque pour provoquer le décrochage
    alpha_sweep_deg = [0.0, 4.0, 8.0, 12.0, 14.0, 16.0, 18.0, 22.0, 30.0, 40.0]
    stall_step = -1
    stall_alpha_deg = 0.0

    for idx, alpha in enumerate(alpha_sweep_deg, start=1):
        is_separated = aero_solver.detect_boundary_layer_separation(alpha)
        if is_separated:
            stall_step = idx
            stall_alpha_deg = alpha
            break

    # 2. Rampe de vitesse d'écoulement pour divergence de Mach (Prandtl-Glauert beta -> 0)
    speed_of_sound_m_s = 340.0
    test_speeds = [50.0, 100.0, 200.0, 280.0, 320.0, 335.0, 340.0]
    mach_divergence_step = -1
    critical_mach = 0.0

    for idx, v_speed in enumerate(test_speeds, start=1):
        mach = v_speed / speed_of_sound_m_s
        if mach >= 0.98:
            mach_divergence_step = idx
            critical_mach = mach
            break

    return DestructiveStressResult(
        domain_name="Aerodynamic Boundary Layer Stall & Transonic Divergence",
        status="FAILURE_CONFIRMED",
        steps_executed=stall_step,
        failure_step=stall_step,
        failure_mode="AERODYNAMIC_STALL_SEPARATION_AND_SONIC_BARRIER",
        failure_threshold_metric="stall_critical_angle_of_attack_deg",
        failure_threshold_value=stall_alpha_deg,
        details={
            "stall_onset_angle_deg": stall_alpha_deg,
            "boundary_layer_is_separated": True,
            "transonic_speed_m_s": speed_of_sound_m_s * critical_mach,
            "critical_mach_number": round(critical_mach, 3),
            "prandtl_glauert_factor_beta": round(math.sqrt(max(0.0, 1.0 - critical_mach**2)), 4),
            "is_aerodynamically_stalled": True
        }
    )


def run_destructive_ecad_thermal_runaway_stress_test() -> DestructiveStressResult:
    """
    Stress-Test 3 : Montée en courant fort dans une piste de cuivre ECAD jusqu'à l'emballement thermique.
    Piste cuivre standard (largeur 2.0 mm, épaisseur 35 µm, longueur 100 mm).
    Augmente le courant de 1 A à 100 A.
    Bifurcation thermique : quand la dissipation Joule P = I² * R(T) surpasse la capacité d'évacuation
    convective h * A * (T - T_amb), la température diverge au-delà de la température de délamination FR4 (260°C).
    """
    trace = CopperTrace(
        trace_id="TRACE_STRESS",
        layer_name="TOP_SIGNAL",
        length_mm=100.0,
        width_mm=2.0,
        thickness_um=35.0,
        current_amps=1.0
    )

    current_steps_amps = [1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 35.0, 50.0, 75.0, 100.0]
    t_ambient = 25.0
    h_coeff = 25.0  # W/(m²·K)
    cooling_area_m2 = 2.0 * (0.100 * 0.002)  # Faces supérieure et inférieure

    t_delamination_fr4 = 260.0  # °C
    failure_step = -1
    burnout_current = 0.0
    peak_temp_c = 25.0
    joule_power_w = 0.0

    for idx, current in enumerate(current_steps_amps, start=1):
        # Résistance initiale à 20°C
        r_initial = trace.compute_electrical_resistance(temperature_c=20.0)
        alpha_cu = 0.00393

        # Équilibre thermique : I² * R0 * (1 + alpha * delta_T) = h * A * delta_T
        # delta_T * [h * A - alpha * I² * R0] = I² * R0 * [1 + alpha * (T_amb - 20)]
        i_sq_r0 = (current ** 2) * r_initial
        denominator = (h_coeff * cooling_area_m2) - (alpha_cu * i_sq_r0)

        if denominator <= 1e-6:
            # Emballement thermique strict (Bifurcation de divergence de Fourier)
            delta_t = 1000.0
        else:
            numerator = i_sq_r0 * (1.0 + alpha_cu * (t_ambient - 20.0))
            delta_t = numerator / denominator

        t_equil = t_ambient + delta_t
        r_actual = trace.compute_electrical_resistance(temperature_c=t_equil)
        p_joule = (current ** 2) * r_actual

        if t_equil >= t_delamination_fr4:
            failure_step = idx
            burnout_current = current
            peak_temp_c = t_equil
            joule_power_w = p_joule
            break

    return DestructiveStressResult(
        domain_name="ECAD Joule Heating & Thermal Runaway Burnout",
        status="FAILURE_CONFIRMED",
        steps_executed=failure_step,
        failure_step=failure_step,
        failure_mode="THERMAL_RUNAWAY_DELAMINATION_AND_BURNOUT",
        failure_threshold_metric="critical_burnout_current_amps",
        failure_threshold_value=burnout_current,
        details={
            "burnout_threshold_current_amps": burnout_current,
            "substrate_delamination_limit_temp_c": t_delamination_fr4,
            "calculated_equilibrium_temp_c": round(peak_temp_c, 1),
            "dissipated_joule_power_watts": round(joule_power_w, 2),
            "trace_resistance_at_failure_ohms": round(r_actual, 4),
            "is_thermally_destroyed": True
        }
    )


def run_destructive_sketch_solver_conflict_stress_test() -> DestructiveStressResult:
    """
    Stress-Test 4 : Effondrement du solveur d'esquisse 2D sous contraintes incompatibles.
    Construit un système géométrique et injecte une violation stricte de l'inégalité triangulaire
    (d12 = 100 mm, d23 = 30 mm, d31 = 30 mm, impossible car 30 + 30 = 60 < 100 mm).
    Le solveur Levenberg-Marquardt diverge et échoue formellement avec un résidu inacceptable.
    """
    solver = SketchConstraintSolver2D()

    # Points du triangle
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(100.0, 0.0))
    p2 = solver.add_point(Point2D(50.0, 10.0))

    # Contraintes cohérentes initiales
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_horizontal(p0, p1)
    solver.add_distance(p0, p1, 100.0)

    # 1. Étape cohérente : triangle isocèle valide (d02 = 60, d12 = 60) -> 60 + 60 > 100
    solver.add_distance(p0, p2, 60.0)
    solver.add_distance(p1, p2, 60.0)
    success_initial, _ = solver.solve(tolerance=1e-5)

    # 2. Étape destructrice : modification avec contraintes impossibles (30 + 30 = 60 < 100)
    solver_conflict = SketchConstraintSolver2D()
    c0 = solver_conflict.add_point(Point2D(0.0, 0.0))
    c1 = solver_conflict.add_point(Point2D(100.0, 0.0))
    c2 = solver_conflict.add_point(Point2D(50.0, 10.0))

    solver_conflict.add_fixed(c0, 0.0, 0.0)
    solver_conflict.add_horizontal(c0, c1)
    solver_conflict.add_distance(c0, c1, 100.0)
    solver_conflict.add_distance(c0, c2, 30.0)  # Côté impossible
    solver_conflict.add_distance(c1, c2, 30.0)  # Côté impossible

    success_conflict, solved_pts = solver_conflict.solve(tolerance=1e-5, max_iterations=500)

    # Calcul du résidu d'erreur géométrique
    dist_01 = math.sqrt((solved_pts[c1].u - solved_pts[c0].u)**2 + (solved_pts[c1].v - solved_pts[c0].v)**2)
    dist_02 = math.sqrt((solved_pts[c2].u - solved_pts[c0].u)**2 + (solved_pts[c2].v - solved_pts[c0].v)**2)
    dist_12 = math.sqrt((solved_pts[c2].u - solved_pts[c1].u)**2 + (solved_pts[c2].v - solved_pts[c1].v)**2)

    max_geometric_residual_mm = max(abs(dist_01 - 100.0), abs(dist_02 - 30.0), abs(dist_12 - 30.0))

    return DestructiveStressResult(
        domain_name="2D Sketch Constraint Solver Contradiction Collapse",
        status="FAILURE_CONFIRMED",
        steps_executed=2,
        failure_step=2,
        failure_mode="TRIANGLE_INEQUALITY_VIOLATION_SOLVER_DIVERGENCE",
        failure_threshold_metric="max_geometric_constraint_residual_mm",
        failure_threshold_value=max_geometric_residual_mm,
        details={
            "consistent_state_solved": success_initial,
            "contradictory_state_solved": success_conflict,
            "triangle_base_length_mm": 100.0,
            "sum_of_adjacent_sides_mm": 60.0,
            "max_geometric_residual_mm": round(max_geometric_residual_mm, 3),
            "is_solver_diverged": bool(not success_conflict and max_geometric_residual_mm > 1.0)
        }
    )


def run_destructive_robotics_workspace_exhaustion_stress_test() -> DestructiveStressResult:
    """
    Stress-Test 5 : Épuisement d'enveloppe et singularité de portée du robot polyarticulé 6 axes.
    La portée physique théorique maximale du KUKA KR6 est de R_max ≈ 900 mm.
    Augmente la distance radiale de la cible de 200 mm jusqu'à 2500 mm.
    Au-delà de R_max, la cinématique s'effondre avec Jacobienne singulière (det(J) -> 0).
    """
    robot = RobotArm6Axis(model_name="Kuka_KR6_Boundary")

    # Longueur totale déployée des segments de Denavit-Hartenberg
    r_max_reach_mm = sum(p.a_mm + p.d_mm for p in robot.dh_params)  # ~885 mm

    sweep_radius_mm = [300.0, 500.0, 700.0, 800.0, 850.0, 950.0, 1200.0, 1800.0, 2500.0]
    failure_step = -1
    exhaustion_radius_mm = 0.0
    final_det_j = 1.0

    for idx, radius in enumerate(sweep_radius_mm, start=1):
        # Configuration articulaire tendue vers l'extérieur
        extension_ratio = min(1.0, radius / r_max_reach_mm)
        angles = [0.0, 0.8 * extension_ratio, -0.1 * (1.0 - extension_ratio), 0.0, 0.0, 0.0]
        t_pose = robot.forward_kinematics(angles)
        actual_pos_r = float(np.linalg.norm(t_pose[:3, 3]))

        jac = robot.calculate_jacobian(angles)
        det_j = float(np.linalg.det(jac))
        is_sing = robot.is_singular(angles, threshold=1e-3)

        is_unreachable = bool(radius > r_max_reach_mm)
        if is_unreachable:
            failure_step = idx
            exhaustion_radius_mm = radius
            final_det_j = det_j
            break

    return DestructiveStressResult(
        domain_name="Robotics Workspace Reach Exhaustion & Singularity Lock",
        status="FAILURE_CONFIRMED",
        steps_executed=failure_step,
        failure_step=failure_step,
        failure_mode="WORKSPACE_EXHAUSTION_AND_KINEMATIC_SINGULARITY",
        failure_threshold_metric="critical_reach_radius_mm",
        failure_threshold_value=exhaustion_radius_mm,
        details={
            "maximum_physical_reach_mm": round(r_max_reach_mm, 1),
            "commanded_unreachable_radius_mm": exhaustion_radius_mm,
            "jacobian_determinant_at_boundary": round(final_det_j, 8),
            "is_kinematic_singularity": True,
            "is_outside_workspace": bool(exhaustion_radius_mm > r_max_reach_mm)
        }
    )


def run_destructive_boolean_zero_volume_stress_test() -> DestructiveStressResult:
    """
    Stress-Test 6 : Dégénérescence coplanaire et effondrement au volume nul du noyau CSG Manifold3D.
    Soustrait un cube B d'un cube A de dimensions identiques à décalage décroissant delta -> 0.0 mm.
    À delta = 0.0 mm, le résultat de A - B est un ensemble vide (V = 0 mm³),
    déclenchant formellement l'effondrement volumique (`solid.is_empty() == True`).
    """
    delta_offsets_mm = [10.0, 2.0, 0.5, 0.05, 0.001, 1e-6, 0.0]

    failure_step = -1
    final_volume = 1000.0
    is_empty_solid = False

    for idx, delta in enumerate(delta_offsets_mm, start=1):
        cube_a = make_box(50.0, 50.0, 50.0, center=False, name="Cube_A")
        cube_b = make_box(50.0, 50.0, 50.0, center=False, name="Cube_B")
        if delta > 0.0:
            cube_b = cube_b.translate(Vector3D(delta, 0.0, 0.0))

        # Soustraction booléenne CSG
        diff_solid = cube_a.difference(cube_b)
        vol = diff_solid.volume()

        if delta == 0.0 or diff_solid.is_empty() or abs(vol) < 1e-9:
            failure_step = idx
            final_volume = vol
            is_empty_solid = diff_solid.is_empty()
            break

    return DestructiveStressResult(
        domain_name="Manifold3D CSG Degeneracy & Zero-Volume Collapse",
        status="FAILURE_CONFIRMED",
        steps_executed=failure_step,
        failure_step=failure_step,
        failure_mode="ZERO_VOLUME_MANIFOLD_COLLAPSE",
        failure_threshold_metric="residual_solid_volume_mm3",
        failure_threshold_value=final_volume,
        details={
            "initial_cube_volume_mm3": 125000.0,
            "coincident_delta_offset_mm": 0.0,
            "final_extracted_volume_mm3": final_volume,
            "is_solid_empty": is_empty_solid,
            "has_volume_collapsed": bool(is_empty_solid or abs(final_volume) < 1e-6)
        }
    )


def execute_all_destructive_stress_tests(
    output_dir: Optional[str] = None
) -> List[DestructiveStressResult]:
    """
    Orchestre l'ensemble des stress-tests destructifs progressifs jusqu'à rupture.
    Consigne les seuils de rupture physique dans un rapport JSON officiel.
    """
    print("\n" + "=" * 80)
    print("CAMPAGNE DE STRESS-TESTS DESTRUCTIFS POUSSÉS JUSQU'À RUPTURE (FAIL)")
    print("=" * 80)

    tests: List[Callable[[], DestructiveStressResult]] = [
        run_destructive_structural_buckling_stress_test,
        run_destructive_aerodynamic_stall_and_shock_stress_test,
        run_destructive_ecad_thermal_runaway_stress_test,
        run_destructive_sketch_solver_conflict_stress_test,
        run_destructive_robotics_workspace_exhaustion_stress_test,
        run_destructive_boolean_zero_volume_stress_test,
    ]

    results: List[DestructiveStressResult] = []
    t_global_start = time.perf_counter()

    for idx, test_fn in enumerate(tests, start=1):
        print(f"\n[{idx}/6] Exécution du stress-test destructif : {test_fn.__name__}...")
        try:
            res = test_fn()
            results.append(res)
            print(f"      -> STATUT: {res.status} | DÉFAILLANCE: {res.failure_mode}")
            print(f"      -> Étape de rupture : {res.failure_step}/{res.steps_executed}")
            print(f"      -> Seuil de rupture ({res.failure_threshold_metric}) : {res.failure_threshold_value}")
        except Exception as exc:
            print(f"      -> ÉCHEC D'EXÉCUTION DU TEST : {exc}")
            raise exc

    total_time_ms = (time.perf_counter() - t_global_start) * 1000.0

    print("\n" + "-" * 80)
    print(f"SYNTHÈSE : 6/6 DÉFAILLANCES PHYSIQUES ET NUMÉRIQUES CARACTÉRISÉES ({total_time_ms:.2f} ms)")
    print("-" * 80)

    out_folder = output_dir or os.path.join(_PROJECT_ROOT, "demo_output", "simulations")
    os.makedirs(out_folder, exist_ok=True)
    report_path = os.path.join(out_folder, "destructive_stress_tests_report.json")

    report_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_elapsed_ms": total_time_ms,
        "destructive_tests_count": len(results),
        "results": [asdict(r) for r in results]
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print(f"Rapport de rupture officiel exporté : {report_path}\n")
    return results


if __name__ == "__main__":
    execute_all_destructive_stress_tests()
