"""
Tests unitaires pour le solveur de contraintes géométriques 2D.
"""

import pytest
import numpy as np

from src.core.types import Point2D
from src.solver.constraints_2d import SketchConstraintSolver2D
from src.solver.live_drag_solver import (
    LiveDragSolver,
    DragConstraint,
    DragConstraintType,
    DofDiagnosticStatus,
    diagnose_degrees_of_freedom,
)



def test_solve_horizontal_and_vertical() -> None:
    """Vérifie la résolution simultanée de contraintes horizontale et verticale."""
    solver = SketchConstraintSolver2D()
    # 3 points formant un triangle rectangle
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 1.0))
    p2 = solver.add_point(Point2D(10.0, 15.0))

    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_horizontal(p0, p1)
    solver.add_vertical(p1, p2)
    solver.add_distance(p0, p1, 20.0)
    solver.add_distance(p1, p2, 10.0)

    success, pts = solver.solve()
    assert success
    assert pytest.approx(pts[0].u, abs=1e-3) == 0.0
    assert pytest.approx(pts[0].v, abs=1e-3) == 0.0

    # p1 doit être à v = 0 et u = 20
    assert pytest.approx(pts[1].u, abs=1e-3) == 20.0
    assert pytest.approx(pts[1].v, abs=1e-3) == 0.0

    # p2 doit être à u = 20 et v = 10
    assert pytest.approx(pts[2].u, abs=1e-3) == 20.0
    assert pytest.approx(pts[2].v, abs=1e-3) == 10.0


def test_solve_coincident() -> None:
    """Vérifie la contrainte de coïncidence de deux points."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(5.0, 5.0))
    p1 = solver.add_point(Point2D(12.0, 8.0))

    solver.add_fixed(p0, 5.0, 5.0)
    solver.add_coincident(p0, p1)

    success, pts = solver.solve()
    assert success
    assert pytest.approx(pts[1].u, 1e-4) == pts[0].u
    assert pytest.approx(pts[1].v, 1e-4) == pts[0].v


def test_solve_parallel() -> None:
    """Vérifie la contrainte de parallélisme entre deux segments 2D."""
    solver = SketchConstraintSolver2D()
    # Segment 1 : horizontal sur l'axe U
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_fixed(p1, 10.0, 0.0)

    # Segment 2 : p2 fixé à (0, 5), p3 initialement incliné à (10, 8)
    p2 = solver.add_point(Point2D(0.0, 5.0))
    p3 = solver.add_point(Point2D(10.0, 8.0))
    solver.add_fixed(p2, 0.0, 5.0)
    solver.add_distance(p2, p3, 10.0)
    solver.add_parallel(p0, p1, p2, p3)

    success, pts = solver.solve()
    assert success
    # Segment 2 doit être horizontal (v(p3) == v(p2) == 5.0, u(p3) == 10.0)
    assert pytest.approx(pts[3].v, abs=1e-3) == 5.0
    assert pytest.approx(pts[3].u, abs=1e-3) == 10.0


def test_solve_perpendicular() -> None:
    """Vérifie la contrainte de perpendicularité entre deux segments 2D."""
    solver = SketchConstraintSolver2D()
    # Segment 1 : horizontal
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_fixed(p1, 10.0, 0.0)

    # Segment 2 : p2 fixé à (5, 5), p3 fixé à v=15 mais libre en u
    p2 = solver.add_point(Point2D(5.0, 5.0))
    p3 = solver.add_point(Point2D(8.0, 15.0))
    solver.add_fixed(p2, 5.0, 5.0)
    solver.add_distance(p2, p3, 10.0)
    solver.add_perpendicular(p0, p1, p2, p3)

    success, pts = solver.solve()
    assert success
    # Segment 2 perpendiculaire à l'horizontale => vertical => u(p3) == 5.0
    assert pytest.approx(pts[3].u, abs=1e-3) == 5.0
    assert pytest.approx(pts[3].v, abs=1e-3) == 15.0


def test_solver_package_facade_reexports() -> None:
    """Vérifie que le package src.solver expose de manière intègre les solveurs 2D et DDL."""
    import src.solver as slv

    expected_symbols = [
        "ConstraintType",
        "GeometricConstraint",
        "GeometricConstraint2D",
        "SketchConstraintSolver2D",
        "DragConstraintType",
        "DofDiagnosticStatus",
        "DofDiagnosticResult",
        "DragConstraint",
        "diagnose_degrees_of_freedom",
        "LiveDragSolver",
    ]
    for sym in expected_symbols:
        assert hasattr(slv, sym), f"Le symbole {sym} doit être exposé par src.solver"
        assert getattr(slv, sym) is not None


def test_live_drag_solver_and_dof() -> None:
    """Vérifie le solveur temps réel de glisser-déplacer et le calcul de DDL."""
    from src.solver import (
        LiveDragSolver,
        DragConstraint,
        DragConstraintType,
        diagnose_degrees_of_freedom,
        DofDiagnosticStatus,
    )

    # 1. Diagnostic DoF : 2 points (4 DDL), 3 contraintes -> 1 DDL restant
    dof_res = diagnose_degrees_of_freedom(num_points=2, num_independent_constraints=3)
    assert dof_res.status == DofDiagnosticStatus.UNDER_CONSTRAINED
    assert dof_res.degrees_of_freedom == 1

    # 4 DDL et 4 contraintes -> Entièrement contraint (0 DDL)
    dof_res_fully = diagnose_degrees_of_freedom(num_points=2, num_independent_constraints=4)
    assert dof_res_fully.status == DofDiagnosticStatus.FULLY_CONSTRAINED
    assert dof_res_fully.degrees_of_freedom == 0

    # 2. Glisser-déplacer interactif
    drag_solver = LiveDragSolver(tolerance=1e-5)
    c_horiz = DragConstraint(
        id="c_h",
        constraint_type=DragConstraintType.HORIZONTAL,
        entity_indices=(1,),
        target_val=12.5
    )
    res_pos = drag_solver.live_drag_step(
        dragged_index=1,
        target_pos=Point2D(45.0, 99.0),
        active_constraints=[c_horiz]
    )
    assert res_pos.x == 45.0
    assert res_pos.y == 12.5


def test_live_drag_coincident_2d_point() -> None:
    """Vérifie la projection exacte sur un point 2D (target_pos) sans contrainte diagonale x=y."""
    drag_solver = LiveDragSolver(tolerance=1e-5)
    c_coinc = DragConstraint(
        id="c_pt",
        constraint_type=DragConstraintType.COINCIDENT,
        entity_indices=(2,),
        target_pos=Point2D(12.3, 45.6)
    )
    res_pos = drag_solver.live_drag_step(
        dragged_index=2,
        target_pos=Point2D(100.0, 200.0),
        active_constraints=[c_coinc]
    )
    assert pytest.approx(res_pos.x, 1e-4) == 12.3
    assert pytest.approx(res_pos.y, 1e-4) == 45.6


def test_unified_sketch_solver_facade() -> None:
    """Vérifie que la façade unifiée orchestre à la fois le mode interactif et le mode rigoureux."""
    from src.solver.unified_solver import UnifiedSketchSolver, SolverMode
    solver = UnifiedSketchSolver()
    assert solver.interactive_solver is not None
    assert solver.rigorous_solver is not None

    # Test mode interactif via façade
    c_vert = DragConstraint(
        id="c_v",
        constraint_type=DragConstraintType.VERTICAL,
        entity_indices=(0,),
        target_val=33.0
    )
    dragged = solver.solve_interactive_drag(
        dragged_index=0,
        target_pos=Point2D(0.0, 88.0),
        active_constraints=[c_vert]
    )
    assert pytest.approx(dragged.x, 1e-4) == 33.0
    assert pytest.approx(dragged.y, 1e-4) == 88.0

    # Test diagnostic via façade
    diag = solver.diagnose_dof(num_points=3, num_independent_constraints=6)
    assert diag.degrees_of_freedom == 0
    assert diag.status.value == "fully_constrained"


def test_planegcs_algebraic_constraint_diagnosis() -> None:
    """Vérifie le diagnostic algébrique exact (FreeCAD PlaneGCS) isolant redondances et conflits."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(10.0, 0.0))

    # C0: Horizontale entre p0 et p1 (v0 = v1)
    solver.add_horizontal(p0, p1)
    # C1: Fixe p0 à (0, 0) (u0 = 0, v0 = 0)
    solver.add_fixed(p0, 0.0, 0.0)
    # C2: Fixe p1 à (10, 0) (u1 = 10, v1 = 0) -> Rendant C0 redondante !
    solver.add_fixed(p1, 10.0, 0.0)

    report = solver.diagnose_constraints()
    assert report.degrees_of_freedom == 0
    assert report.is_overconstrained is True
    assert 2 in report.redundant_constraint_indices  # La contrainte 2 contient une dépendance redondante sur v1

    # Maintenant, créons un conflit direct
    solver_conflict = SketchConstraintSolver2D()
    pa = solver_conflict.add_point(Point2D(0.0, 0.0))
    pb = solver_conflict.add_point(Point2D(10.0, 0.0))

    solver_conflict.add_horizontal(pa, pb)
    solver_conflict.add_fixed(pa, 0.0, 0.0)
    # En conflit violent avec l'horizontalité car v_b = 5.0 alors que v_a = 0.0
    solver_conflict.add_fixed(pb, 10.0, 5.0)

    conf_report = solver_conflict.diagnose_constraints()
    assert len(conf_report.conflicting_constraint_indices) > 0
    assert 2 in conf_report.conflicting_constraint_indices


