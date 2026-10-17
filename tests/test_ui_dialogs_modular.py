"""
Tests unitaires pour le sous-paquet modulaire des boîtes de dialogue Qt (src.ui.dialogs).
"""

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.dialogs import (
    CreateBoxDialog,
    CreateCylinderDialog,
    CreateSphereDialog,
    CreateConeDialog,
    CreateTorusDialog,
    CreateWedgeDialog,
    CreatePipeDialog,
    FastenerDialog,
    ExtrudeDialog,
    RevolveDialog,
    HoleDialog,
    ShellDialog,
    CombineDialog,
    LoftDialog,
    SweepDialog,
    FilletDialog,
    ChamferDialog,
    DraftDialog,
    FEADialog,
    ParametersDialog,
    SheetMetalDialog,
    RenderDialog,
    MeasureDialog,
    MeshAnalysisDialog,
    SectionCutDialog,
)
from src.core.parameters import ParameterTable


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Fixture Qt Application pour les tests d'interface graphique."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dialogs_import_and_instantiation(qapp: QApplication) -> None:
    """Vérifie que les dialogues peuvent être instanciés correctement."""
    box_dlg = CreateBoxDialog(existing_bodies=["body_1"])
    assert box_dlg.width() > 0
    assert box_dlg.windowTitle() == "Créer une Boîte (Box)"

    cyl_dlg = CreateCylinderDialog(existing_bodies=[])
    assert cyl_dlg.windowTitle() == "Créer un Cylindre"

    param_table = ParameterTable()
    params_dlg = ParametersDialog(param_table)
    assert params_dlg.windowTitle() == "Paramètres Utilisateur (fx)"



def test_dialogs_facade_integrity() -> None:
    """Vérifie que le module src.ui.dialogs expose les 25 classes."""
    import src.ui.dialogs as dlgs
    assert len(dlgs.__all__) == 25
    for name in dlgs.__all__:
        assert hasattr(dlgs, name)
        assert getattr(dlgs, name) is not None
