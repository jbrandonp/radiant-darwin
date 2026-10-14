"""
Suite de tests de résistance, stress testing et simulations multi-types (Multi-Type Simulation Suite).
Valide la résilience du noyau CAO/FAO/FEA face aux cas limites et sollicitations extrêmes :
1. FEA & Éléments Finis : chargements nuls, gigantisme, solides vides.
2. Éléments Finis Non-Linéaires (Tet10, Plasticité, Contact Frottant).
3. Géométrie B-Rep : dimensions nulles, intersections disjointes, coques et congés limites.
4. FAO / CAM : outils géants, profondeurs nulles, opérations inconnues.
5. Solveur de Contraintes 2D : systèmes contradictoires, segments superposés, sur-contraintes.
6. Tôlerie industrielle : cotes limites et déplié flan.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.geometry import Solid, make_box, make_cylinder, make_sphere, make_cone
from src.core.types import Point2D
from src.fea.fea_solver import FEASimulator
from src.fea.nonlinear_fem import (
    Tet10Element,
    BilinearPlasticMaterial,
    FrictionalContactPair,
    NonlinearFEASolver
)
from src.cam.cam_engine import CAMEngine, CNCTool, ToolType
from src.solver.constraints_2d import (
    ConstraintType,
    GeometricConstraint,
    SketchConstraintSolver2D
)
from src.ai.cad_ai_full_suite import CADFullSuiteOrchestrator


class TestFEAMultiphysicsStress:
    """Vérifie la robustesse de l'analyseur par éléments finis."""

    def test_zero_applied_force(self) -> None:
        box = make_box(20.0, 20.0, 20.0)
        res = CADFullSuiteOrchestrator.run_fea(box, applied_force_n=0.0)
        assert not math.isnan(res.max_stress_mpa)
        assert not math.isinf(res.max_stress_mpa)
        assert res.max_stress_mpa >= 0.0

    def test_gigantic_applied_force(self) -> None:
        box = make_box(20.0, 20.0, 20.0)
        res = CADFullSuiteOrchestrator.run_fea(box, applied_force_n=1e9)
        assert not math.isnan(res.max_stress_mpa)
        assert not math.isnan(res.max_displacement_mm)
        assert res.is_safe is False

    def test_unknown_material_fallback(self) -> None:
        box = make_box(20.0, 20.0, 20.0)
        res = CADFullSuiteOrchestrator.run_fea(box, applied_force_n=1000.0, material_name="Matiere_Inconnue_X")
        assert res.max_stress_mpa >= 0.0

    def test_empty_solid_fea(self) -> None:
        empty = Solid()
        res = CADFullSuiteOrchestrator.run_fea(empty, applied_force_n=500.0)
        assert res.is_safe is False
        assert "Solide vide" in res.status_verdict


class TestNonlinearFEMAndPlasticity:
    """Vérifie la robustesse des modèles de plasticité et contact."""

    def test_flat_degenerate_tet10_element(self) -> None:
        flat_nodes = np.zeros((10, 3), dtype=np.float64)
        flat_nodes[0] = [0.0, 0.0, 0.0]
        flat_nodes[1] = [10.0, 0.0, 0.0]
        flat_nodes[2] = [0.0, 10.0, 0.0]
        flat_nodes[3] = [5.0, 5.0, 0.0]
        elem = Tet10Element(element_id=1, node_indices=list(range(10)))
        vol = elem.calculate_volume(flat_nodes)
        assert vol == pytest.approx(0.0)

        mat = BilinearPlasticMaterial(name="Acier", youngs_modulus_mpa=210000.0, poissons_ratio=0.3, yield_strength_mpa=250.0)
        ke = elem.calculate_stiffness_matrix(flat_nodes, mat)
        assert not np.any(np.isnan(ke))

    def test_plastic_hardening_monotonicity(self) -> None:
        mat = BilinearPlasticMaterial(name="Acier", youngs_modulus_mpa=210000.0, poissons_ratio=0.3, yield_strength_mpa=250.0, tangent_modulus_mpa=2100.0)
        stress, pl_strain, is_yield = mat.evaluate_stress(total_strain=5.0)
        assert not math.isnan(stress)
        assert is_yield is True
        assert stress >= mat.yield_strength_mpa

    def test_contact_equilibrium_zero_load(self) -> None:
        mat = BilinearPlasticMaterial(name="Acier", youngs_modulus_mpa=210000.0, poissons_ratio=0.3, yield_strength_mpa=250.0)
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
        assert res_contact["converged"] is True


class TestGeometryBRepEdgeCases:
    """Vérifie la robustesse des opérations géométriques face aux singularités."""

    def test_zero_and_negative_dimension_primitives(self) -> None:
        b_zero = make_box(0.0, 0.0, 0.0)
        assert b_zero.is_manifold() is True
        assert b_zero.volume() > 0.0

        c_zero = make_cylinder(0.0, 0.0)
        assert c_zero.is_manifold() is True
        assert c_zero.volume() > 0.0

        s_zero = make_sphere(-5.0)
        assert s_zero.is_manifold() is True
        assert s_zero.volume() > 0.0

        cone_zero = make_cone(0.0, 0.0, 0.0)
        assert cone_zero.is_manifold() is True
        assert cone_zero.volume() > 0.0

    def test_disjoint_boolean_operations(self) -> None:
        b1 = make_box(10.0, 10.0, 10.0)
        b2 = make_box(10.0, 10.0, 10.0).translate(1000.0, 1000.0, 1000.0)
        diff = b1.difference(b2)
        assert diff.volume() == pytest.approx(b1.volume(), rel=1e-3)
        inter = b1.intersection(b2)
        assert inter.is_empty() is True or inter.volume() < 1e-5

    def test_oversized_shell_rejection(self) -> None:
        box = make_box(20.0, 20.0, 20.0, center=True)
        with pytest.raises(ValueError) as exc_info:
            CADFullSuiteOrchestrator.direct_modeling_shell(box, wall_thickness_mm=50.0)
        assert "dépasse la géométrie" in str(exc_info.value)

    def test_oversized_fillet_handling(self) -> None:
        box = make_box(20.0, 20.0, 20.0, center=True)
        res_fillet = CADFullSuiteOrchestrator.direct_modeling_fillet(box, radius_mm=25.0)
        assert res_fillet.solid is not None


class TestCAMAndToolpathStress:
    """Vérifie la robustesse du générateur de trajectoires d'usinage."""

    def test_giant_tool_cam(self) -> None:
        box = make_box(60.0, 40.0, 20.0, center=True)
        cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="contour", tool_diameter_mm=200.0, depth_mm=10.0)
        assert cam_res.gcode_preview != ""

    def test_zero_tool_diameter(self) -> None:
        box = make_box(60.0, 40.0, 20.0, center=True)
        cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="contour", tool_diameter_mm=0.0, depth_mm=10.0)
        assert cam_res.total_cut_length_mm >= 0.0

    def test_zero_depth(self) -> None:
        box = make_box(60.0, 40.0, 20.0, center=True)
        cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="pocket", depth_mm=0.0)
        assert cam_res.total_cut_length_mm >= 0.0

    def test_unknown_operation_fallback(self) -> None:
        box = make_box(60.0, 40.0, 20.0, center=True)
        cam_res = CADFullSuiteOrchestrator.run_cam(box, operation_type="plasma_laser_unknown")
        assert cam_res.gcode_preview != ""


class TestSolver2DStressAndDegeneracy:
    """Vérifie la robustesse du solveur de contraintes 2D."""

    def test_zero_distance_identical_points(self) -> None:
        solver = SketchConstraintSolver2D()
        p1 = solver.add_point(Point2D(0.0, 0.0))
        p2 = solver.add_point(Point2D(0.0, 0.0))
        solver.add_distance(p1, p2, distance=0.0)
        success, pts = solver.solve(max_iterations=50)
        assert len(pts) == 2

    def test_contradictory_constraints(self) -> None:
        solver = SketchConstraintSolver2D()
        p1 = solver.add_point(Point2D(0.0, 0.0))
        p2 = solver.add_point(Point2D(10.0, 0.0))
        solver.add_distance(p1, p2, distance=10.0)
        solver.add_distance(p1, p2, distance=50.0)
        success, pts = solver.solve(max_iterations=30)
        assert success is False

    def test_redundant_horizontal_constraints(self) -> None:
        solver = SketchConstraintSolver2D()
        p1 = solver.add_point(Point2D(0.0, 0.0))
        p2 = solver.add_point(Point2D(10.0, 2.0))
        solver.add_horizontal(p1, p2)
        solver.add_horizontal(p1, p2)
        solver.add_horizontal(p1, p2)
        success, pts = solver.solve(max_iterations=30)
        assert success is True


class TestSheetMetalEdgeCases:
    """Vérifie la robustesse des opérations de tôlerie industrielle."""

    def test_zero_thickness(self) -> None:
        sm_res = CADFullSuiteOrchestrator.design_sheet_metal(width_mm=100.0, length_mm=100.0, thickness_mm=0.0, flange_height_mm=20.0)
        assert sm_res.solid is not None

    def test_zero_flange_height(self) -> None:
        sm_res = CADFullSuiteOrchestrator.design_sheet_metal(width_mm=100.0, length_mm=100.0, thickness_mm=2.0, flange_height_mm=0.0)
        assert sm_res.solid is not None
