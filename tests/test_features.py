"""
Tests unitaires pour les fonctionnalités paramétriques et l'arbre d'historique (Timeline).
"""

import pytest
from src.core.types import BooleanOperation
from src.core.feature import BoxFeature, CylinderFeature, SphereFeature, ExtrudeFeature, BooleanFeature
from src.core.document import CADDocument
from src.core.sketch import Sketch2D
from src.core.types import Point2D, PlaneType


def test_document_feature_addition_and_rebuild() -> None:
    """Vérifie l'ajout de features et le recalcul automatique des corps solides."""
    doc = CADDocument("TestDoc")

    box_feat = BoxFeature("f1", "Box 1", width=20.0, height=20.0, depth=10.0)
    doc.add_feature(box_feat)

    assert len(doc.bodies) == 1
    body_id = box_feat.body_id
    assert body_id in doc.bodies
    assert pytest.approx(doc.bodies[body_id].volume(), 0.1) == 4000.0

    # Ajouter un cylindre fusionné
    cyl_feat = CylinderFeature(
        "f2", "Cyl 1", radius=5.0, height=10.0,
        operation=BooleanOperation.JOIN,
        target_body_id=body_id
    )
    doc.add_feature(cyl_feat)

    assert len(doc.bodies) == 1  # Toujours 1 corps car fusionné (JOIN)
    assert doc.bodies[body_id].volume() > 4000.0


def test_document_rollback_timeline() -> None:
    """Vérifie le fonctionnement de la barre de retour dans le temps (Rollback)."""
    doc = CADDocument("RollbackDoc")

    f1 = BoxFeature("f1", "Box 1", width=10.0, height=10.0, depth=10.0)
    f2 = BoxFeature("f2", "Box 2", width=10.0, height=10.0, depth=10.0)
    f3 = BoxFeature("f3", "Box 3", width=10.0, height=10.0, depth=10.0)

    doc.add_feature(f1)
    doc.add_feature(f2)
    doc.add_feature(f3)

    assert len(doc.bodies) == 3

    # Revenir en arrière à l'étape 0 (seul f1 doit exister)
    doc.set_rollback_index(0)
    assert len(doc.bodies) == 1
    assert f1.body_id in doc.bodies

    # Revenir à l'étape 1 (f1 et f2 existent)
    doc.set_rollback_index(1)
    assert len(doc.bodies) == 2

    # Rétablir la fin
    doc.set_rollback_index(2)
    assert len(doc.bodies) == 3


def test_extrude_feature() -> None:
    """Vérifie l'extrusion paramétrique d'une esquisse via une ExtrudeFeature."""
    doc = CADDocument("ExtrudeDoc")

    sketch = Sketch2D("sk1", "Sketch 1", PlaneType.XY)
    sketch.add_rectangle(Point2D(0.0, 0.0), 30.0, 20.0)
    doc.add_sketch(sketch)

    ext_feat = ExtrudeFeature("f_ext", "Extrusion 1", sketch_id="sk1", distance=10.0)
    doc.add_feature(ext_feat)

    assert len(doc.bodies) == 1
    body = doc.bodies[ext_feat.body_id]
    assert pytest.approx(body.volume(), 0.1) == 6000.0


def test_parameter_live_update() -> None:
    """Vérifie que la modification d'un paramètre met à jour le volume après rebuild."""
    doc = CADDocument("ParamDoc")
    box_feat = BoxFeature("f_box", "Box", width=10.0, height=10.0, depth=10.0)
    doc.add_feature(box_feat)

    assert pytest.approx(doc.bodies[box_feat.body_id].volume(), 0.1) == 1000.0

    # Modifier la largeur à 20 mm
    box_feat.set_parameter("width", 20.0)
    doc.rebuild()

    assert pytest.approx(doc.bodies[box_feat.body_id].volume(), 0.1) == 2000.0


def test_sphere_feature_and_combine() -> None:
    """Vérifie SphereFeature et BooleanFeature explicite."""
    doc = CADDocument("SphereDoc")
    f_sph1 = SphereFeature("f_sph1", "Sph1", radius=10.0)
    f_sph2 = SphereFeature("f_sph2", "Sph2", radius=8.0)
    doc.add_feature(f_sph1)
    doc.add_feature(f_sph2)

    assert len(doc.bodies) == 2
    # Combiner avec CUT
    f_comb = BooleanFeature("f_comb", "Cut", target_body_id=f_sph1.body_id, tool_body_id=f_sph2.body_id, operation=BooleanOperation.CUT)
    doc.add_feature(f_comb)

    assert len(doc.bodies) == 1
    assert doc.bodies[f_sph1.body_id].volume() < (4.0 / 3.0 * 3.14159 * 1000)

    # Test suppression
    doc.remove_feature("f_comb")
    assert len(doc.bodies) == 2
