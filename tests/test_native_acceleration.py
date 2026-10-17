"""
Tests unitaires pour le moteur d'accélération native hybride (src/core/nexus_kernel/native_accel.py).
Validation des prédicats géométriques, quadrature, arbres d'intervalles et recherche NURBS.
"""

from __future__ import annotations
import numpy as np
import pytest

from src.core.nexus_kernel.native_accel import (
    NativeAccelerationEngine,
    AccelerationBackend,
    accelerated_orient2d,
    accelerated_orient3d,
    accelerated_interval_overlap,
    accelerated_saye_quadrature,
    accelerated_nurbs_knot_span,
)


def test_accelerated_orient2d() -> None:
    """Vérifie l'exactitude du prédicat d'orientation 2D."""
    # Triangle anti-horaire (CCW)
    res_ccw = accelerated_orient2d(0.0, 0.0, 10.0, 0.0, 0.0, 10.0)
    assert res_ccw > 0.0

    # Triangle horaire (CW)
    res_cw = accelerated_orient2d(0.0, 0.0, 0.0, 10.0, 10.0, 0.0)
    assert res_cw < 0.0

    # Points alignés (colinéaires)
    res_collinear = accelerated_orient2d(0.0, 0.0, 5.0, 5.0, 10.0, 10.0)
    assert abs(res_collinear) < 1e-12


def test_accelerated_orient3d() -> None:
    """Vérifie le prédicat d'orientation 3D tétraédrique."""
    # Point D au-dessus du plan XY (z > 0)
    res_above = accelerated_orient3d(
        0.0, 0.0, 0.0,
        10.0, 0.0, 0.0,
        0.0, 10.0, 0.0,
        5.0, 5.0, 10.0
    )
    assert res_above != 0.0

    # Point coplanaire au plan XY
    res_coplanar = accelerated_orient3d(
        0.0, 0.0, 0.0,
        10.0, 0.0, 0.0,
        0.0, 10.0, 0.0,
        5.0, 5.0, 0.0
    )
    assert abs(res_coplanar) < 1e-12


def test_accelerated_interval_overlap() -> None:
    """Vérifie la détection vectorisée de chevauchement d'intervalles."""
    intervals = np.array([
        [0.0, 5.0],
        [10.0, 15.0],
        [4.0, 12.0],
        [20.0, 30.0]
    ], dtype=np.float64)

    # Fenêtre [4.5, 11.0] doit toucher les intervalles 0, 1 et 2
    hits = accelerated_interval_overlap(intervals, 4.5, 11.0)
    assert 0 in hits
    assert 1 in hits
    assert 2 in hits
    assert 3 not in hits

    # Cas vide
    empty_hits = accelerated_interval_overlap(np.empty((0, 2)), 0.0, 1.0)
    assert len(empty_hits) == 0


def test_accelerated_saye_quadrature() -> None:
    """Vérifie le produit scalaire vectorisé de la règle de Saye."""
    vals = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    weights = np.array([0.25, 0.25, 0.25, 0.25], dtype=np.float64)
    result = accelerated_saye_quadrature(vals, weights)
    assert abs(result - 2.5) < 1e-6


def test_accelerated_nurbs_knot_span() -> None:
    """Vérifie la recherche d'intervalle de nœuds NURBS."""
    # Degré 2, 6 points de contrôle (n = 5), 9 nœuds
    knots = np.array([0.0, 0.0, 0.0, 0.25, 0.5, 0.75, 1.0, 1.0, 1.0], dtype=np.float64)

    span = accelerated_nurbs_knot_span(n=5, p=2, u=0.4, knots=knots)
    assert span == 3  # [0.25, 0.5)

    span_max = accelerated_nurbs_knot_span(n=5, p=2, u=1.0, knots=knots)
    assert span_max == 5


def test_native_acceleration_engine_singleton_and_bench() -> None:
    """Vérifie le statut et le micro-benchmark de débit du moteur."""
    engine = NativeAccelerationEngine.get_instance()
    status = engine.get_status()

    assert "backend" in status
    assert status["predicates_accelerated"] is True
    assert status["quadrature_accelerated"] is True
    assert status["nurbs_accelerated"] is True

    bench = engine.benchmark_speedup(iterations=500)
    assert bench["orient2d_ops_per_sec"] > 1000.0
    assert bench["nurbs_knot_ops_per_sec"] > 1000.0
