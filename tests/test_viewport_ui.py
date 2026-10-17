"""
Tests unitaires pour les composants UI du Viewport (NavBar, ViewCube, GLRenderer config).
"""

from __future__ import annotations
import pytest
from PySide6.QtWidgets import QApplication

from src.viewport.nav_bar import ViewportNavBar
from src.viewport.view_cube import ViewCubeOverlay
from src.viewport.gl_renderer import GLRenderer
from src.core.document import CADDocument
from src.ui.browser_tree import CADBrowserTree


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Fournit une instance QApplication partagée pour les tests de widgets Qt."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_nav_bar_initialization_and_signals(qapp: QApplication) -> None:
    """Vérifie la création de la barre de navigation et ses signaux."""
    nav = ViewportNavBar()
    assert nav.btn_grid.isChecked() is True
    assert nav.btn_edges.isChecked() is True

    signals_received = []

    nav.orbit_requested.connect(lambda: signals_received.append("orbit"))
    nav.zoom_fit_requested.connect(lambda: signals_received.append("fit"))
    nav.toggle_grid_requested.connect(lambda: signals_received.append("grid"))
    nav.toggle_edges_requested.connect(lambda: signals_received.append("edges"))

    nav.btn_orbit.click()
    nav.btn_fit.click()
    nav.btn_grid.click()
    nav.btn_edges.click()

    assert "orbit" in signals_received
    assert "fit" in signals_received
    assert "grid" in signals_received
    assert "edges" in signals_received


def test_view_cube_signals(qapp: QApplication) -> None:
    """Vérifie les signaux du ViewCube avec ses libellés français."""
    vc = ViewCubeOverlay()
    received = []
    vc.view_selected.connect(lambda name: received.append(name))

    vc.view_selected.emit("TOP")
    vc.view_selected.emit("FRONT")
    vc.view_selected.emit("FIT")

    assert received == ["TOP", "FRONT", "FIT"]


def test_gl_renderer_config() -> None:
    """Vérifie les paramètres de rendu initial et couleurs de fond studio."""
    renderer = GLRenderer()
    assert renderer.show_grid is True
    assert renderer.show_edges is True
    assert renderer.bg_color_top[0] > 0.1
    assert renderer.bg_color_bottom[0] > 0.05


def test_browser_tree_context_menu_setup(qapp: QApplication) -> None:
    """Vérifie l'arborescence du modèle et la gestion de documents."""
    doc = CADDocument("TestDoc")
    tree = CADBrowserTree(doc)
    assert tree.tree.topLevelItemCount() == 1
    assert "TestDoc" in tree.tree.topLevelItem(0).text(0)


def test_properties_panel_field_ranges(qapp: QApplication) -> None:
    """Vérifie que le panneau de propriétés configure correctement les plages négatives, entières et angulaires."""
    from src.ui.properties_panel import CADPropertiesPanel
    from src.core.feature import BoxFeature, ConeFeature
    from src.core.operations_advanced import HoleFeature, CircularPatternFeature

    doc = CADDocument("TestDoc")
    panel = CADPropertiesPanel(doc)

    # 1. Feature avec coordonnées négatives
    hole = HoleFeature("h1", "Trou Negatif", target_body_id="b1", pos_x=-50.0, pos_y=-25.0, diameter=8.0)
    doc.add_feature(hole)
    panel.set_feature("h1")
    assert "pos_x" in panel.param_spinboxes
    spin_x = panel.param_spinboxes["pos_x"]
    assert spin_x.minimum() < 0.0
    assert spin_x.value() == -50.0

    # 2. Feature avec count entier et angle négatif
    circ = CircularPatternFeature("c1", "Pattern Circulaire", source_body_id="b1", count=8, total_angle_deg=-120.0)
    doc.add_feature(circ)
    panel.set_feature("c1")
    assert "count" in panel.param_spinboxes
    spin_count = panel.param_spinboxes["count"]
    assert spin_count.suffix() == ""
    assert spin_count.value() == 8.0

    assert "total_angle" in panel.param_spinboxes
    spin_angle = panel.param_spinboxes["total_angle"]
    assert spin_angle.minimum() < 0.0
    assert spin_angle.value() == -120.0

    # 3. Feature avec radius_top à 0.0 (cône pointu)
    cone = ConeFeature("cone1", "Cone", radius_bottom=10.0, radius_top=0.0, height=20.0)
    doc.add_feature(cone)
    panel.set_feature("cone1")
    assert "radius_top" in panel.param_spinboxes
    assert panel.param_spinboxes["radius_top"].minimum() == 0.0
    assert panel.param_spinboxes["radius_top"].value() == 0.0

    panel.set_feature("")
    assert len(panel.param_spinboxes) == 0


def test_transform_gizmo_interaction() -> None:
    """Vérifie le fonctionnement du manipulateur 3D interactif (TransformGizmo)."""
    from src.viewport.transform_gizmo import TransformGizmo, GizmoMode, GizmoAxis
    from src.core.types import Vector3D

    gizmo = TransformGizmo()
    assert gizmo.is_visible is False

    # 1. Activation et positionnement
    gizmo.set_target(Vector3D(0.0, 0.0, 0.0))
    assert gizmo.is_visible is True
    assert gizmo.position == Vector3D(0.0, 0.0, 0.0)

    # 2. Test d'intersection par rayon sur l'axe X
    ray_origin = Vector3D(15.0, 0.0, 100.0)
    ray_dir = Vector3D(0.0, 0.0, -1.0)
    hit_axis = gizmo.hit_test(ray_origin, ray_dir)
    assert hit_axis == GizmoAxis.X
    assert gizmo.hovered_axis == GizmoAxis.X

    # 3. Session de glissement en translation
    gizmo.start_drag(GizmoAxis.X, mouse_x=100.0, mouse_y=200.0, ray_origin=ray_origin, ray_dir=ray_dir)
    assert gizmo.is_dragging is True
    assert gizmo.active_axis == GizmoAxis.X

    delta_t, delta_r, delta_s = gizmo.update_drag(
        mouse_x=140.0, mouse_y=200.0,
        ray_origin=ray_origin, ray_dir=ray_dir
    )
    assert delta_t.x > 0.0
    assert delta_t.y == 0.0
    assert delta_t.z == 0.0
    gizmo.end_drag()
    assert gizmo.is_dragging is False

    # 4. Mode Rotation
    gizmo.set_mode(GizmoMode.ROTATE)
    assert gizmo.mode == GizmoMode.ROTATE
    gizmo.start_drag(GizmoAxis.ROTATE_Z, mouse_x=100.0, mouse_y=100.0, ray_origin=ray_origin, ray_dir=ray_dir)
    _, rot_deg, _ = gizmo.update_drag(120.0, 100.0, ray_origin, ray_dir)
    assert rot_deg > 0.0
    gizmo.end_drag()

    # 5. Mode Échelle
    gizmo.set_mode(GizmoMode.SCALE)
    gizmo.start_drag(GizmoAxis.SCALE_XYZ, mouse_x=50.0, mouse_y=50.0, ray_origin=ray_origin, ray_dir=ray_dir)
    _, _, scale_vec = gizmo.update_drag(60.0, 50.0, ray_origin, ray_dir)
    assert scale_vec.x > 1.0
    gizmo.end_drag()

    # 6. Masquage
    gizmo.hide()
    assert gizmo.is_visible is False
    assert gizmo.hovered_axis == GizmoAxis.NONE

