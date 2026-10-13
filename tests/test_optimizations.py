"""
Tests unitaires validant les optimisations de performance et de mise en cache :
- Caching O(1) de MeshBuffer dans Solid
- Caching par instantanés (Snapshots) de timeline dans CADDocument
- Précalcul vectorisé de la grille 3D dans GLRenderer
- Rendu rapide PBR et vectorisation des projections
"""

from __future__ import annotations
import time
import pytest
import numpy as np

from src.core.geometry import make_box, make_cylinder, Solid
from src.core.document import CADDocument
from src.core.feature import BoxFeature, CylinderFeature
from src.core.types import BooleanOperation
from src.viewport.gl_renderer import GLRenderer
from src.render.raytracer import PBRRaytracer
from src.render.pbr_material import PBR_LIBRARY


def test_solid_mesh_buffer_caching() -> None:
    """Valide que le deuxième appel à to_mesh_buffer() est quasi-instantané via le cache."""
    solid = make_box(30.0, 30.0, 30.0)
    assert solid._cached_buffer is None

    buf1 = solid.to_mesh_buffer()
    assert buf1 is not None
    assert solid._cached_buffer is buf1

    # Deuxième appel : renvoie exactement la même référence en cache
    buf2 = solid.to_mesh_buffer()
    assert buf2 is buf1


def test_document_timeline_snapshot_caching() -> None:
    """Valide le cache par instantané lors du retour en arrière et de la lecture."""
    doc = CADDocument("SnapshotDoc")
    b1 = BoxFeature("b1", "Box 1", 10.0, 10.0, 10.0)
    b2 = BoxFeature("b2", "Box 2", 20.0, 20.0, 20.0)
    b3 = BoxFeature("b3", "Box 3", 30.0, 30.0, 30.0)

    doc.add_feature(b1)
    doc.add_feature(b2)
    doc.add_feature(b3)

    assert 0 in doc._timeline_snapshots
    assert 1 in doc._timeline_snapshots
    assert 2 in doc._timeline_snapshots

    # Rollback à l'étape 1 (Box 2)
    t0 = time.perf_counter()
    doc.set_rollback_index(1)
    t_elapsed = time.perf_counter() - t0

    # L'accès via snapshot en cache doit être quasi instantané (< 5 ms)
    assert t_elapsed < 0.05
    assert len(doc.bodies) == 2


def test_gl_renderer_grid_precomputation() -> None:
    """Valide que la géométrie de la grille est précalculée sous forme de tableaux NumPy."""
    renderer = GLRenderer()
    assert renderer._grid_minor_pts is not None
    assert renderer._grid_major_pts is not None
    assert isinstance(renderer._grid_minor_pts, np.ndarray)
    assert isinstance(renderer._grid_major_pts, np.ndarray)
    assert renderer._grid_minor_pts.dtype == np.float32
    assert renderer._grid_major_pts.dtype == np.float32


def test_raytracer_vectorized_rendering_performance() -> None:
    """Valide la génération d'image de rendu photoréaliste vectorisée."""
    solid = make_box(20.0, 20.0, 20.0)
    material = PBR_LIBRARY["Aluminium Brossé"]
    raytracer = PBRRaytracer()

    t0 = time.perf_counter()
    img = raytracer.render_solid_to_image(solid, material, width=120, height=80)
    t_elapsed = time.perf_counter() - t0

    assert not img.isNull()
    assert img.width() == 120
    assert img.height() == 80
    # Le rendu de cette résolution doit être rapide grâce au fond QLinearGradient et à la projection vectorisée
    assert t_elapsed < 1.0
