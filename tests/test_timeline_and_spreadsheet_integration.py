"""
Tests unitaires pour l'intégration de la timeline réorganisable
et du tableur paramétrique interactif.
"""

import pytest
from PySide6.QtWidgets import QApplication

from src.core.document import CADDocument
from src.core.feature import BoxFeature, CylinderFeature
from src.ui.timeline import CADTimeline, TimelineStepButton
from src.ui.spreadsheet_widget import SpreadsheetWidget, ParametricSpreadsheet


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def test_timeline_reordering(qapp: QApplication) -> None:
    """Vérifie la réorganisation interactive de la timeline chronologique."""
    doc = CADDocument("Timeline Reorder Test")
    box = BoxFeature("f1", "Boite Base", width=20.0, height=20.0, depth=10.0)
    cyl = CylinderFeature("f2", "Cylindre Bossage", radius=5.0, height=15.0)

    doc.add_feature(box)
    doc.add_feature(cyl)
    assert doc.features[0].feature_id == "f1"
    assert doc.features[1].feature_id == "f2"

    timeline = CADTimeline(doc)
    assert timeline.steps_layout.count() == 2

    # Déplacer f1 à l'index 1 (après f2)
    timeline._on_reorder_requested(0, 1)
    assert doc.features[0].feature_id == "f2"
    assert doc.features[1].feature_id == "f1"

    # Vérifier que les boutons ont été rafraîchis
    timeline.refresh()
    assert timeline.steps_layout.count() == 2


def test_spreadsheet_widget_interaction(qapp: QApplication) -> None:
    """Vérifie la saisie interactive de formules et le rafraîchissement tabulaire."""
    sheet = ParametricSpreadsheet()
    sheet.set_cell("A1", "12.5")
    sheet.set_alias("A1", "Largeur")
    sheet.set_cell("A2", "=Largeur * 2")

    widget = SpreadsheetWidget(sheet)
    qt_w = widget.get_widget()
    assert qt_w is not None

    # Vérifier les valeurs calculées dans les cellules
    assert sheet.get_cell_value("A1") == 12.5
    assert sheet.get_cell_value("A2") == 25.0

    # Simuler la sélection et l'application d'une nouvelle formule
    widget._current_cell_ref = "A3"
    widget.formula_edit.setText("=A2 + 10")
    widget.alias_edit.setText("HauteurTotale")
    widget._on_apply_clicked()

    assert sheet.get_cell_value("A3") == 35.0
    assert sheet.get_alias_value("HauteurTotale") == 35.0
