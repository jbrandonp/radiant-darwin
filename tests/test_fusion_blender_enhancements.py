"""
Suite de tests complète pour les fonctionnalités inspirées de Fusion 360 et Blender :
- Pile de modificateurs non-destructifs (ModifierStack)
- Modélisation directe Press-Pull (PushPullEngine)
- Solveur de liaisons cinématiques et d'assemblages (JointKinematicSolver)
- Gestionnaire de shading et analyse de surface (ViewportShadingManager)
- Moteur d'accrochage magnétique (MagneticSnapEngine)
- Manipulateur 3D interactif (TransformGizmo)
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.types import Vector3D, ColorRGBA, MeshBuffer, BooleanOperation
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere
from src.core.modifier_stack import (
    ModifierStack, ModifierType, MirrorModifier, ArrayModifier,
    SolidifyModifier, BevelModifier, BooleanModifier
)
from src.core.push_pull import PushPullEngine, PushPullResult
from src.core.joint_solver import (
    FusionJointType, JointLimit, JointAnchor, AssemblyJoint, JointKinematicSolver
)
from src.viewport.viewport_shading import ViewportShadingManager, ShadingMode
from src.viewport.snap_engine import MagneticSnapEngine, SnapTarget, SnapResult
from src.viewport.transform_gizmo import TransformGizmo, GizmoMode, GizmoAxis
from src.viewport.camera import CADCamera


# =========================================================================
# 1. Tests ModifierStack (Blender non-destructive workflow)
# =========================================================================

def test_modifier_stack_creation_and_reorder() -> None:
    stack = ModifierStack("body_1")
    assert stack.count() == 0

    m1 = MirrorModifier("mod_mirror", "Miroir X", axis="X")
    m2 = ArrayModifier("mod_array", "Réseau", count=3, offset_x=25.0)
    stack.add_modifier(m1)
    stack.add_modifier(m2)

    assert stack.count() == 2
    assert stack.modifiers[0].modifier_id == "mod_mirror"
    assert stack.modifiers[1].modifier_id == "mod_array"

    # Déplacer vers le bas (move down: direction +1)
    ok_move = stack.move_modifier("mod_mirror", 1)
    assert ok_move is True
    assert stack.modifiers[0].modifier_id == "mod_array"
    assert stack.modifiers[1].modifier_id == "mod_mirror"

    # Déplacer vers le haut (move up: direction -1)
    ok_up = stack.move_modifier("mod_mirror", -1)
    assert ok_up is True
    assert stack.modifiers[0].modifier_id == "mod_mirror"


def test_mirror_modifier_evaluation() -> None:
    box = make_box(20.0, 20.0, 20.0, center=False)
    vol_init = box.volume()
    assert vol_init > 0.0

    mod = MirrorModifier("mod_m", "Miroir", axis="X", merge=True)
    res = mod.apply(box, {})
    # Symétrie miroir + fusion => volume doublé (ou étendu selon l'axe)
    assert res.volume() >= vol_init
    assert not res.is_empty()


def test_array_modifier_linear_and_radial() -> None:
    cyl = make_cylinder(5.0, 15.0)
    vol_single = cyl.volume()

    # Linéaire 3 copies espacées
    mod_linear = ArrayModifier("arr_lin", "Réseau Linéaire", count=3, offset_x=40.0)
    res_lin = mod_linear.apply(cyl, {})
    assert res_lin.volume() > vol_single * 2.8

    # Circulaire / Radial
    mod_radial = ArrayModifier("arr_rad", "Réseau Radial", count=4, radial=True, radial_angle_deg=90.0)
    res_rad = mod_radial.apply(cyl, {})
    assert res_rad.volume() > 0.0


def test_solidify_modifier_shell() -> None:
    box = make_box(30.0, 30.0, 30.0, center=True)
    vol_full = box.volume()

    mod_solidify = SolidifyModifier("mod_sol", "Coque", thickness=2.0, inner=True)
    res_shell = mod_solidify.apply(box, {})
    # Le solide évidé doit avoir un volume strictement inférieur au bloc plein
    assert 0.0 < res_shell.volume() < vol_full


def test_modifier_stack_evaluate_and_apply_bake() -> None:
    base = make_box(20.0, 20.0, 10.0, center=False)
    stack = ModifierStack("body_test")

    m_arr = ArrayModifier("m_arr", "Array", count=2, offset_x=30.0)
    stack.add_modifier(m_arr)

    # Évaluation non-destructif : le solide de base reste intact
    evaluated = stack.evaluate_stack(base, {})
    assert evaluated.volume() > base.volume()
    assert base.volume() == pytest.approx(4000.0, rel=1e-2)

    # Application définitive (Bake)
    baked, ok = stack.apply_modifier("m_arr", base, {})
    assert ok is True
    assert baked.volume() > base.volume()
    assert stack.count() == 0  # Modificateur retiré après cuisson


# =========================================================================
# 2. Tests PushPullEngine (Fusion 360 Direct Modeling)
# =========================================================================

def test_push_pull_boss_and_pocket() -> None:
    base = make_box(60.0, 60.0, 30.0, center=True)
    vol_orig = base.volume()

    # Extrusion vers l'extérieur (Boss: offset +10mm sur face supérieure +Z)
    hit_pt = Vector3D(0.0, 0.0, 15.0)
    normal = Vector3D(0.0, 0.0, 1.0)
    res_boss = PushPullEngine.execute_press_pull(base, hit_pt, normal, 10.0, footprint_radius=15.0)

    assert res_boss.success is True
    assert res_boss.operation_type == "BOSS_EXTRUSION"
    assert res_boss.volume_delta > 0.0
    assert res_boss.modified_solid.volume() > vol_orig

    # Creusement vers l'intérieur (Pocket: offset -8mm sur face supérieure)
    res_pocket = PushPullEngine.execute_press_pull(base, hit_pt, normal, -8.0, footprint_radius=10.0)
    assert res_pocket.success is True
    assert res_pocket.operation_type == "POCKET_CUT"
    assert res_pocket.volume_delta < 0.0
    assert res_pocket.modified_solid.volume() < vol_orig


def test_push_pull_zero_or_empty() -> None:
    empty_solid = Solid()
    res = PushPullEngine.execute_press_pull(empty_solid, Vector3D(0.0, 0.0, 0.0), Vector3D(0.0, 0.0, 1.0), 10.0)
    assert res.success is False

    valid = make_box(10.0, 10.0, 10.0)
    res_zero = PushPullEngine.execute_press_pull(valid, Vector3D(0.0, 0.0, 5.0), Vector3D(0.0, 0.0, 1.0), 0.0)
    assert res_zero.success is True
    assert res_zero.volume_delta == 0.0


# =========================================================================
# 3. Tests JointKinematicSolver (Fusion 360 Assembly Joints)
# =========================================================================

def test_assembly_joint_limits_and_transforms() -> None:
    anchor_p = JointAnchor(Vector3D(0.0, 0.0, 0.0), Vector3D(0.0, 0.0, 1.0), Vector3D(1.0, 0.0, 0.0))
    anchor_c = JointAnchor(Vector3D(0.0, 0.0, 0.0), Vector3D(0.0, 0.0, 1.0), Vector3D(1.0, 0.0, 0.0))
    limit = JointLimit(has_limits=True, min_val=-45.0, max_val=45.0, rest_val=0.0)

    joint = AssemblyJoint(
        "j_revolute", "Pivot Bras", FusionJointType.REVOLUTE,
        "base", "arm", anchor_p, anchor_c, angular_limit=limit
    )

    # Test limitation angulaire
    joint.set_motion(angle_deg=90.0)
    assert joint.current_angle_deg == 45.0  # Clampé à +45°

    joint.set_motion(angle_deg=-100.0)
    assert joint.current_angle_deg == -45.0  # Clampé à -45°

    mat = joint.compute_local_transform()
    assert mat.shape == (4, 4)
    assert np.allclose(mat[3, :], [0.0, 0.0, 0.0, 1.0])


def test_kinematic_solver_chain_propagation() -> None:
    solver = JointKinematicSolver()
    solver.set_grounded("base_frame")

    # Liaison 1 : Pivot entre bâti et bras 1
    a1 = JointAnchor(Vector3D(0.0, 0.0, 50.0), Vector3D(0.0, 0.0, 1.0), Vector3D(1.0, 0.0, 0.0))
    j1 = AssemblyJoint("j1", "Liaison 1", FusionJointType.REVOLUTE, "base_frame", "link_1", a1, a1)
    solver.add_joint(j1)

    # Liaison 2 : Glissière entre bras 1 et chariot
    a2 = JointAnchor(Vector3D(30.0, 0.0, 0.0), Vector3D(1.0, 0.0, 0.0), Vector3D(0.0, 1.0, 0.0))
    j2 = AssemblyJoint("j2", "Liaison 2", FusionJointType.SLIDER, "link_1", "carriage", a2, a2)
    solver.add_joint(j2)

    # Piloter les mouvements
    solver.drive_motion("j1", 30.0)
    solver.drive_motion("j2", 15.0)

    poses = solver.solve_poses()
    assert "base_frame" in poses
    assert "link_1" in poses
    assert "carriage" in poses
    assert np.allclose(poses["base_frame"], np.eye(4))
    assert not np.allclose(poses["carriage"], np.eye(4))


# =========================================================================
# 4. Tests ViewportShadingManager (Blender MatCaps & Zebra Analysis)
# =========================================================================

def test_viewport_shading_matcaps_and_zebra() -> None:
    sphere = make_sphere(15.0, segments=24)
    buf = sphere.to_mesh_buffer()
    eye = Vector3D(50.0, 50.0, 80.0)

    mgr = ViewportShadingManager()

    # 1. MatCap Clay
    mgr.set_shading_mode(ShadingMode.MATCAP_CLAY)
    buf_clay = mgr.apply_shading_to_buffer(buf, eye)
    assert buf_clay.vertex_colors is not None
    assert len(buf_clay.vertex_colors) == len(buf.vertices)
    assert buf_clay.vertex_colors[:, 3].min() >= 0.99  # Alpha 1.0

    # 2. MatCap Red Wax
    mgr.set_shading_mode(ShadingMode.MATCAP_RED_WAX)
    buf_wax = mgr.apply_shading_to_buffer(buf, eye)
    assert buf_wax.vertex_colors is not None
    # Rouge prédominant dans la cire rouge
    assert buf_wax.vertex_colors[:, 0].mean() > buf_wax.vertex_colors[:, 1].mean()

    # 3. Bandes zébrées de réflexion (Fusion 360 Zebra Stripes)
    mgr.set_shading_mode(ShadingMode.ZEBRA_STRIPES)
    buf_zebra = mgr.apply_shading_to_buffer(buf, eye)
    assert buf_zebra.vertex_colors is not None
    # Contraste fort noir/blanc (valeurs proches de 0.12 ou 0.92)
    shades = buf_zebra.vertex_colors[:, 0]
    assert (shades > 0.8).any()
    assert (shades < 0.2).any()

    # 4. Analyse d'angle de dépouille (Draft Angle Analysis)
    mgr.set_shading_mode(ShadingMode.DRAFT_ANGLE)
    buf_draft = mgr.apply_shading_to_buffer(buf, eye)
    assert buf_draft.vertex_colors is not None
    # Doit contenir des zones vertes (positive draft) et rouges (undercut/pôle inférieur)
    assert (buf_draft.vertex_colors[:, 1] > 0.8).any()  # Vert
    assert (buf_draft.vertex_colors[:, 0] > 0.8).any()  # Rouge


# =========================================================================
# 5. Tests MagneticSnapEngine (Blender Magnetic Snapping)
# =========================================================================

def test_magnetic_snap_grid_and_origin() -> None:
    engine = MagneticSnapEngine()
    cam = CADCamera()
    cam.set_preset_view("TOP")

    # Recherche au centre de l'écran (proche de l'origine 0,0,0)
    snap = engine.find_best_snap(400, 300, 800, 600, cam, [])
    assert snap.has_snap is True
    assert snap.target_type in (SnapTarget.ORIGIN, SnapTarget.GRID)
    assert abs(snap.snapped_point.z) < 1e-4


def test_magnetic_snap_vertices_and_edges() -> None:
    engine = MagneticSnapEngine()
    cam = CADCamera()
    box = make_box(40.0, 40.0, 40.0, center=True)
    buffers = [box.to_mesh_buffer()]

    # Doit détecter sommets ou milieux d'arêtes
    snap = engine.find_best_snap(400, 300, 800, 600, cam, buffers)
    assert snap.has_snap is True
    assert snap.target_type in (SnapTarget.VERTEX, SnapTarget.EDGE_MIDPOINT, SnapTarget.GRID, SnapTarget.ORIGIN)


# =========================================================================
# 6. Tests TransformGizmo (Blender / Fusion 360 Manipulator)
# =========================================================================

def test_transform_gizmo_hit_test_and_deltas() -> None:
    gizmo = TransformGizmo()
    gizmo.set_target(Vector3D(0.0, 0.0, 0.0))
    assert gizmo.is_visible is True

    # Rayon pointant directement vers l'axe X (+X = (15, 0, 0))
    ray_orig = Vector3D(15.0, -50.0, 0.0)
    ray_dir = Vector3D(0.0, 1.0, 0.0)

    hit_axis = gizmo.hit_test(ray_orig, ray_dir)
    assert hit_axis == GizmoAxis.X

    # Calcul de déplacement le long de l'axe X
    delta_x = gizmo.compute_translation_delta(GizmoAxis.X, 12.5)
    assert delta_x.x == 12.5
    assert delta_x.y == 0.0
    assert delta_x.z == 0.0

    delta_z = gizmo.compute_translation_delta(GizmoAxis.Z, -8.0)
    assert delta_z.z == -8.0

    gizmo.hide()
    assert gizmo.is_visible is False
    assert gizmo.hit_test(ray_orig, ray_dir) == GizmoAxis.NONE
