"""
Suite de Tests Unitaires et de Validation d'Invariants pour NEXUS-3D (AI Geometric Kernel).
Vérifie la rigueur de la topologie B-Rep, les courbures analytiques continues,
la robustesse des booléens hybrides, le moteur Neural SDF, les Jacobiennes différentiables
et les représentations GNN / Tokens pour agents IA.
Typage strict exhaustif, zéro Any, zéro object.
"""

from __future__ import annotations
import numpy as np
import pytest

from src.core.nexus_kernel import (
    SurfaceType, CurveType, NexusVertex, NexusLineCurve, NexusCircleCurve,
    NexusEdge, NexusWire, NexusPlaneSurface, NexusCylinderSurface, NexusSphereSurface,
    NexusFace, NexusShell, NexusBRep, NexusSolid, NeuralSDFEngine,
    DifferentiableGeometryEngine, CADTokenizer, LatentShapeEmbedding
)
from src.core.geometry import make_box, Solid


def test_nexus_brep_euler_characteristic() -> None:
    """Vérifie le théorème d'Euler-Poincaré V - E + F = 2 sur un cube B-Rep exact."""
    box = NexusSolid.make_box(10.0, 20.0, 30.0, name="EulerBox")
    summary = box.brep.to_summary_dict()

    assert summary["vertex_count"] == 8
    assert summary["edge_count"] == 12
    assert summary["face_count"] == 6
    assert summary["euler_characteristic"] == 2
    assert box.brep.is_euler_valid(expected_genus=0) is True


def test_nexus_surface_analytical_curvatures() -> None:
    """Vérifie l'exactitude des courbures analytiques gaussiennes et moyennes."""
    # 1. Plan
    plane = NexusPlaneSurface("Plane1", np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]))
    assert plane.gaussian_curvature(0.0, 0.0) == 0.0
    assert plane.mean_curvature(0.0, 0.0) == 0.0
    assert np.allclose(plane.normal(10.0, 5.0), [0.0, 0.0, 1.0])

    # 2. Cylindre de rayon R=10
    r_cyl = 10.0
    cyl = NexusCylinderSurface("Cyl1", np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), r_cyl)
    assert cyl.gaussian_curvature(0.0, 5.0) == 0.0  # Développable
    assert pytest.approx(cyl.mean_curvature(0.0, 5.0), rel=1e-5) == 1.0 / (2.0 * r_cyl)

    # 3. Sphère de rayon R=5
    r_sph = 5.0
    sph = NexusSphereSurface("Sph1", np.array([0.0, 0.0, 0.0]), r_sph)
    assert pytest.approx(sph.gaussian_curvature(0.0, 0.0), rel=1e-5) == 1.0 / (r_sph ** 2)
    assert pytest.approx(sph.mean_curvature(0.0, 0.0), rel=1e-5) == 1.0 / r_sph


def test_nexus_curve_analytical_properties() -> None:
    """Vérifie les courbes analytiques 3D continues (segments et cercles)."""
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([10.0, 0.0, 0.0])
    line = NexusLineCurve("L1", p0, p1)
    assert line.length() == 10.0
    assert np.allclose(line.evaluate(0.5), [5.0, 0.0, 0.0])
    assert np.allclose(line.tangent(0.5), [1.0, 0.0, 0.0])

    circle = NexusCircleCurve("C1", p0, np.array([0.0, 0.0, 1.0]), radius=5.0)
    assert pytest.approx(circle.length(), rel=1e-5) == 2.0 * np.pi * 5.0
    # À t=0, point sur l'axe U
    pt0 = circle.evaluate(0.0)
    assert pytest.approx(np.linalg.norm(pt0), rel=1e-5) == 5.0


def test_nexus_hybrid_solid_primitives_and_booleans() -> None:
    """Vérifie la robustesse des opérations booléennes hybrides duales."""
    box = NexusSolid.make_box(20.0, 20.0, 20.0, name="BoxA")
    assert pytest.approx(box.volume(), rel=1e-3) == 8000.0
    assert box.is_watertight() is True

    cyl = NexusSolid.make_cylinder(radius=5.0, height=30.0, name="CylTool")
    assert cyl.volume() > 2000.0
    assert cyl.is_watertight() is True

    # Soustraction sans échec
    cut = box.difference(cyl, name="PercedBox")
    assert cut.volume() < 8000.0
    assert cut.is_watertight() is True

    # Union
    fused = box.union(cyl, name="FusedShape")
    assert fused.volume() > 8000.0
    assert fused.is_watertight() is True


def test_neural_sdf_engine() -> None:
    """Vérifie le calcul du champ de distance signée (SDF) et de ses gradients."""
    box = NexusSolid.make_box(10.0, 10.0, 10.0)

    # Point intérieur : d < 0
    pts_in = np.array([[5.0, 5.0, 5.0]], dtype=np.float64)
    sdf_in = NeuralSDFEngine.compute_signed_distance(box, pts_in)
    assert sdf_in[0] < -0.1

    # Point extérieur : d > 0
    pts_out = np.array([[20.0, 5.0, 5.0]], dtype=np.float64)
    sdf_out = NeuralSDFEngine.compute_signed_distance(box, pts_out)
    assert sdf_out[0] > 5.0

    # Gradient spatial unitaire
    grads = NeuralSDFEngine.compute_spatial_gradients(box, pts_out)
    assert pytest.approx(float(np.linalg.norm(grads[0])), rel=1e-3) == 1.0


def test_differentiable_geometry_engine() -> None:
    """Vérifie les Jacobiennes exactes de volume pour l'optimisation par gradient."""
    # Boîte : dV/ddx = dy * dz = 20 * 30 = 600
    grad_box = DifferentiableGeometryEngine.compute_volume_gradient_box(10.0, 20.0, 30.0)
    assert pytest.approx(grad_box[0]) == 600.0
    assert pytest.approx(grad_box[1]) == 300.0
    assert pytest.approx(grad_box[2]) == 200.0

    # Cylindre : dV/dr = 2*pi*r*h, dV/dh = pi*r^2
    r, h = 5.0, 10.0
    grad_cyl = DifferentiableGeometryEngine.compute_volume_gradient_cylinder(r, h)
    assert pytest.approx(grad_cyl[0], rel=1e-5) == 2.0 * np.pi * r * h
    assert pytest.approx(grad_cyl[1], rel=1e-5) == np.pi * (r ** 2)

    # Sphère : dV/dr = 4*pi*r^2
    grad_sph = DifferentiableGeometryEngine.compute_volume_gradient_sphere(4.0)
    assert pytest.approx(grad_sph, rel=1e-5) == 4.0 * np.pi * (4.0 ** 2)


def test_cad_tokenizer_and_gnn_graph() -> None:
    """Vérifie la tokenisation pour LLM et l'exportation de graphe GNN."""
    box = NexusSolid.make_box(10.0, 20.0, 30.0, name="TokenBox")
    tokens = CADTokenizer.tokenize(box)

    assert "<SOLID_START>" in tokens
    assert "NAME:TokenBox" in tokens
    assert "V:8" in tokens
    assert "E:12" in tokens
    assert "F:6" in tokens
    assert "EULER:2" in tokens
    assert "<SOLID_END>" in tokens

    # GNN Graph Adjacency
    gnn = CADTokenizer.to_gnn_adjacency(box)
    assert gnn["node_features"].shape == (8, 3)
    assert gnn["edge_index"].shape[0] == 2
    assert gnn["edge_index"].shape[1] == 24  # 12 arêtes * 2 directions


def test_latent_shape_embedding() -> None:
    """Vérifie la génération du vecteur d'empreinte latent de taille 64."""
    box1 = NexusSolid.make_box(10.0, 20.0, 30.0)
    emb1 = LatentShapeEmbedding.compute_embedding(box1, embedding_dim=64)
    assert emb1.shape == (64,)
    assert pytest.approx(float(np.linalg.norm(emb1)), rel=1e-3) == 1.0

    # Deux boîtes homothétiques doivent avoir une similarité cosinus très élevée (> 0.95)
    box2 = NexusSolid.make_box(20.0, 40.0, 60.0)
    emb2 = LatentShapeEmbedding.compute_embedding(box2, embedding_dim=64)
    similarity = float(np.dot(emb1, emb2))
    assert similarity > 0.95


def test_solid_to_nexus_bridges() -> None:
    """Vérifie les méthodes passerelles ajoutées sur la classe Solid existante."""
    legacy_solid = make_box(15.0, 25.0, 35.0, name="LegacyBox")
    nexus_sol = legacy_solid.to_nexus()

    assert nexus_sol.volume() > 0.0
    assert len(legacy_solid.get_ai_tokens()) > 5
    assert legacy_solid.get_latent_embedding().shape == (64,)

    query_pts = np.array([[7.5, 12.5, 17.5]], dtype=np.float64)
    sdf_val = legacy_solid.compute_sdf(query_pts)
    assert sdf_val[0] < 0.0  # Intérieur
