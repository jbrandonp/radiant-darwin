"""
Tests unitaires pour les packages découplés src/catalog/ et src/system/.
Valide le fonctionnement natif et la rétrocompatibilité intégrale via les shims src/core/.
"""

from __future__ import annotations
import tempfile
import os

from src.core.document import CADDocument
from src.catalog.fasteners import (
    create_hex_bolt,
    create_socket_head_cap_screw,
    create_hex_nut,
    create_washer,
    clear_fastener_cache,
    ISO_METRIC_TABLE,
)
from src.core.fasteners import FastenerFeature
from src.system.preferences import (
    CADPreferences,
    UserPreferences,
    PreferencesManager,
    UnitLength,
    CameraNavigationPreset,
    ThemeMode,
)
from src.system.undo_redo import (
    UndoRedoManager,
    CADCommand,
)
from src.system.worker_pool import (
    CADWorkerPool,
    WorkerPool,
    TPMSWorkerParams,
)

import src.core.fasteners as core_fasteners
import src.core.preferences as core_preferences
import src.core.undo_redo as core_undo_redo
import src.core.worker_pool as core_worker_pool


def test_catalog_fasteners_and_shims() -> None:
    """Vérifie que la création de visserie fonctionne à la fois depuis src.catalog et src.core."""
    bolt = create_hex_bolt("M6", length=20.0)
    assert not bolt.is_empty()
    assert bolt.volume() > 0.0

    # Test via shim
    bolt_shim = core_fasteners.create_hex_bolt("M6", length=20.0)
    assert not bolt_shim.is_empty()

    # Nut & Washer
    nut = create_hex_nut("M8")
    washer = create_washer("M8")
    assert not nut.is_empty()
    assert not washer.is_empty()

    # FastenerFeature
    feat = FastenerFeature("fastener_1", "Screw", "hex_bolt", "M6", 25.0)
    assert feat.name == "Screw"

    # Cache clear
    clear_fastener_cache()
    core_fasteners.clear_fastener_cache()


def test_system_preferences_and_shims() -> None:
    """Vérifie le chargement et la persistance des préférences utilisateur."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pref_file = os.path.join(tmpdir, "prefs.json")
        mgr = PreferencesManager(config_path=pref_file)
        assert mgr.preferences.unit_length == UnitLength.MM
        assert mgr.preferences.navigation_preset == CameraNavigationPreset.BLENDER

        # Modification et sauvegarde
        mgr.preferences.theme = ThemeMode.LIGHT
        mgr.save()
        assert os.path.exists(pref_file)

        # Relecture via shim
        mgr_shim = core_preferences.PreferencesManager(config_path=pref_file)
        assert mgr_shim.preferences.theme == core_preferences.ThemeMode.LIGHT


def test_system_undo_redo_and_shims() -> None:
    """Vérifie le gestionnaire transactionnel Undo/Redo."""
    doc = CADDocument("test_doc")
    mgr = UndoRedoManager(doc, max_history_depth=10)
    assert not mgr.can_undo
    assert not mgr.can_redo

    mgr_shim = core_undo_redo.UndoRedoManager(doc, max_history_depth=10)
    assert not mgr_shim.can_undo


def test_system_worker_pool_and_shims() -> None:
    """Vérifie les structures de tâches et singleton du WorkerPool."""
    pool = CADWorkerPool.get_instance()
    assert pool is not None

    pool_shim = core_worker_pool.WorkerPool.get_instance()
    assert pool_shim is not None

    params = TPMSWorkerParams(0.0, 0.0, 0.0, 10.0, 10.0, 10.0, 10.0, 1.5, "gyroid")
    assert params.min_x == 0.0
    assert params.max_x == 10.0
