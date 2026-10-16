"""
Tests de Performance et Non-Régression Temporelle (Apple-Grade Benchmarks).
Mesure et valide que les opérations critiques respectent des seuils stricts de latence
(Booléens CSG, Solveur 2D, Heatmap FEA, Arêtes vives, Rollback temporel O(1)).
"""

import time
import pytest
import numpy as np

from src.core.geometry import make_box, make_cylinder, _extract_sharp_edges
from src.core.types import Vector3D, Point2D
from src.core.feature import BoxFeature
from src.core.document import CADDocument
from src.core.parameters import SafeExpressionEvaluator
from src.fea.fea_solver import FEASimulator, _vectorized_colormap_jet
from src.solver.constraints_2d import SketchConstraintSolver2D


def test_benchmark_csg_boolean_speed() -> None:
    """Vérifie que l'union et la soustraction booléenne Manifold3D s'exécutent en moins de 50 ms."""
    b = make_box(30.0, 30.0, 30.0)
    c = make_cylinder(8.0, 40.0, center=True)

    t0 = time.perf_counter()
    diff = b.difference(c)
    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000.0

    assert not diff.is_empty()
    assert duration_ms < 50.0  # Doit être quasi-instantané (< 50 ms)


def test_benchmark_solver_2d_convergence_speed() -> None:
    """Vérifie que la résolution d'une esquisse à 6 contraintes prend moins de 30 ms."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(25.0, 2.0))
    p2 = solver.add_point(Point2D(24.0, 31.0))
    p3 = solver.add_point(Point2D(-1.0, 30.0))

    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_horizontal(p0, p1)
    solver.add_vertical(p0, p3)
    solver.add_distance(p0, p1, 50.0)
    solver.add_distance(p0, p3, 30.0)
    solver.add_equal(p0, p1, p3, p2)

    t0 = time.perf_counter()
    success, _ = solver.solve()
    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000.0

    assert success
    assert duration_ms < 30.0


def test_benchmark_vectorized_fea_colormap_speed() -> None:
    """Vérifie que la colormap vectorisée traite 20 000 sommets en moins de 10 ms."""
    vals = np.linspace(0.0, 1.0, 20000, dtype=np.float32)

    t0 = time.perf_counter()
    rgba = _vectorized_colormap_jet(vals)
    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000.0

    assert rgba.shape == (20000, 4)
    assert duration_ms < 10.0


def test_benchmark_extract_sharp_edges_speed() -> None:
    """Vérifie que l'extraction dièdre vectorisée des arêtes vives s'exécute en moins de 15 ms."""
    box = make_box(20.0, 20.0, 20.0)
    mesh = box.manifold.to_mesh()
    tri_verts = np.array(mesh.tri_verts, dtype=np.uint32)
    # 12 triangles pour un cube
    face_normals = np.zeros((len(tri_verts), 3), dtype=np.float32)

    t0 = time.perf_counter()
    edges = _extract_sharp_edges(tri_verts, face_normals, angle_threshold_deg=20.0)
    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000.0

    assert len(edges) > 0
    assert duration_ms < 15.0


def test_benchmark_expression_evaluator_throughput() -> None:
    """Vérifie que l'évaluateur d'expressions mathématiques dépasse 5 000 évaluations / seconde."""
    ctx = {"length": 50.0, "width": 20.0}
    expr = "sqrt(length ** 2 + width ** 2) + 10mm"

    n_evals = 2000
    t0 = time.perf_counter()
    for _ in range(n_evals):
        SafeExpressionEvaluator.evaluate(expr, ctx)
    t1 = time.perf_counter()

    elapsed = max(1e-6, t1 - t0)
    evals_per_sec = n_evals / elapsed
    assert evals_per_sec > 5000.0


def test_benchmark_rollback_cache_instant_restoration() -> None:
    """Vérifie que la restauration d'instantané depuis le cache se fait en O(1) (< 2 ms)."""
    doc = CADDocument("RollbackBench")
    for i in range(10):
        doc.add_feature(BoxFeature(f"b{i}", f"Box_{i}", width=10, height=10, depth=10))

    # Premier calcul remplit le cache
    doc.set_rollback_index(5)

    # Restauration instantanée O(1)
    t0 = time.perf_counter()
    doc.set_rollback_index(5)
    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000.0

    assert len(doc.bodies) >= 1
    assert duration_ms < 2.0
