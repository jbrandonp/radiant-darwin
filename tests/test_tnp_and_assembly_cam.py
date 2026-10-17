"""
Tests unitaires et d'intégration industrielle :
1. Ray-Casting & Picking 3D interactif dans le Viewport.
2. Résolution du Nommage Topologique (TNP Mitigation RealThunder style).
3. Atelier d'Assemblage Multi-Pièces & Solveur Cinématique (Mates, DoF, Collisions).
4. Post-processeurs CNC industriels (Haas, Fanuc, Heidenhain).
Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
import numpy as np
import pytest

from src.core.types import Vector3D
from src.core.geometry import Solid, make_box, make_cylinder
from src.viewport.camera import CADCamera
from src.viewport.ray_picking import Ray3D, RayPicker, PickedEntityType
from src.core.tnp_mitigation import TNPMitigationManager, GeometricFingerprint, TNPSurfaceKind
from src.core.assembly import AssemblyInstance, AssemblyMate, MateType, AssemblySolver
from src.cam.cam_engine import CAMEngine, CNCTool, ToolType
from src.cam.post_processors import IndustrialPostProcessor, CNCDialect


def test_ray_picking_face_and_edge() -> None:
    """Vérifie le lancer de rayon 3D pour la sélection directe de faces et d'arêtes."""
    box = make_box(60.0, 40.0, 20.0)

    # 1. Sélection de face par lancer de rayon vertical descendant
    ray_top = Ray3D(origin=Vector3D(30.0, 20.0, 100.0), direction=Vector3D(0.0, 0.0, -1.0))
    hit_face = RayPicker.pick_face(ray_top, box.to_mesh_buffer(), body_id="body_box")

    assert hit_face is not None
    assert hit_face.entity_type == PickedEntityType.FACE
    assert abs(hit_face.hit_point.z - 20.0) < 1e-3
    assert abs(hit_face.normal.z - 1.0) < 1e-3
    assert hit_face.body_id == "body_box"

    # 2. Sélection de face latérale droite (+X)
    ray_right = Ray3D(origin=Vector3D(120.0, 20.0, 10.0), direction=Vector3D(-1.0, 0.0, 0.0))
    hit_right = RayPicker.pick_face(ray_right, box.to_mesh_buffer(), body_id="body_box")

    assert hit_right is not None
    assert abs(hit_right.hit_point.x - 60.0) < 1e-3
    assert abs(hit_right.normal.x - 1.0) < 1e-3

    # 3. Sélection d'arête par proximité
    # Arête supérieure droite : Y varie de 0 à 40 à X=60, Z=20
    ray_edge = Ray3D(origin=Vector3D(60.2, 20.0, 100.0), direction=Vector3D(0.0, 0.0, -1.0))
    hit_edge = RayPicker.pick_edge(ray_edge, box.to_mesh_buffer(), max_tolerance=1.5, body_id="body_box")

    assert hit_edge is not None
    assert hit_edge.entity_type == PickedEntityType.EDGE
    assert hit_edge.edge_index >= 0

    # 4. Sélection depuis l'écran via la caméra
    cam = CADCamera()
    cam.target = Vector3D(30.0, 20.0, 10.0)
    cam.set_preset_view("TOP")
    bodies = {"body_box": box}
    screen_hit = RayPicker.pick_from_screen(400.0, 300.0, 800, 600, cam, bodies)
    assert screen_hit.has_hit


def test_tnp_mitigation_persistent_fingerprinting() -> None:
    """Vérifie l'identification persistante des faces lors du recalcul de dimensions amont."""
    manager = TNPMitigationManager()

    # Solide initial : boîte 50x30x20
    box_initial = make_box(50.0, 30.0, 20.0)
    faces_initial = manager.extract_faces(box_initial, feature_id="f_pad1")
    assert len(faces_initial) >= 6

    # Trouver la face supérieure (normale Z=+1, Z=20)
    top_face_init = next(f for f in faces_initial if abs(f.fingerprint.normal[2] - 1.0) < 1e-3)
    fp_target = top_face_init.fingerprint

    # Modification amont : boîte élargie à 55x30x20 (les indices triangulaires peuvent bouger)
    box_modified = make_box(55.0, 30.0, 20.0)
    faces_modified = manager.extract_faces(box_modified, feature_id="f_pad1")

    # Retrouver la face cible grâce à l'empreinte géométrique multi-facteurs
    matched_face = manager.match_face_across_rebuild(fp_target, faces_modified, acceptance_threshold=0.60)

    assert matched_face is not None
    assert abs(matched_face.fingerprint.normal[2] - 1.0) < 1e-3
    assert abs(matched_face.fingerprint.centroid[2] - 20.0) < 1e-3


def test_multi_body_assembly_solver_and_collisions() -> None:
    """Vérifie le solveur cinématique d'assemblage multi-pièces et la détection d'interférences."""
    # Pièce 1 : Boîtier de roulement fixé (grounded) avec alésage central
    housing_box = make_box(80.0, 80.0, 40.0)
    hole_cutter = make_cylinder(20.0, 40.0, center=False).translate([40.0, 40.0, 0.0])
    housing = housing_box.difference(hole_cutter)

    # Pièce 2 : Arbre mécanique cylindrique de rayon 20mm
    shaft = make_cylinder(19.8, 80.0, center=False)

    inst_housing = AssemblyInstance("inst_housing", housing, name="Carter", is_grounded=True)
    inst_shaft = AssemblyInstance("inst_shaft", shaft, name="Arbre", is_grounded=False)

    instances = {
        "inst_housing": inst_housing,
        "inst_shaft": inst_shaft
    }

    # Contrainte de coaxialité entre l'alésage du carter (40, 40) et l'arbre (0, 0)
    mate_coax = AssemblyMate(
        mate_id="mate_coax",
        mate_type=MateType.COAXIAL,
        instance1_id="inst_housing",
        instance2_id="inst_shaft",
        point1=(40.0, 40.0, 20.0),
        axis1=(0.0, 0.0, 1.0),
        point2=(0.0, 0.0, 40.0),
        axis2=(0.0, 0.0, 1.0)
    )

    # Contrainte de plan coïncident avec décalage de 10 mm
    mate_plane = AssemblyMate(
        mate_id="mate_plane",
        mate_type=MateType.COINCIDENT_PLANES,
        instance1_id="inst_housing",
        instance2_id="inst_shaft",
        point1=(0.0, 0.0, 40.0),
        axis1=(0.0, 0.0, 1.0),
        point2=(0.0, 0.0, 0.0),
        axis2=(0.0, 0.0, 1.0),
        offset=5.0
    )

    success = AssemblySolver.solve_mates(instances, [mate_coax, mate_plane])
    assert success is True

    # Vérification que l'arbre a été translaté en X=40, Y=40
    tx = float(inst_shaft.transform_matrix[0, 3])
    ty = float(inst_shaft.transform_matrix[1, 3])
    assert abs(tx - 40.0) < 1e-4
    assert abs(ty - 40.0) < 1e-4

    # Degrés de liberté : 6 DDL - (4 coaxialité + 3 plan) = 0 DDL bloqué
    dof = AssemblySolver.compute_degrees_of_freedom(instances, [mate_coax, mate_plane])
    assert dof == 0

    # Test de détection de collision physique :
    # Si on force une interférence volumique dans la paroi pleine du carter
    colliding_part = make_box(20.0, 20.0, 20.0).translate([5.0, 5.0, 10.0])
    inst_collide = AssemblyInstance("inst_interfere", colliding_part, is_grounded=True)
    inter_instances = {"inst_housing": inst_housing, "inst_collide": inst_collide}

    collisions = AssemblySolver.detect_collisions(inter_instances)
    assert len(collisions) >= 1
    assert collisions[0][2] > 0.0  # Volume d'interférence positif


def test_assembly_instance_preserves_full_3d_rotation() -> None:
    """Vérifie que AssemblyInstance.get_transformed_solid applique la rotation 3x3 et pas seulement la translation."""
    box = make_box(20.0, 10.0, 10.0)
    inst = AssemblyInstance("inst_rot", box, name="RotatedBox")

    # Rotation de 90° autour de Z : X -> Y, Y -> -X
    # [ 0, -1,  0, 10 ]
    # [ 1,  0,  0, 20 ]
    # [ 0,  0,  1,  0 ]
    # [ 0,  0,  0,  1 ]
    mat = np.eye(4, dtype=np.float64)
    mat[0, 0] = 0.0
    mat[0, 1] = -1.0
    mat[1, 0] = 1.0
    mat[1, 1] = 0.0
    mat[0, 3] = 10.0
    mat[1, 3] = 20.0
    inst.transform_matrix = mat

    transformed_solid = inst.get_transformed_solid()
    b_min, b_max = transformed_solid.bounding_box()

    # Dimensions originelles : DX=20, DY=10, DZ=10
    # Après rotation 90° autour de Z : DX=10, DY=20, DZ=10
    dx = b_max.x - b_min.x
    dy = b_max.y - b_min.y
    dz = b_max.z - b_min.z
    assert abs(dx - 10.0) < 1e-3
    assert abs(dy - 20.0) < 1e-3
    assert abs(dz - 10.0) < 1e-3


def test_cam_industrial_post_processors_haas_fanuc_heidenhain() -> None:
    """Vérifie la génération de code CNC pour contrôleurs Haas, Fanuc et Heidenhain."""
    engine = CAMEngine()
    fraise = CNCTool(
        tool_id=2,
        name="Fraise Carbure Ø10mm",
        tool_type=ToolType.END_MILL,
        diameter_mm=10.0,
        flute_length_mm=30.0,
        feedrate_mm_min=1200.0,
        plunge_rate_mm_min=300.0,
        spindle_speed_rpm=10000.0
    )

    op_face = engine.generate_facing_toolpath(
        min_x=0.0, max_x=100.0,
        min_y=0.0, max_y=60.0,
        stock_z=10.0, target_z=5.0,
        tool=fraise
    )

    operations = [op_face]

    # 1. Post-processeur Haas
    gcode_haas = IndustrialPostProcessor.post_process_haas(operations, program_number=1234)
    assert "%" in gcode_haas
    assert "O01234" in gcode_haas
    assert "G43 H02 Z50.0 M08" in gcode_haas
    assert "G53 G00 Z0." in gcode_haas
    assert "M30" in gcode_haas

    # 2. Post-processeur Fanuc
    gcode_fanuc = IndustrialPostProcessor.post_process_fanuc(operations, program_number=202)
    assert "O0202" in gcode_fanuc
    assert "G28 G91 Z0." in gcode_fanuc
    assert "G43 H02 Z50.0 M08" in gcode_fanuc
    assert "M30" in gcode_fanuc

    # 3. Post-processeur Heidenhain Klartext
    gcode_heidenhain = IndustrialPostProcessor.post_process_heidenhain(operations, program_name="PIECE_MOTEUR")
    assert "BEGIN PGM PIECE_MOTEUR MM" in gcode_heidenhain
    assert "TOOL CALL 2 Z S10000" in gcode_heidenhain
    assert "FMAX M3 M8" in gcode_heidenhain
    assert "END PGM PIECE_MOTEUR MM" in gcode_heidenhain

    # 4. Métriques physiques d'usinage
    metrics = IndustrialPostProcessor.calculate_metrics(operations)
    assert metrics.total_distance_mm > 100.0
    assert metrics.cutting_distance_mm > 0.0
    assert metrics.estimated_time_seconds > 0.0
    assert "s" in metrics.estimated_time_formatted
