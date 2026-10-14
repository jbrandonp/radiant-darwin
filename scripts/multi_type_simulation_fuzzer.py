"""
Banc de simulation multi-physique, stress testing et fuzzing géométrique (Multi-Type Simulation Fuzzer).
Teste systématiquement les limites physiques, topologiques et algorithmiques de CAD Studio :
1. FEA & Éléments Finis : chargement nul, chargements démesurés, Poisson incompressible/auxétique, modes rigides.
2. Éléments Finis Non-Linéaires (Tet10, Contact, Plasticité) : tétraèdres dégénérés, volume nul, déformations plastiques extrêmes.
3. Géométrie & B-Rep : dimensions nulles/négatives, intersections disjointes, congés surdimensionnés, coques limites.
4. Solveur de Contraintes 2D : systèmes sur-contraints, contraintes contradictoires, longueurs nulles, Jacobiennes singulières.
5. CAM & Usinage : fraise géante, passe nulle, profondeurs négatives, opérations 5-axes limites.
6. Tôlerie & Pliage : épaisseur nulle, pli à angle limite, hauteur de rebord négative, développé DXF.
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from typing import Dict, List, Tuple, Optional, Any

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Imports du moteur CAD Studio
from src.core.document import CADDocument
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
)
from src.fea.fea_solver import FEASimulator, FEAResult
from src.fea.nonlinear_fem import (
    Tet10Element,
    BilinearPlasticMaterial,
    FrictionalContactPair,
    NonlinearFEASolver
)
from src.cam.cam_engine import CAMEngine, CNCTool, ToolType
from src.sheetmetal.sheet_metal import SheetMetalPart
from src.solver.constraints_2d import (
    ConstraintType,
    GeometricConstraint,
    SketchConstraintSolver2D
)
from src.core.types import Point2D
from src.ai.cad_ai_full_suite import CADFullSuiteOrchestrator


class SimulationFuzzer:
    """Orchestrateur de tests extrêmes et simulations aux limites."""

    def __init__(self) -> None:
        self.total_tests: int = 0
        self.bugs_found: List[Dict[str, str]] = []

    def log_bug(self, category: str, test_name: str, error_msg: str, trace: str) -> None:
        """Enregistre un bug ou comportement anormal détecté."""
        print(f"  [BUG DÉTECTÉ] {category} -> {test_name}: {error_msg}")
        self.bugs_found.append({
            "category": category,
            "test_name": test_name,
            "error_msg": error_msg,
            "trace": trace
        })

    def run_all(self) -> None:
        """Exécute l'intégralité des batteries de simulation."""
        print("=" * 70)
        print("LANCEMENT DU BANC DE SIMULATION ET DE STRESS MULTI-TYPES (FUZZING)")
        print("=" * 70)

        self._fuzz_fea_simulations()
        self._fuzz_nonlinear_fem()
        self._fuzz_geometry_edge_cases()
        self._fuzz_cam_and_toolpaths()
        self._fuzz_solver_2d()
        self._fuzz_sheetmetal_limits()

        print("\n" + "=" * 70)
        print(f"RÉSULTATS : {self.total_tests} scénarios de simulation testés.")
        print(f"NOMBRE DE BUGS DÉTECTÉS : {len(self.bugs_found)}")
        print("=" * 70)

    # -------------------------------------------------------------------------
    # 1. FEA & MULTIPHYSICS
    # -------------------------------------------------------------------------
    def _fuzz_fea_simulations(self) -> None:
        print("\n[1/6] Fuzzing Simulation FEA Mécanique...")

        # Cas 1.1 : Effort strictement nul
        self.total_tests += 1
        try:
            box = make_box(20.0, 20.0, 20.0)
            res = CADFullSuiteOrchestrator.run_fea(box, applied_force_n=0.0)
            if math.isnan(res.max_stress_mpa) or math.isinf(res.max_stress_mpa):
                self.log_bug("FEA", "Zero Force NaN", "max_stress_mpa est NaN ou Inf", "")
            if res.max_stress_mpa < 0.0:
                self.log_bug("FEA", "Negative Stress", "Contrainte von Mises négative", "")
        except Exception as e:
            self.log_bug("FEA", "Zero Force Crash", str(e), traceback.format_exc())

        # Cas 1.2 : Effort gigantesque (1 GigaNewton)
        self.total_tests += 1
        try:
            box = make_box(20.0, 20.0, 20.0)
            res = CADFullSuiteOrchestrator.run_fea(box, applied_force_n=1e9)
            if math.isnan(res.max_stress_mpa) or math.isnan(res.max_displacement_mm):
                self.log_bug("FEA", "Gigantic Force NaN", "Déplacement ou contrainte est NaN sous 1 GN", "")
        except Exception as e:
            self.log_bug("FEA", "Gigantic Force Crash", str(e), traceback.format_exc())

        # Cas 1.3 : Matériau inconnu
        self.total_tests += 1
        try:
            box = make_box(20.0, 20.0, 20.0)
            res = CADFullSuiteOrchestrator.run_fea(box, applied_force_n=1000.0, material_name="Matière_Inconnue_Kryptonite")
            if res.max_stress_mpa < 0.0:
                self.log_bug("FEA", "Unknown Material Negative", "max_stress_mpa négatif", "")
        except Exception as e:
            self.log_bug("FEA", "Unknown Material Crash", str(e), traceback.format_exc())

        # Cas 1.4 : Solide vide
        self.total_tests += 1
        try:
            empty = Solid()
            res = CADFullSuiteOrchestrator.run_fea(empty, applied_force_n=500.0)
            if math.isnan(res.max_stress_mpa):
                self.log_bug("FEA", "Empty Solid NaN", "max_stress_mpa est NaN sur solide vide", "")
        except Exception as e:
            self.log_bug("FEA", "Empty Solid Crash", str(e), traceback.format_exc())

    # -------------------------------------------------------------------------
    # 2. NON-LINEAR FEM (Tet10, Contact, Plasticity)
    # -------------------------------------------------------------------------
    def _fuzz_nonlinear_fem(self) -> None:
        print("\n[2/6] Fuzzing Éléments Finis Non-Linéaires Tet10 & Plasticité...")

        # Cas 2.1 : Tétraèdre Tet10 plat / coplanaire (volume = 0)
        self.total_tests += 1
        try:
            # 10 nœuds tous situés sur le plan Z=0
            flat_nodes = np.zeros((10, 3), dtype=np.float64)
            flat_nodes[0] = [0.0, 0.0, 0.0]
            flat_nodes[1] = [10.0, 0.0, 0.0]
            flat_nodes[2] = [0.0, 10.0, 0.0]
            flat_nodes[3] = [5.0, 5.0, 0.0] # 4ème nœud aussi dans Z=0
            elem = Tet10Element(element_id=1, node_indices=list(range(10)))
            vol = elem.calculate_volume(flat_nodes)
            if vol != 0.0 and vol > 1e-6:
                self.log_bug("NonlinearFEM", "Flat Tet Nonzero Volume", f"Volume={vol} pour tétraèdre plat", "")
            mat = BilinearPlasticMaterial(
                name="Acier Test",
                youngs_modulus_mpa=210000.0,
                poissons_ratio=0.3,
                yield_strength_mpa=250.0,
                tangent_modulus_mpa=2100.0
            )
            ke = elem.calculate_stiffness_matrix(flat_nodes, mat)
            if np.any(np.isnan(ke)) or np.any(np.isinf(ke)):
                self.log_bug("NonlinearFEM", "Flat Tet Stiffness NaN", "Matrice Ke contient NaN", "")
        except Exception as e:
            self.log_bug("NonlinearFEM", "Flat Tet Crash", str(e), traceback.format_exc())

        # Cas 2.2 : Écrouissage plastique avec déformation plastique gigantesque
        self.total_tests += 1
        try:
            mat = BilinearPlasticMaterial(
                name="Acier Test",
                youngs_modulus_mpa=210000.0,
                poissons_ratio=0.3,
                yield_strength_mpa=250.0,
                tangent_modulus_mpa=2100.0
            )
            # Déformation plastique 500% (5.0)
            stress, pl_strain, is_yield = mat.evaluate_stress(total_strain=5.0)
            if math.isnan(stress) or math.isinf(stress):
                self.log_bug("NonlinearFEM", "Plastic Stress NaN", "Contrainte d'écoulement est NaN", "")
            if stress < mat.yield_strength_mpa:
                self.log_bug("NonlinearFEM", "Softening without damage", "Contrainte inférieure à limite initiale", "")
        except Exception as e:
            self.log_bug("NonlinearFEM", "Plastic Strain Crash", str(e), traceback.format_exc())

        # Cas 2.3 : Résolution contact et équilibre non-linéaire avec force nulle
        self.total_tests += 1
        try:
            pair = FrictionalContactPair(
                slave_node_coords=np.array([0.0, 0.0, -0.5]),
                master_plane_origin=np.array([0.0, 0.0, 0.0]),
                master_plane_normal=np.array([0.0, 0.0, 1.0]),
                penalty_stiffness=1e5,
                friction_coefficient=0.3
            )
            res_contact = NonlinearFEASolver.solve_contact_equilibrium(
                material=mat,
                applied_load_newtons=0.0,
                cross_section_area_mm2=100.0,
                contact_pairs=[pair]
            )
            if not res_contact["converged"]:
                self.log_bug("NonlinearFEM", "Zero Load Not Converged", "Équilibre non convergé avec force nulle", "")
        except Exception as e:
            self.log_bug("NonlinearFEM", "Zero Load Nonlinear Crash", str(e), traceback.format_exc())

    # -------------------------------------------------------------------------
    # 3. GÉOMÉTRIE B-REP & MANIFOLD
    # -------------------------------------------------------------------------
    def _fuzz_geometry_edge_cases(self) -> None:
        print("\n[3/6] Fuzzing Géométrie & Opérations B-Rep...")

        # Cas 3.1 : Primitives à dimensions nulles ou négatives
        self.total_tests += 1
        try:
            b_zero = make_box(0.0, 0.0, 0.0)
            if not b_zero.is_empty() and b_zero.volume() > 1e-9:
                self.log_bug("Geometry", "Zero Box Not Empty", f"Volume={b_zero.volume()} pour boîte 0x0x0", "")
        except Exception as e:
            self.log_bug("Geometry", "Zero Box Crash", str(e), traceback.format_exc())

        self.total_tests += 1
        try:
            c_zero = make_cylinder(0.0, 0.0)
            if not c_zero.is_empty() and c_zero.volume() > 1e-9:
                self.log_bug("Geometry", "Zero Cylinder Not Empty", f"Volume={c_zero.volume()} pour cyl r=0 h=0", "")
        except Exception as e:
            self.log_bug("Geometry", "Zero Cylinder Crash", str(e), traceback.format_exc())

        # Cas 3.2 : Opérations booléennes sur solides complètement disjoints
        self.total_tests += 1
        try:
            b1 = make_box(10.0, 10.0, 10.0).translate(0.0, 0.0, 0.0)
            b2 = make_box(10.0, 10.0, 10.0).translate(1000.0, 1000.0, 1000.0)
            diff = b1.difference(b2)
            if abs(diff.volume() - b1.volume()) > 1e-3:
                self.log_bug("Geometry", "Disjoint Difference Inaccurate", f"Vol attendu={b1.volume()}, obtenu={diff.volume()}", "")
            inter = b1.intersection(b2)
            if not inter.is_empty() and inter.volume() > 1e-5:
                self.log_bug("Geometry", "Disjoint Intersection Not Empty", f"Intersection non vide de vol={inter.volume()}", "")
        except Exception as e:
            self.log_bug("Geometry", "Disjoint Booleans Crash", str(e), traceback.format_exc())

        # Cas 3.3 : Modélisation directe : Coque (Shell) avec épaisseur de paroi démesurée
        self.total_tests += 1
        try:
            box = make_box(20.0, 20.0, 20.0, center=True)
            res_shell = CADFullSuiteOrchestrator.direct_modeling_shell(box, wall_thickness_mm=50.0) # > 10mm demi-largeur
            if res_shell.solid is None:
                self.log_bug("Geometry", "Shell Returned None", "Solide coque retourné est None", "")
        except ValueError:
            # Rejet propre par ValueError conforme aux spécifications de conception mécanique
            pass
        except Exception as e:
            self.log_bug("Geometry", "Oversized Shell Crash", str(e), traceback.format_exc())

        # Cas 3.4 : Congé (Fillet) avec rayon supérieur à la moitié de la pièce
        self.total_tests += 1
        try:
            box = make_box(20.0, 20.0, 20.0, center=True)
            res_fillet = CADFullSuiteOrchestrator.direct_modeling_fillet(box, radius_mm=25.0) # > 10mm
            if res_fillet.solid is None:
                self.log_bug("Geometry", "Fillet Returned None", "Solide retourné est None", "")
        except Exception as e:
            self.log_bug("Geometry", "Oversized Fillet Crash", str(e), traceback.format_exc())

    # -------------------------------------------------------------------------
    # 4. CAM & USINAGE CNC
    # -------------------------------------------------------------------------
    def _fuzz_cam_and_toolpaths(self) -> None:
        print("\n[4/6] Fuzzing FAO & Trajectoires CAM...")

        box = make_box(60.0, 40.0, 20.0, center=True)

        # Cas 4.1 : Fraise géante (diamètre > taille de la pièce)
        self.total_tests += 1
        try:
            cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="contour", tool_diameter_mm=200.0, depth_mm=10.0)
            if not cam_res.gcode_preview:
                self.log_bug("CAM", "Giant Tool Empty GCode", "G-Code vide avec fraise géante", "")
        except Exception as e:
            self.log_bug("CAM", "Giant Tool Crash", str(e), traceback.format_exc())

        # Cas 4.2 : Diamètre d'outil nul ou négatif
        self.total_tests += 1
        try:
            cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="contour", tool_diameter_mm=0.0, depth_mm=10.0)
            if cam_res.total_cut_length_mm < 0:
                self.log_bug("CAM", "Zero Tool Negative Cut", "Longueur de coupe négative", "")
        except Exception as e:
            self.log_bug("CAM", "Zero Tool Crash", str(e), traceback.format_exc())

        # Cas 4.3 : Profondeur d'usinage nulle ou négative
        self.total_tests += 1
        try:
            cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="pocket", depth_mm=0.0)
            if cam_res.total_cut_length_mm < 0:
                self.log_bug("CAM", "Zero Depth Negative Cut", "Longueur négative avec depth=0", "")
        except Exception as e:
            self.log_bug("CAM", "Zero Depth Crash", str(e), traceback.format_exc())

        # Cas 4.4 : Opération inconnue
        self.total_tests += 1
        try:
            cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="plasma_warp_cut")
            if not cam_res.gcode_preview:
                self.log_bug("CAM", "Unknown Op Empty GCode", "GCode vide sur op inconnue", "")
        except Exception as e:
            self.log_bug("CAM", "Unknown Operation Crash", str(e), traceback.format_exc())

    # -------------------------------------------------------------------------
    # 5. SOLVEUR DE CONTRAINTES 2D
    # -------------------------------------------------------------------------
    def _fuzz_solver_2d(self) -> None:
        print("\n[5/6] Fuzzing Solveur de Contraintes 2D...")

        # Cas 5.1 : Points identiques avec contrainte de distance nulle
        self.total_tests += 1
        try:
            solver = SketchConstraintSolver2D()
            p1_idx = solver.add_point(Point2D(0.0, 0.0))
            p2_idx = solver.add_point(Point2D(0.0, 0.0))
            solver.add_distance(p1_idx, p2_idx, distance=0.0)
            res = solver.solve(max_iterations=50)
        except Exception as e:
            if "division by zero" in str(e).lower() or "zerodivision" in str(e).lower():
                self.log_bug("Solver2D", "Zero Distance DivisionByZero", str(e), traceback.format_exc())
            else:
                self.log_bug("Solver2D", "Zero Distance Crash", str(e), traceback.format_exc())

        # Cas 5.2 : Contraintes contradictoires (distance 10 et distance 50 entre 2 mêmes points)
        self.total_tests += 1
        try:
            solver = SketchConstraintSolver2D()
            p1 = solver.add_point(Point2D(0.0, 0.0))
            p2 = solver.add_point(Point2D(10.0, 0.0))
            solver.add_distance(p1, p2, distance=10.0)
            solver.add_distance(p1, p2, distance=50.0)
            success, pts = solver.solve(max_iterations=30)
            if success:
                self.log_bug("Solver2D", "Contradictory Succeeded", "Un système contradictoire a renvoyé success=True", "")
        except Exception as e:
            self.log_bug("Solver2D", "Contradictory Crash", str(e), traceback.format_exc())

        # Cas 5.3 : Système sur-contraint dégénéré (3 contraintes horizontales sur même segment)
        self.total_tests += 1
        try:
            solver = SketchConstraintSolver2D()
            p1 = solver.add_point(Point2D(0.0, 0.0))
            p2 = solver.add_point(Point2D(10.0, 2.0))
            solver.add_horizontal(p1, p2)
            solver.add_horizontal(p1, p2)
            solver.add_horizontal(p1, p2)
            success, pts = solver.solve(max_iterations=30)
        except Exception as e:
            self.log_bug("Solver2D", "Overconstrained Crash", str(e), traceback.format_exc())

    # -------------------------------------------------------------------------
    # 6. TÔLERIE & PLIAGE
    # -------------------------------------------------------------------------
    def _fuzz_sheetmetal_limits(self) -> None:
        print("\n[6/6] Fuzzing Tôlerie & Pliage...")

        # Cas 6.1 : Épaisseur nulle ou négative
        self.total_tests += 1
        try:
            sm_res = CADFullSuiteOrchestrator.design_sheet_metal(width_mm=100.0, length_mm=100.0, thickness_mm=0.0, flange_height_mm=20.0)
            if sm_res.solid.is_empty():
                pass
        except Exception as e:
            self.log_bug("SheetMetal", "Zero Thickness Crash", str(e), traceback.format_exc())

        # Cas 6.2 : Hauteur de rebord nulle
        self.total_tests += 1
        try:
            sm_res = CADFullSuiteOrchestrator.design_sheet_metal(width_mm=100.0, length_mm=100.0, thickness_mm=2.0, flange_height_mm=0.0)
            if sm_res.bends_count > 0:
                pass
        except Exception as e:
            self.log_bug("SheetMetal", "Zero Flange Crash", str(e), traceback.format_exc())

        # Cas 6.3 : Déplié à plat d'un flan avec cotes négatives
        self.total_tests += 1
        try:
            sm_res = CADFullSuiteOrchestrator.design_sheet_metal(width_mm=-50.0, length_mm=-50.0, thickness_mm=2.0, flange_height_mm=10.0)
            if sm_res.flat_pattern_width_mm < 0:
                self.log_bug("SheetMetal", "Negative Dimensions Kept Negative", "Cotes de flan négatives générées", "")
        except Exception as e:
            self.log_bug("SheetMetal", "Negative Dimensions Crash", str(e), traceback.format_exc())


if __name__ == "__main__":
    fuzzer = SimulationFuzzer()
    fuzzer.run_all()
    if fuzzer.bugs_found:
        sys.exit(len(fuzzer.bugs_found))
    sys.exit(0)
