"""
Tests d'intégration pour le gestionnaire transactionnel Undo/Redo dans l'interface principale (CADMainWindow).
"""

from __future__ import annotations
import pytest
from PySide6.QtWidgets import QApplication

from src.ui.main_window import CADMainWindow
from src.core.feature import BoxFeature
from src.core.types import BooleanOperation


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_add_feature_undo_redo(qapp: QApplication) -> None:
    """Vérifie que l'ajout d'une feature via _add_feature_with_undo est annulable puis rétablissable."""
    window = CADMainWindow()
    initial_feature_count = len(window.document.features)
    assert window.undo_redo_manager.can_undo is False

    # Ajout d'une boîte via _add_feature_with_undo
    feat = BoxFeature("test_box_undo", "Boîte Test", 20.0, 20.0, 20.0, True, BooleanOperation.NEW_BODY)
    window._add_feature_with_undo(feat)

    assert len(window.document.features) == initial_feature_count + 1
    assert window.undo_redo_manager.can_undo is True

    # Annulation (Ctrl+Z)
    window._on_action_undo()
    assert len(window.document.features) == initial_feature_count
    assert window.undo_redo_manager.can_undo is False
    assert window.undo_redo_manager.can_redo is True

    # Rétablissement (Ctrl+Y)
    window._on_action_redo()
    assert len(window.document.features) == initial_feature_count + 1
    assert window.undo_redo_manager.can_undo is True
    assert window.undo_redo_manager.can_redo is False

    window.close()
