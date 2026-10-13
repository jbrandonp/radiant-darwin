"""
Tests unitaires complets pour la parité FreeCAD :
- Atelier PartDesign : Lissage (Loft), Balayage (Sweep), Congé (Fillet), Chanfrein (Chamfer), Dépouille (Draft).
- Atelier Inspection / Measure : Mesure 3D, Angles, Barycentre / Centre de Gravité, Jeux (Clearance), Collisions.
- Atelier Mesh : Diagnostic d'étanchéité 2-Manifold, Réparation topologique, Décimation, Inversion de normales.
- Sérialisation et Persistance (.cadproj).
- Boîtes de dialogue de l'interface utilisateur.
"""

import pytest
import numpy as np
from typing import Dict, List

from src.core.types import BooleanOperation, PlaneType, Point2D, Vector3D
from src.core.geometry import Solid, make_box, make_cylinder
from src.core.sketch import Sketch2D
from src.core.document import CADDocument
from src.core.operations_advanced import (
    LoftFeature, SweepFeature, FilletFeature, ChamferFeature, DraftFeature
)
from src.core.inspector import (
    measure_points, measure_angle_vectors, compute_center_of_mass,
    compute_clearance, compute_interference, generate_inspection_report
)
from src.core.mesh_tools import (
    diagnose_mesh, repair_mesh, simplify_mesh, flip_mesh_normals,
    create_solid_from_triangles
)
from src.core.serializer import ProjectSerializer


def test_loft_between_two_sketches():
    """Vérifie la création d'un solide par lissage (Loft) entre deux esquisses distinctes."""
    doc = CADDocument("TestLoft")

    # Esquisse 1 : Carré 30x30 en Z=0
    sk1 = Sketch2D("sk_base", "Base", PlaneType.XY)
    sk1.add_rectangle(Point2D(-15.0, -15.0), 30.0, 30.0)
    doc.add_sketch(sk1)

    # Esquisse 2 : Carré 15x15 en haut
    sk2 = Sketch2D("sk_top", "Top", PlaneType.XY)
    sk2.add_rectangle(Point2D(-7.5, -7.5), 15.0, 15.0)
    doc.add_sketch(sk2)

    loft = LoftFeature(
        feature_id="loft_1",
        name="Loft Transition",
        start_sketch_id="sk_base",
        end_sketch_id="sk_top",
        height_offset=25.0,
        num_segments=32,
        operation=BooleanOperation.NEW_BODY
    )
    doc.add_feature(loft)

    assert len(doc.bodies) == 1
    body = list(doc.bodies.values())[0]
    assert not body.is_empty()
    assert body.volume() > 1000.0
    b_min, b_max = body.bounding_box()
    assert pytest.approx(b_max.z - b_min.z, 0.1) == 25.0


def test_loft_single_sketch_taper():
    """Vérifie le lissage à partir d'une seule esquisse avec facteur d'échelle supérieur."""
    doc = CADDocument("TestLoftTaper")
    sk = Sketch2D("sk_circ", "Cercle Base", PlaneType.XY)
    sk.add_circle(Point2D(0.0, 0.0), 10.0)
    doc.add_sketch(sk)

    loft = LoftFeature(
        feature_id="loft_taper",
        name="Loft Cone",
        start_sketch_id="sk_circ",
        end_sketch_id="",
        height_offset=20.0,
        scale_top=0.5,
        num_segments=36
    )
    doc.add_feature(loft)

    assert len(doc.bodies) == 1
    body = list(doc.bodies.values())[0]
    assert not body.is_empty()
    assert body.volume() > 500.0


def test_sweep_arc_and_helix():
    """Vérifie le balayage volumique (Sweep) le long d'un arc et d'une hélice."""
    doc = CADDocument("TestSweep")
    sk = Sketch2D("sk_prof", "Profil Circulaire", PlaneType.XY)
    sk.add_circle(Point2D(0.0, 0.0), 4.0)
    doc.add_sketch(sk)

    # Balayage en Arc
    sweep_arc = SweepFeature(
        feature_id="sweep_1",
        name="Tuyau Coude",
        profile_sketch_id="sk_prof",
        trajectory_type="arc",
        radius=30.0,
        height=30.0,
        num_steps=20,
        segments=20
    )
    doc.add_feature(sweep_arc)
    assert len(doc.bodies) == 1
    assert not list(doc.bodies.values())[0].is_empty()

    # Balayage en Hélice
    doc2 = CADDocument("TestSweepHelix")
    doc2.add_sketch(sk)
    sweep_helix = SweepFeature(
        feature_id="sweep_2",
        name="Ressort Hélicoïdal",
        profile_sketch_id="sk_prof",
        trajectory_type="helix",
        radius=20.0,
        height=30.0,
        turns=1.5,
        num_steps=30,
        segments=16
    )
    doc2.add_feature(sweep_helix)
    assert len(doc2.bodies) == 1
    assert not list(doc2.bodies.values())[0].is_empty()


def test_fillet_and_chamfer():
    """Vérifie les opérations de congé (Fillet) et chanfrein (Chamfer)."""
    # 1. Congé d'arête
    cube = make_box(20.0, 20.0, 20.0, center=True, name="BaseCube")
    bodies = {"body_cube": cube}
    sketches: Dict[str, Sketch2D] = {}

    fillet = FilletFeature(
        feature_id="fillet_1",
        name="Congé R2",
        target_body_id="body_cube",
        radius=2.0,
        segments=16
    )
    res_fillet = fillet.evaluate(bodies, sketches)
    filleted_solid = res_fillet["body_cube"]
    assert not filleted_solid.is_empty()
    # Le volume avec congé doit être légèrement inférieur au cube parfait (8000)
    assert filleted_solid.volume() < 8000.0
    assert filleted_solid.volume() > 7000.0

    # 2. Chanfrein d'arête
    chamfer = ChamferFeature(
        feature_id="chamfer_1",
        name="Chanfrein 2mm",
        target_body_id="body_cube",
        distance=2.0,
        edges_mode="all"
    )
    res_chamfer = chamfer.evaluate(bodies, sketches)
    chamfered_solid = res_chamfer["body_cube"]
    assert not chamfered_solid.is_empty()
    assert chamfered_solid.volume() < 8000.0


def test_draft_feature():
    """Vérifie l'application d'un angle de dépouille (Draft)."""
    cube = make_box(20.0, 20.0, 30.0, center=False, name="MoldingBase")
    bodies = {"body_mold": cube}
    sketches: Dict[str, Sketch2D] = {}

    draft = DraftFeature(
        feature_id="draft_1",
        name="Dépouille 4deg",
        target_body_id="body_mold",
        draft_angle_deg=4.0,
        pull_axis="Z"
    )
    res = draft.evaluate(bodies, sketches)
    drafted_solid = res["body_mold"]
    assert not drafted_solid.is_empty()
    assert drafted_solid.volume() < cube.volume()


def test_inspector_measurements():
    """Vérifie la précision des outils de mesure 3D et métrologie."""
    # Distance entre 2 points
    p1 = Vector3D(0.0, 0.0, 0.0)
    p2 = Vector3D(10.0, 20.0, 20.0)
    res = measure_points(p1, p2)
    assert pytest.approx(res.distance, 1e-4) == 30.0  # sqrt(100 + 400 + 400) = 30
    assert pytest.approx(res.dx, 1e-4) == 10.0
    assert pytest.approx(res.dy, 1e-4) == 20.0
    assert pytest.approx(res.dz, 1e-4) == 20.0
    assert pytest.approx(res.midpoint.x, 1e-4) == 5.0

    # Angle entre vecteurs
    v_x = Vector3D(1.0, 0.0, 0.0)
    v_y = Vector3D(0.0, 1.0, 0.0)
    assert pytest.approx(measure_angle_vectors(v_x, v_y), 1e-4) == 90.0
    assert pytest.approx(measure_angle_vectors(v_x, v_x), 1e-4) == 0.0

    # Centre de gravité d'une boîte centrée en (15, 25, 35)
    box = make_box(10.0, 10.0, 10.0, center=True).translate(Vector3D(15.0, 25.0, 35.0))
    cog = compute_center_of_mass(box)
    assert pytest.approx(cog.x, 0.1) == 15.0
    assert pytest.approx(cog.y, 0.1) == 25.0
    assert pytest.approx(cog.z, 0.1) == 35.0

    # Jeux (Clearance) et Collisions
    box_a = make_box(10.0, 10.0, 10.0, center=True)
    box_b = make_box(10.0, 10.0, 10.0, center=True).translate(Vector3D(25.0, 0.0, 0.0))
    gap = compute_clearance(box_a, box_b)
    assert pytest.approx(gap, 0.1) == 15.0  # de x=5 à x=20

    has_col, vol_col = compute_interference(box_a, box_b)
    assert not has_col
    assert vol_col == 0.0

    # Rapport d'inspection
    rep = generate_inspection_report(box_a, "Acier S235", 7.85)
    assert pytest.approx(float(rep["volume_mm3"]), 0.1) == 1000.0
    assert pytest.approx(float(rep["surface_area_mm2"]), 0.1) == 600.0


def test_mesh_workbench_diagnostic_and_repair():
    """Vérifie l'analyse et la réparation de maillage de l'atelier Mesh."""
    cube = make_box(10.0, 10.0, 10.0, center=True)
    diag = diagnose_mesh(cube)
    assert diag.is_watertight
    assert diag.num_faces == 12
    assert diag.num_vertices == 8
    assert diag.genus == 0
    assert diag.degenerate_faces == 0

    # Réparation de maillage
    repaired = repair_mesh(cube)
    assert not repaired.is_empty()
    assert pytest.approx(repaired.volume(), 0.1) == 1000.0

    # Simplification de maillage
    cyl = make_cylinder(10.0, 20.0, segments=48)
    initial_faces = cyl.num_faces()
    decimated = simplify_mesh(cyl, 0.5)
    assert not decimated.is_empty()

    # Inversion de normales
    flipped = flip_mesh_normals(cube)
    assert not flipped.is_empty()

    # Construction depuis triangles bruts
    verts = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10]]
    faces = [
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]
    ]
    solid_from_tri = create_solid_from_triangles(verts, faces, "CustomSolid")
    assert not solid_from_tri.is_empty()
    assert solid_from_tri.volume() > 0.0


def test_serialization_freecad_parity_features(tmp_path):
    """Vérifie que les nouvelles features se sauvegardent et se rechargent sans perte."""
    doc = CADDocument("TestSer")
    sk = Sketch2D("sk_1", "Esquisse", PlaneType.XY)
    sk.add_rectangle(Point2D(-10.0, -10.0), 20.0, 20.0)
    doc.add_sketch(sk)

    doc.add_feature(LoftFeature("f_loft", "MonLoft", "sk_1", "", height_offset=25.0, scale_top=0.7))
    doc.add_feature(SweepFeature("f_sweep", "MonSweep", "sk_1", trajectory_type="arc", radius=25.0, height=25.0))

    filepath = str(tmp_path / "project_freecad_parity.cadproj")
    ok = ProjectSerializer.save_project(doc, filepath)
    assert ok

    loaded_doc = ProjectSerializer.load_project(filepath)
    assert loaded_doc is not None
    assert len(loaded_doc.features) == 2
    assert loaded_doc.features[0].__class__.__name__ == "LoftFeature"
    assert loaded_doc.features[1].__class__.__name__ == "SweepFeature"


def test_ui_freecad_parity_dialogs():
    """Vérifie l'instanciation et la récupération des valeurs de toutes les boîtes de dialogue."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from src.ui.dialogs import (
        LoftDialog, SweepDialog, FilletDialog, ChamferDialog,
        DraftDialog, MeasureDialog, MeshAnalysisDialog
    )
    _app = QApplication.instance() or QApplication([])
    b = make_box(10.0, 10.0, 10.0, center=True)
    bodies = {"b1": b, "b2": b}
    sketches = ["sk1", "sk2"]

    d_loft = LoftDialog(sketches, list(bodies.keys()))
    val_loft = d_loft.get_values()
    assert val_loft["height_offset"] == 30.0

    d_sweep = SweepDialog(sketches, list(bodies.keys()))
    val_sweep = d_sweep.get_values()
    assert val_sweep["radius"] == 30.0

    d_fillet = FilletDialog(list(bodies.keys()))
    val_fillet = d_fillet.get_values()
    assert val_fillet["radius"] == 2.0

    d_chamfer = ChamferDialog(list(bodies.keys()))
    val_chamfer = d_chamfer.get_values()
    assert val_chamfer["distance"] == 2.0

    d_draft = DraftDialog(list(bodies.keys()))
    val_draft = d_draft.get_values()
    assert val_draft["draft_angle"] == 3.0

    d_meas = MeasureDialog(bodies)
    assert d_meas is not None

    d_mesh = MeshAnalysisDialog(bodies)
    assert d_mesh is not None
