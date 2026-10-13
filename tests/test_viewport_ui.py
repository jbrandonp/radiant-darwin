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
