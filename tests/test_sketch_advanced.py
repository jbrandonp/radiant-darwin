"""
Tests exhaustifs des fonctionnalités avancées de l'esquisseuse 2D (Sketcher).
Valide :
- La projection de géométrie 3D externe (External Reference)
- Les cotes pilotées (Driven Dimensions) vs cotes actives (Driving Dimensions)
- Les opérations de découpe (Trim) et de prolongement (Extend)
- Le congé 2D (Fillet) et le chanfrein 2D (Chamfer)
- Le peigne de courbure 2D (Porcupine Comb) sur courbes splines / Bézier
"""

import numpy as np
import pytest

from src.core.sketch import (
    Sketch2D, SketchLine, SketchCircle, SketchArc, SketchExternalReference,
    DimensionType, SketchDimension, EntityType
)
from src.core.types import Point2D, PlaneType


def test_sketch_add_external_reference():
    """Vérifie la projection d'une arête 3D en trait de référence passif violet."""
    sketch = Sketch2D("sketch_test", "MainSketch", plane=PlaneType.XY, offset_distance=10.0)

    edge_start_3d = (0.0, 5.0, 10.0)
    edge_end_3d = (50.0, 5.0, 10.0)

    ref_entity = sketch.add_external_reference(
        edge_start_3d, edge_end_3d, source_body_id="Body_Pad", source_edge_id="Edge_Top"
    )

    assert isinstance(ref_entity, SketchExternalReference)
    assert ref_entity.entity_type == EntityType.EXTERNAL_REFERENCE
    assert ref_entity.is_construction is True
    assert ref_entity.color == "#8A2BE2"  # Violet
    assert ref_entity.p1.u == pytest.approx(0.0)
    assert ref_entity.p1.v == pytest.approx(5.0)
    assert ref_entity.p2.u == pytest.approx(50.0)
    assert ref_entity.p2.v == pytest.approx(5.0)

    # Vérifie que les entités de construction ne polluent pas le profil primaire
    assert len(sketch.get_solid_entities()) == 0
    assert len(sketch.get_construction_entities()) == 1


def test_sketch_driven_vs_driving_dimensions():
    """Vérifie l'enregistrement et le calcul des cotes pilotées (driven) et actives (driving)."""
    sketch = Sketch2D("sketch_dims", plane=PlaneType.XY)
    l1 = sketch.add_line(Point2D(0.0, 0.0), Point2D(30.0, 40.0))

    # Cote pilotante imposant 50.0
    dim_driving = sketch.add_dimension(DimensionType.DISTANCE, l1.entity_id, value=50.0, is_driven=False)
    # Cote pilotée / référence calculée automatiquement (30^2 + 40^2 = 50^2)
    dim_driven = sketch.add_dimension(DimensionType.DISTANCE, l1.entity_id, is_driven=True)

    assert dim_driving.is_driven is False
    assert dim_driving.value == 50.0

    assert dim_driven.is_driven is True
    assert dim_driven.value == pytest.approx(50.0, abs=1e-3)

    assert len(sketch.get_driving_dimensions()) == 1
    assert len(sketch.get_driven_dimensions()) == 1


def test_sketch_trim_segment():
    """Vérifie la découpe d'un segment de ligne par un trait sécant."""
    sketch = Sketch2D("sketch_trim", plane=PlaneType.XY)
    target = sketch.add_line(Point2D(0.0, 10.0), Point2D(50.0, 10.0))
    cutter = sketch.add_line(Point2D(20.0, 0.0), Point2D(20.0, 30.0))

    trimmed = sketch.trim_segment(target.entity_id, cutter.entity_id, keep_side="start")
    assert trimmed is not None
    assert trimmed.p1.u == pytest.approx(0.0)
    assert trimmed.p1.v == pytest.approx(10.0)
    assert trimmed.p2.u == pytest.approx(20.0)
    assert trimmed.p2.v == pytest.approx(10.0)


def test_sketch_extend_segment():
    """Vérifie le prolongement d'un segment jusqu'à une droite frontière."""
    sketch = Sketch2D("sketch_extend", plane=PlaneType.XY)
    target = sketch.add_line(Point2D(0.0, 10.0), Point2D(15.0, 10.0))
    boundary = sketch.add_line(Point2D(30.0, 0.0), Point2D(30.0, 40.0))

    extended = sketch.extend_segment(target.entity_id, boundary.entity_id)
    assert extended is not None
    assert extended.p1.u == pytest.approx(0.0)
    assert extended.p2.u == pytest.approx(30.0)
    assert extended.p2.v == pytest.approx(10.0)


def test_sketch_fillet_and_chamfer_2d():
    """Vérifie la création de congés et chanfreins 2D entre deux lignes orthogonales."""
    # Test Fillet
    sketch_f = Sketch2D("sketch_fillet", plane=PlaneType.XY)
    l1 = sketch_f.add_line(Point2D(0.0, 0.0), Point2D(20.0, 0.0))
    l2 = sketch_f.add_line(Point2D(20.0, 0.0), Point2D(20.0, 20.0))

    res_fillet = sketch_f.fillet_2d_lines(l1.entity_id, l2.entity_id, radius=5.0)
    assert res_fillet is not None
    up_l1, up_l2, circle = res_fillet
    assert up_l1.p2.u == pytest.approx(15.0, abs=1e-2)
    assert up_l2.p1.v == pytest.approx(5.0, abs=1e-2)
    assert circle.radius == pytest.approx(5.0, abs=1e-2)

    # Test Chamfer
    sketch_c = Sketch2D("sketch_chamfer", plane=PlaneType.XY)
    cl1 = sketch_c.add_line(Point2D(0.0, 0.0), Point2D(20.0, 0.0))
    cl2 = sketch_c.add_line(Point2D(20.0, 0.0), Point2D(20.0, 20.0))

    res_chamfer = sketch_c.chamfer_2d_lines(cl1.entity_id, cl2.entity_id, distance=4.0)
    assert res_chamfer is not None
    cup_l1, cup_l2, bevel = res_chamfer
    assert cup_l1.p2.u == pytest.approx(16.0, abs=1e-2)
    assert cup_l2.p1.v == pytest.approx(4.0, abs=1e-2)
    assert bevel.p1.u == pytest.approx(16.0, abs=1e-2)
    assert bevel.p2.v == pytest.approx(4.0, abs=1e-2)


def test_sketch_porcupine_comb_2d():
    """Vérifie la génération du peigne de courbure (porcupine comb) sur une courbe de Bézier."""
    sketch = Sketch2D("sketch_comb", plane=PlaneType.XY)
    ctrl_pts = [Point2D(0.0, 0.0), Point2D(10.0, 20.0), Point2D(20.0, 0.0)]
    bezier = sketch.add_bezier(ctrl_pts, segments=30)

    comb = sketch.generate_porcupine_comb_2d(bezier.entity_id, num_samples=15, scale=5.0)
    assert len(comb) >= 10
    for root, tip in comb:
        assert isinstance(root, Point2D)
        assert isinstance(tip, Point2D)
        # La pointe du peigne est distante de la racine en fonction de la courbure
        dist = np.hypot(tip.u - root.u, tip.v - root.v)
        assert dist > 0.0
