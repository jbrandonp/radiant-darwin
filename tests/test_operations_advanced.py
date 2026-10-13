"""
Tests unitaires pour les opérations volumiques avancées (Revolve, Hole, Shell, Patterns, Mirror).
"""

import pytest

from src.core.document import CADDocument
from src.core.sketch import Sketch2D
from src.core.types import Point2D, PlaneType
from src.core.feature import BoxFeature
from src.core.operations_advanced import (
    RevolveFeature, LinearPatternFeature, CircularPatternFeature,
    MirrorFeature, HoleFeature, ShellFeature
)


def test_revolve_feature() -> None:
    """Vérifie la création d'un solide de révolution à 360 degrés."""
    doc = CADDocument("RevolveDoc")
    sketch = Sketch2D("s_rev", "Sketch Revolve", PlaneType.XY)
    # Profil rectangulaire décalé de l'axe : [5,0] à [15,20]
    sketch.add_polygon([
        Point2D(5.0, 0.0),
        Point2D(15.0, 0.0),
        Point2D(15.0, 20.0),
        Point2D(5.0, 20.0)
    ])
    doc.add_sketch(sketch)

    rev_feat = RevolveFeature("f_rev", "Revolve", sketch_id="s_rev", angle_deg=360.0)
    doc.add_feature(rev_feat)

    assert len(doc.bodies) == 1
    solid = doc.bodies[rev_feat.body_id]
    assert not solid.is_empty()
    assert solid.volume() > 5000.0


def test_hole_feature() -> None:
    """Vérifie la soustraction d'un perçage dans un corps existant."""
    doc = CADDocument("HoleDoc")
    box = BoxFeature("f_box", "Base", width=40.0, height=40.0, depth=20.0, center=True)
    doc.add_feature(box)
    v0 = doc.bodies[box.body_id].volume()

    hole = HoleFeature("f_hole", "Hole Ø10", target_body_id=box.body_id, pos_x=0.0, pos_y=0.0, diameter=10.0, depth=30.0)
    doc.add_feature(hole)

    v1 = doc.bodies[box.body_id].volume()
    assert v1 < v0


def test_shell_feature() -> None:
    """Vérifie l'évidement d'une boîte solide avec paroi constante."""
    doc = CADDocument("ShellDoc")
    box = BoxFeature("f_box", "Box", width=30.0, height=30.0, depth=30.0, center=True)
    doc.add_feature(box)
    v_solid = doc.bodies[box.body_id].volume()

    shell = ShellFeature("f_shell", "Shell", target_body_id=box.body_id, wall_thickness=2.0)
    doc.add_feature(shell)

    v_hollow = doc.bodies[box.body_id].volume()
    assert v_hollow < v_solid


def test_linear_pattern_feature() -> None:
    """Vérifie la duplication matricielle rectangulaire."""
    doc = CADDocument("LinearPatDoc")
    box = BoxFeature("f_box", "Cube", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box)

    pat = LinearPatternFeature("f_pat", "Linear", source_body_id=box.body_id, count_x=3, spacing_x=20.0, join_bodies=True)
    doc.add_feature(pat)

    # 3 cubes de 10x10x10 = 3000 mm³
    assert pytest.approx(doc.bodies[box.body_id].volume(), 0.1) == 3000.0


def test_mirror_feature() -> None:
    """Vérifie la symétrie miroir par rapport au plan YZ."""
    doc = CADDocument("MirrorDoc")
    box = BoxFeature("f_box", "Half", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box)

    mirror = MirrorFeature("f_mir", "Mirror", source_body_id=box.body_id, mirror_plane=PlaneType.YZ, join_with_source=True)
    doc.add_feature(mirror)

    # Le volume doit être doublé
    assert pytest.approx(doc.bodies[box.body_id].volume(), 0.1) == 2000.0
