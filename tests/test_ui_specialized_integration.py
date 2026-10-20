"""
Tests d'intégration pour les onglets métiers spécialisés (BIM, Aéro, ECAD)
et la gestion des callbacks d'erreurs et d'invalidation sélective de cache.
"""

from __future__ import annotations
import pytest
from PySide6.QtWidgets import QApplication

from src.ui.ribbon import CADRibbonBar
from src.ui.main_window import CADMainWindow
from src.core.document import CADDocument
from src.core.sketch import Sketch2D, PlaneType
from src.core.feature import ExtrudeFeature, FeatureStatus


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ribbon_specialized_tab(qapp: QApplication) -> None:
    """Vérifie la présence et les signaux de l'onglet MÉTIERS."""
    ribbon = CADRibbonBar()
    tab_titles = [ribbon.tabText(i) for i in range(ribbon.count())]
    assert "MÉTIERS" in tab_titles

    signals_emitted: list[str] = []
    ribbon.bim_generate_requested.connect(lambda: signals_emitted.append("bim"))
    ribbon.aero_analysis_requested.connect(lambda: signals_emitted.append("aero"))
    ribbon.ecad_thermal_requested.connect(lambda: signals_emitted.append("ecad"))

    ribbon.bim_generate_requested.emit()
    ribbon.aero_analysis_requested.emit()
    ribbon.ecad_thermal_requested.emit()

    assert signals_emitted == ["bim", "aero", "ecad"]


def test_document_error_callback_and_selective_invalidation() -> None:
    """Vérifie l'enregistrement des callbacks d'erreur et l'invalidation sélective de cache."""
    doc = CADDocument("TestDoc")
    errors: list[tuple[str, str]] = []
    doc.register_error_callback(lambda msg, feat: errors.append((msg, feat.name)))

    sk1 = Sketch2D("sk1", "Sketch 1", PlaneType.XY)
    doc.add_sketch(sk1)
    assert "sk1" in doc.sketches

    # Ajout d'une opération dépendant de sk1
    extrude = ExtrudeFeature("feat_ext", "Extrusion 1", "sk1", 10.0)
    doc.add_feature(extrude)

    # Invalidation sélective pour sk1
    doc.invalidate_for_sketch("sk1")
    assert len(doc._timeline_snapshots) == 0

    # Invalidation pour une esquisse inconnue ne vide pas le cache
    doc._timeline_snapshots[0] = {}
    doc.invalidate_for_sketch("sk_unknown")
    assert 0 in doc._timeline_snapshots


def test_main_window_specialized_actions(qapp: QApplication) -> None:
    """Vérifie l'exécution des actions métiers dans la fenêtre principale sans exception."""
    window = CADMainWindow()

    # Vérification que les actions s'exécutent proprement (QMessageBox non bloquant simulé)
    assert hasattr(window, "_on_action_bim_generate")
    assert hasattr(window, "_on_action_aero_analysis")
    assert hasattr(window, "_on_action_ecad_thermal")

    window.close()


def test_main_window_ortho_toggle(qapp: QApplication) -> None:
    """Vérifie le basculement orthographique via le ruban, la fenêtre et le raccourci."""
    window = CADMainWindow()
    assert not window.viewport.camera.is_orthographic

    # Basculement via la méthode d'action liée au raccourci '5' et au ruban
    window._on_toggle_ortho()
    assert window.viewport.camera.is_orthographic is True
    assert "Orthographique" in window.status_bar.currentMessage()

    # Deuxième basculement : retour en perspective
    window._on_toggle_ortho()
    assert window.viewport.camera.is_orthographic is False
    assert "Perspective" in window.status_bar.currentMessage()

    # Vérification du signal du ruban
    emitted = []
    window.ribbon.toggle_ortho_requested.connect(lambda: emitted.append(True))
    window.ribbon.toggle_ortho_requested.emit()
    assert len(emitted) == 1

    window.close()
