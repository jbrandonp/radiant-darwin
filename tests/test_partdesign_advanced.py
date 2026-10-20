"""
Tests exhaustifs des fonctionnalités volumiques avancées PartDesign :
1. Congés à rayon variable (VariableRadiusFilletFeature)
2. Lissage multi-rails avec courbes guides (MultiRailLoftFeature)
3. Plans de référence dynamiques multi-modes (DynamicDatumPlaneFeature)
"""

import numpy as np
import pytest

from src.core.types import BooleanOperation, FeatureStatus, PlaneType, Point2D, Vector3D
from src.core.geometry import Solid, make_box
from src.core.sketch import Sketch2D
from src.core.operations_advanced import (
    VariableRadiusFilletFeature, MultiRailLoftFeature,
    DynamicDatumPlaneFeature, DatumAttachmentMode
)
from src.core.registry import FeatureRegistry, FeatureCategory


def test_variable_radius_fillet_evaluation() -> None:
    """Vérifie l'application d'un congé à rayon variable sur un pavé droit."""
    box = make_box(40.0, 40.0, 40.0, name="BaseCube")
    bodies = {"body_cube": box}
    sketches = {}

    feat = VariableRadiusFilletFeature(
        feature_id="vfillet_1",
        target_body_id="body_cube",
        start_radius=1.0,
        end_radius=4.0,
        mid_radius=2.5,
        steps=12
    )

    updated = feat.evaluate(bodies, sketches)
    assert feat.status == FeatureStatus.OK
    assert "body_cube" in updated
    res_solid = updated["body_cube"]
    assert res_solid.volume() > 0.0
    assert res_solid.is_watertight() is True


def test_multi_rail_loft_with_guide_curves() -> None:
    """Vérifie le lissage 3D peau tendue le long de rails directeurs."""
    # Création des deux profils d'esquisse
    s1 = Sketch2D("sketch_base", plane=PlaneType.XY, offset_distance=0.0)
    s1.add_rectangle(Point2D(-10.0, -10.0), 20.0, 20.0)

    s2 = Sketch2D("sketch_top", plane=PlaneType.XY, offset_distance=50.0)
    s2.add_rectangle(Point2D(-15.0, -15.0), 30.0, 30.0)

    sketches = {"sketch_base": s1, "sketch_top": s2}
    bodies = {}

    # Courbes guides 3D simulant une déformation galbée (ex: conduit ou carénage)
    rail_left = [(-10.0, 0.0, 0.0), (-18.0, 0.0, 25.0), (-15.0, 0.0, 50.0)]
    rail_right = [(10.0, 0.0, 0.0), (18.0, 0.0, 25.0), (15.0, 0.0, 50.0)]

    loft_feat = MultiRailLoftFeature(
        feature_id="loft_rails_1",
        name="GuidedFuselage",
        profile_sketch_ids=["sketch_base", "sketch_top"],
        guide_rail_curves=[rail_left, rail_right],
        num_intermediate_sections=10,
        num_segments=24,
        operation=BooleanOperation.NEW_BODY
    )

    updated = loft_feat.evaluate(bodies, sketches)
    assert loft_feat.status == FeatureStatus.OK
    body_key = f"body_{loft_feat.feature_id}"
    assert body_key in updated
    loft_solid = updated[body_key]
    assert loft_solid.volume() > 0.0
    assert loft_solid.is_watertight() is True
    b_min, b_max = loft_solid.bounding_box()
    assert b_max.z >= 45.0


def test_dynamic_datum_plane_three_points() -> None:
    """Vérifie la création d'un plan de référence passant par 3 points non alignés."""
    p1 = (0.0, 0.0, 0.0)
    p2 = (10.0, 0.0, 0.0)
    p3 = (0.0, 20.0, 0.0)

    plane_feat = DynamicDatumPlaneFeature(
        feature_id="datum_3p",
        name="ObliquePlane",
        mode=DatumAttachmentMode.THREE_POINTS,
        point1=p1,
        point2=p2,
        point3=p3
    )

    # Normale orientée vers Z positif (10, 0, 0) x (0, 20, 0) = (0, 0, 200) -> Z+
    assert plane_feat.normal.z == pytest.approx(1.0, abs=1e-3)
    assert plane_feat.u_axis.x == pytest.approx(1.0, abs=1e-3)

    # Projection d'un point 3D dans le repère local 2D (u, v)
    pt_2d = plane_feat.project_point_to_plane((5.0, 15.0, 0.0))
    assert pt_2d.u == pytest.approx(5.0, abs=1e-3)
    assert pt_2d.v == pytest.approx(15.0, abs=1e-3)

    # Matrice de passage 4x4
    mat = plane_feat.get_transformation_matrix()
    assert mat.shape == (4, 4)
    assert mat[3, 3] == 1.0


def test_dynamic_datum_plane_normal_to_curve() -> None:
    """Vérifie la création d'un plan de référence normal à une tangente de courbe."""
    tangent = (0.0, 0.0, 1.0)
    p_curve = (15.0, 25.0, 30.0)

    plane_feat = DynamicDatumPlaneFeature(
        feature_id="datum_norm_curve",
        mode=DatumAttachmentMode.NORMAL_TO_CURVE,
        point1=p_curve,
        tangent_or_normal=tangent
    )

    assert plane_feat.origin.x == pytest.approx(15.0)
    assert plane_feat.origin.y == pytest.approx(25.0)
    assert plane_feat.origin.z == pytest.approx(30.0)
    assert plane_feat.normal.z == pytest.approx(1.0, abs=1e-3)


def test_partdesign_features_in_registry() -> None:
    """Vérifie que les nouvelles features sont bien référencées dans le FeatureRegistry."""
    assert FeatureRegistry.is_registered("VariableRadiusFilletFeature") is True
    assert FeatureRegistry.is_registered("MultiRailLoftFeature") is True
    assert FeatureRegistry.is_registered("DynamicDatumPlaneFeature") is True

    desc_var_fillet = FeatureRegistry.get("VariableRadiusFilletFeature")
    assert desc_var_fillet is not None
    assert desc_var_fillet.category == FeatureCategory.MODIFICATION

    desc_loft_rails = FeatureRegistry.get("MultiRailLoftFeature")
    assert desc_loft_rails is not None
    assert desc_loft_rails.category == FeatureCategory.SKETCH_BASED


def test_fidget_interval_tree_evaluation_helpers() -> None:
    """Vérifie l'évaluation modulaire scalaire et par intervalle des primitives Fidget."""
    from src.core.nexus_kernel.fidget_interval_tree import SDFIntervalTreeNode, CSGOpType, SDFInterval

    sphere_node = SDFIntervalTreeNode(op=CSGOpType.SPHERE, params=(10.0, 0.0, 0.0, 0.0))
    # Centre (0,0,0) -> distance = -10.0
    assert sphere_node.eval_scalar(0.0, 0.0, 0.0) == pytest.approx(-10.0)
    # Surface (10,0,0) -> distance = 0.0
    assert sphere_node.eval_scalar(10.0, 0.0, 0.0) == pytest.approx(0.0)

    # Boîte demi-dimensions (5, 5, 5)
    box_node = SDFIntervalTreeNode(op=CSGOpType.BOX, params=(5.0, 5.0, 5.0))
    assert box_node.eval_scalar(0.0, 0.0, 0.0) <= 0.0
    assert box_node.eval_scalar(10.0, 0.0, 0.0) == pytest.approx(5.0)

    # Intervalle sphère
    ix = SDFInterval(-2.0, 2.0)
    iy = SDFInterval(-2.0, 2.0)
    iz = SDFInterval(-2.0, 2.0)
    res_int = sphere_node.eval_interval(ix, iy, iz)
    assert res_int.min_val < 0.0


def test_fidget_interval_tree_pruning_rules() -> None:
    """Vérifie les règles d'élagage d'arbre d'intervalles (Union, Intersection, Différence)."""
    from src.core.nexus_kernel.fidget_interval_tree import SDFIntervalTreeNode, CSGOpType, SDFInterval

    node_a = SDFIntervalTreeNode(op=CSGOpType.CONSTANT, params=(1.0,))
    node_b = SDFIntervalTreeNode(op=CSGOpType.CONSTANT, params=(5.0,))

    int_a = SDFInterval(1.0, 2.0)
    int_b = SDFInterval(4.0, 6.0)

    # 1. Union: A max (2.0) < B min (4.0) -> A l'emporte (min)
    pruned_u = SDFIntervalTreeNode._try_prune_union(node_a, node_b, int_a, int_b)
    assert pruned_u == node_a

    # 2. Intersection: A min (1.0) < B max (6.0), mais B min (4.0) > A max (2.0) -> B l'emporte (max)
    pruned_i = SDFIntervalTreeNode._try_prune_intersection(node_a, node_b, int_a, int_b)
    assert pruned_i == node_b

    # 3. Différence: max(L, -R)
    # L in [1.0, 2.0], R in [-10.0, -8.0] -> -R in [8.0, 10.0]
    # L max (2.0) < -R min (8.0) -> -R l'emporte
    int_r = SDFInterval(-10.0, -8.0)
    pruned_d = SDFIntervalTreeNode._try_prune_difference(node_a, node_b, int_a, int_r)
    assert pruned_d is not None
    assert pruned_d.op == CSGOpType.CONSTANT
    assert pruned_d.params == (8.0,)


def test_localized_top_edge_fillet_preserves_planar_bottom() -> None:
    """Vérifie que le congé d'arête en mode 'top' arrondit le dessus sans modifier la face inférieure."""
    from src.core.geometry import make_box
    from src.core.operations.surfaces import FilletFeature
    from src.core.types import FeatureStatus

    box = make_box(30.0, 30.0, 20.0, center=False)
    bodies = {"box_1": box}

    fillet = FilletFeature(
        feature_id="f_top",
        name="TopFillet",
        target_body_id="box_1",
        radius=2.0,
        edges_mode="top"
    )
    res = fillet.evaluate(bodies, {})
    assert fillet.status == FeatureStatus.OK
    assert "box_1" in res

    filleted_solid = res["box_1"]
    assert filleted_solid.volume() < box.volume()
    assert filleted_solid.volume() > 0.95 * box.volume()
    assert filleted_solid.is_watertight() is True

    # Le bas de la boîte doit rester exactement à Z = 0.0 sans aucun rétrécissement
    b_min, b_max = filleted_solid.bounding_box()
    assert b_min.z == pytest.approx(0.0, abs=1e-3)
    assert b_min.x == pytest.approx(0.0, abs=1e-3)
    assert b_min.y == pytest.approx(0.0, abs=1e-3)
    assert b_max.z == pytest.approx(20.0, abs=1e-3)


def test_specific_edge_fillet_and_chamfer() -> None:
    """Vérifie l'arrondi et le chanfrein ciblé sur des arêtes topologiques spécifiques (edge_indices)."""
    from src.core.geometry import make_box
    from src.core.operations.surfaces import FilletFeature, ChamferFeature
    from src.core.types import FeatureStatus

    box = make_box(20.0, 20.0, 20.0, center=False)
    bodies = {"b1": box}

    # 1. Chanfrein sur arête 0 uniquement
    chamfer = ChamferFeature("ch_edge", target_body_id="b1", distance=2.0, edge_indices=[0])
    res_ch = chamfer.evaluate(bodies, {})
    assert chamfer.status == FeatureStatus.OK
    ch_solid = res_ch["b1"]
    assert ch_solid.volume() < box.volume()
    assert ch_solid.is_watertight() is True

    # 2. Congé sur arête 0 uniquement
    fillet = FilletFeature("fl_edge", target_body_id="b1", radius=2.0, edge_indices=[0])
    res_fl = fillet.evaluate(bodies, {})
    assert fillet.status == FeatureStatus.OK
    fl_solid = res_fl["b1"]
    assert fl_solid.volume() < box.volume()
    assert fl_solid.is_watertight() is True

